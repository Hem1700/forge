"""External research agent.

Before weaponizing a CVE-bearing finding, this fetches the public advisory,
extracts patch commits / advisory URLs / affected version ranges, and returns
a research bundle that's fed into the ExploitScriptEngine prompt. Improves
script accuracy substantially — the LLM goes from "guess the patched version"
to having the actual fix metadata in front of it.

OSV (free, no API key) is the primary source. NVD is queried only if the
finding has a bare CVE id and no OSV match.
"""
from __future__ import annotations

import re
from typing import Any

import httpx


OSV_API = "https://api.osv.dev/v1/vulns"   # GET /v1/vulns/{id}
NVD_API = "https://services.nvd.nist.gov/rest/json/cves/2.0"

CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.I)
GHSA_RE = re.compile(r"\bGHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}\b", re.I)


def _candidate_ids(finding: dict) -> list[str]:
    """Pull plausible advisory IDs out of the finding."""
    out: list[str] = []
    for key in ("osv_id", "id"):
        v = finding.get(key)
        if isinstance(v, str) and (CVE_RE.search(v) or GHSA_RE.search(v)):
            out.append(v.strip())
    haystack = " ".join(
        str(finding.get(k, ""))
        for k in ("description", "evidence", "recommendation", "title")
    )
    if isinstance(finding.get("evidence"), list):
        haystack += " " + " ".join(str(e) for e in finding["evidence"])
    for m in CVE_RE.finditer(haystack):
        out.append(m.group(0).upper())
    for m in GHSA_RE.finditer(haystack):
        out.append(m.group(0))
    seen, deduped = set(), []
    for x in out:
        x_norm = x.upper() if x.upper().startswith("CVE-") else x
        if x_norm not in seen:
            seen.add(x_norm)
            deduped.append(x_norm)
    return deduped[:3]


class Researcher:
    """Fetches advisory + fix metadata for a finding."""

    def __init__(self, timeout: float = 8.0) -> None:
        self._timeout = timeout

    async def research(self, finding: dict) -> dict:
        ids = _candidate_ids(finding)
        if not ids:
            return {"sources": [], "advisories": [], "fix_refs": [], "first_fixed": None, "ranges": [], "summary": ""}

        advisories: list[dict] = []
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for advisory_id in ids:
                osv = await self._osv(client, advisory_id)
                if osv:
                    advisories.append(osv)

            # Fall back to NVD only if we got nothing from OSV
            if not advisories:
                for advisory_id in ids:
                    if advisory_id.startswith("CVE-"):
                        nvd = await self._nvd(client, advisory_id)
                        if nvd:
                            advisories.append(nvd)
                            break

        return self._merge(advisories)

    async def _osv(self, client: httpx.AsyncClient, advisory_id: str) -> dict | None:
        try:
            resp = await client.get(f"{OSV_API}/{advisory_id}")
            if resp.status_code != 200:
                return None
            data = resp.json()
        except Exception:
            return None

        refs = data.get("references", []) or []
        fix_refs = [r.get("url") for r in refs if r.get("type") in {"FIX", "PATCH"} and r.get("url")]
        advisory_refs = [r.get("url") for r in refs if r.get("type") in {"ADVISORY", "REPORT"} and r.get("url")]

        ranges: list[dict] = []
        first_fixed: str | None = None
        for aff in data.get("affected", []) or []:
            pkg = (aff.get("package") or {}).get("name", "")
            for r in aff.get("ranges", []) or []:
                events = r.get("events", []) or []
                introduced = next((e["introduced"] for e in events if "introduced" in e), None)
                fixed = next((e["fixed"] for e in events if "fixed" in e), None)
                ranges.append({"package": pkg, "introduced": introduced, "fixed": fixed})
                if fixed and first_fixed is None:
                    first_fixed = fixed

        return {
            "source": "osv",
            "id": data.get("id", advisory_id),
            "aliases": data.get("aliases", []),
            "summary": (data.get("summary") or "")[:400],
            "details": (data.get("details") or "")[:2000],
            "fix_refs": fix_refs[:5],
            "advisory_refs": advisory_refs[:5],
            "first_fixed": first_fixed,
            "ranges": ranges[:10],
        }

    async def _nvd(self, client: httpx.AsyncClient, cve_id: str) -> dict | None:
        try:
            resp = await client.get(NVD_API, params={"cveId": cve_id})
            if resp.status_code != 200:
                return None
            data = resp.json()
            items = data.get("vulnerabilities", []) or []
            if not items:
                return None
            cve = items[0].get("cve", {})
            descs = cve.get("descriptions", []) or []
            summary = next((d.get("value", "") for d in descs if d.get("lang") == "en"), "")
            refs = [r.get("url") for r in cve.get("references", []) or [] if r.get("url")]
            return {
                "source": "nvd",
                "id": cve_id,
                "aliases": [],
                "summary": summary[:400],
                "details": summary[:2000],
                "fix_refs": [u for u in refs if "patch" in u.lower() or "commit" in u.lower()][:5],
                "advisory_refs": refs[:5],
                "first_fixed": None,
                "ranges": [],
            }
        except Exception:
            return None

    def _merge(self, advisories: list[dict]) -> dict:
        if not advisories:
            return {"sources": [], "advisories": [], "fix_refs": [], "first_fixed": None, "ranges": [], "summary": ""}
        first_fixed = next((a["first_fixed"] for a in advisories if a.get("first_fixed")), None)
        all_fix_refs: list[str] = []
        for a in advisories:
            all_fix_refs.extend(a.get("fix_refs") or [])
        seen, fix_refs = set(), []
        for r in all_fix_refs:
            if r not in seen:
                seen.add(r)
                fix_refs.append(r)
        all_ranges: list[dict] = []
        for a in advisories:
            all_ranges.extend(a.get("ranges") or [])
        return {
            "sources": [a.get("source", "") for a in advisories],
            "advisories": advisories,
            "fix_refs": fix_refs[:10],
            "first_fixed": first_fixed,
            "ranges": all_ranges[:10],
            "summary": advisories[0].get("summary", ""),
        }


def research_block_for_prompt(research: dict | None) -> str:
    """Render a research bundle as a concise block for inclusion in an LLM prompt.
    Empty string if no research. Keeps token cost predictable."""
    if not research or not research.get("advisories"):
        return ""
    lines: list[str] = ["External research:"]
    if research.get("first_fixed"):
        lines.append(f"- First fixed version: {research['first_fixed']}")
    for r in research.get("ranges", [])[:6]:
        lines.append(
            f"- Range: {r.get('package','?')} introduced={r.get('introduced','?')} fixed={r.get('fixed','?')}"
        )
    if research.get("fix_refs"):
        lines.append("- Patch / fix commits:")
        for url in research["fix_refs"][:5]:
            lines.append(f"  · {url}")
    for a in research.get("advisories", [])[:2]:
        if a.get("summary"):
            lines.append(f"- Advisory ({a.get('id','')}): {a['summary']}")
        if a.get("details"):
            lines.append(f"  Details: {a['details'][:600]}")
    return "\n".join(lines)
