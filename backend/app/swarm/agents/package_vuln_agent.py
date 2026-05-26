# backend/app/swarm/agents/package_vuln_agent.py
"""PackageVulnAgent — runs Trivy against the host's package list to find CVEs,
then asks the LLM to assess exploitability in context.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage

from app.brain.llm_factory import TaskType, get_llm
from app.brain.os_fingerprint import OSFingerprint
from app.swarm.agents.base import BaseAgent
from app.swarm.agents.privesc_agent import _dict_to_fp
from app.ws import progress as ws_progress

logger = logging.getLogger(__name__)

_EXPLOITABILITY_SYSTEM_PROMPT = (
    "You are a security analyst assessing CVE exploitability in a specific system context. "
    "For each CVE, assess: (1) Is the affected package actually used/exposed based on the "
    "system context? (2) Does the configuration make exploitation easier or harder? "
    "(3) Assign exploitability_in_context score 0–1. "
    "Return ONLY a JSON array. Each item: "
    '{"vuln_id": str, "exploitability_in_context": float, "reasoning": str}.'
)

_CVSS_TO_SEVERITY = {
    9.0: "critical",
    7.0: "high",
    4.0: "medium",
    0.0: "low",
}


@dataclass
class PackageVulnAgent(BaseAgent):

    async def _execute(self, task: dict) -> dict:
        fp = _dict_to_fp(task.get("fingerprint", {}))
        org_id = task.get("org_id")
        findings: list[dict] = []

        if not fp.packages:
            self.signal_history.append(0.3)
            return {"agent_type": self.agent_type, "agent_id": self.agent_id, "findings": []}

        await ws_progress.progress(
            self.engagement_id, "package_vuln.scanning",
            f"Running Trivy against {len(fp.packages)} packages",
        )

        trivy_result = await self._run_trivy(fp.packages)
        if trivy_result is None:
            logger.warning("PackageVulnAgent: Trivy unavailable or failed")
            self.signal_history.append(0.3)
            return {"agent_type": self.agent_type, "agent_id": self.agent_id, "findings": []}

        raw_vulns = _parse_trivy_result(trivy_result)

        # Filter to CVSS >= 4.0
        significant = [v for v in raw_vulns if v.get("cvss_score", 0) >= 4.0]

        await ws_progress.progress(
            self.engagement_id, "package_vuln.trivy_done",
            f"Trivy found {len(raw_vulns)} CVEs total, {len(significant)} with CVSS≥4.0",
        )

        # Build base findings
        for v in significant:
            findings.append({
                "vulnerability": "known_cve",
                "severity": _cvss_to_severity(v.get("cvss_score", 0)),
                "description": f"{v['vuln_id']} in {v['package']} {v['installed_version']}: {v.get('description', '')}",
                "evidence": f"CVE: {v['vuln_id']}\nPackage: {v['package']} {v['installed_version']}\nFixed in: {v.get('fixed_version', 'unknown')}\nCVSS: {v.get('cvss_score')}",
                "recommendation": f"Upgrade {v['package']} to {v.get('fixed_version', 'latest available version')}.",
                "confidence_score": 0.85,
                "_vuln_id": v["vuln_id"],
            })

        # LLM exploitability-in-context for CVSS >= 6.0 findings, in batches of 10
        high_cvss = [v for v in significant if v.get("cvss_score", 0) >= 6.0]
        if high_cvss:
            context_summary = {
                "os": fp.os_info.get("NAME", "unknown"),
                "services": [s.get("name") for s in fp.services[:20]],
                "open_ports": [p.get("local") for p in fp.open_ports[:20]],
            }
            for i in range(0, len(high_cvss), 10):
                batch = high_cvss[i:i + 10]
                try:
                    llm = await get_llm(TaskType.package_vuln_analysis, org_id=org_id)
                    payload = {
                        "system_context": context_summary,
                        "cves": [{"vuln_id": v["vuln_id"], "package": v["package"],
                                  "description": v.get("description", "")} for v in batch],
                    }
                    messages = [
                        SystemMessage(content=_EXPLOITABILITY_SYSTEM_PROMPT),
                        HumanMessage(content=json.dumps(payload)),
                    ]
                    resp = await llm.ainvoke(messages)
                    raw = resp.content.strip().lstrip("```json").rstrip("```").strip()
                    assessments = json.loads(raw)
                    if isinstance(assessments, list):
                        scores = {a["vuln_id"]: a for a in assessments}
                        for f in findings:
                            vid = f.get("_vuln_id")
                            if vid and vid in scores:
                                f["evidence"] += f"\nExploitability in context: {scores[vid].get('exploitability_in_context')}\nReasoning: {scores[vid].get('reasoning', '')}"
                except Exception:
                    logger.exception("PackageVulnAgent: LLM exploitability batch %d failed", i // 10)

        # Clean internal key
        for f in findings:
            f.pop("_vuln_id", None)

        await ws_progress.progress(
            self.engagement_id, "package_vuln.done",
            f"PackageVulnAgent complete — {len(findings)} CVE findings",
        )
        self.signal_history.append(1.0 if findings else 0.4)
        return {
            "agent_type": self.agent_type,
            "agent_id": self.agent_id,
            "findings": findings,
            "packages_scanned": len(fp.packages),
            "cves_found": len(raw_vulns),
        }

    async def _run_trivy(self, packages: list[dict]) -> dict | None:
        """Write a CycloneDX SBOM and call trivy sbom on it. Returns raw JSON or None."""
        sbom = _make_cyclonedx_sbom(packages)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, prefix="forge_sbom_"
            ) as f:
                json.dump(sbom, f)
                tmp_path = f.name

            proc = await asyncio.create_subprocess_exec(
                "trivy", "sbom",
                "--format", "json",
                "--skip-db-update",
                "--quiet",
                tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode == 0 and stdout:
                return json.loads(stdout)
            return None
        except FileNotFoundError:
            logger.warning("PackageVulnAgent: trivy binary not found in PATH")
            return None
        except asyncio.TimeoutError:
            logger.warning("PackageVulnAgent: trivy timed out after 120s")
            return None
        except Exception:
            logger.exception("PackageVulnAgent: trivy execution failed")
            return None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


def _make_cyclonedx_sbom(packages: list[dict]) -> dict:
    """Build a minimal CycloneDX 1.4 SBOM from an OSFingerprint package list."""
    components = []
    for pkg in packages:
        name = pkg.get("name", "")
        version = pkg.get("version", "")
        if not name:
            continue
        components.append({
            "type": "library",
            "name": name,
            "version": version,
            "purl": f"pkg:deb/{name}@{version}" if version else f"pkg:deb/{name}",
        })
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.4",
        "version": 1,
        "components": components,
    }


def _parse_trivy_result(data: dict) -> list[dict]:
    """Extract flat CVE list from Trivy JSON output."""
    vulns = []
    for result in data.get("Results", []):
        for v in result.get("Vulnerabilities") or []:
            cvss = 0.0
            cvss_block = v.get("CVSS", {})
            for source_data in cvss_block.values():
                score = source_data.get("V3Score") or source_data.get("V2Score") or 0.0
                if score > cvss:
                    cvss = float(score)
            vulns.append({
                "vuln_id": v.get("VulnerabilityID", ""),
                "package": v.get("PkgName", ""),
                "installed_version": v.get("InstalledVersion", ""),
                "fixed_version": v.get("FixedVersion", ""),
                "cvss_score": cvss,
                "description": v.get("Description", "")[:300],
            })
    return vulns


def _cvss_to_severity(score: float) -> str:
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    return "low"
