import httpx
from app.swarm.agents.base import BaseAgent

PROBE_PAYLOADS = {
    "sqli": ["'", "1' OR '1'='1", "1; DROP TABLE users--"],
    "xss": ["<script>alert(1)</script>", '"><img src=x onerror=alert(1)>'],
    "idor": ["/1", "/2", "/0", "/../admin"],
    "auth_bypass": ["../", "..%2f", "%00"],
    "race_condition": [],
    "default": ["test", "probe"],
}


class ProbeAgent(BaseAgent):
    async def _compute_confidence(self, task: dict) -> tuple[float, str, int, str]:
        attack_class = task.get("attack_class", task.get("description", "")).lower()
        has_payloads = any(kw in attack_class for kw in PROBE_PAYLOADS)
        confidence = 0.75 if has_payloads else 0.55
        return confidence, f"Probe agent — {'has' if has_payloads else 'no'} specific payloads for attack class", 6, "low"

    async def _execute(self, task: dict) -> dict:
        surface = task.get("surface", "")
        attack_class = task.get("attack_class", "default")
        payloads = PROBE_PAYLOADS.get(attack_class, PROBE_PAYLOADS["default"])
        findings = []
        base_url = surface if surface.startswith("http") else f"https://{surface}"
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
                baseline = await client.get(base_url)
                baseline_len = len(baseline.text)
                baseline_status = baseline.status_code
                for payload in payloads[:3]:
                    try:
                        resp = await client.get(f"{base_url}?q={payload}")
                        length_diff = abs(len(resp.text) - baseline_len)
                        status_diff = resp.status_code != baseline_status
                        error_keywords = any(kw in resp.text.lower() for kw in ["error", "exception", "syntax", "warning", "stack trace"])
                        if error_keywords or status_diff or length_diff > 500:
                            findings.append({"type": "anomaly", "payload": payload, "status": resp.status_code, "length_diff": length_diff, "error_keywords": error_keywords})
                            self.emit_signal(0.8)
                        else:
                            self.emit_signal(0.2)
                    except Exception:
                        self.emit_signal(0.1)
        except Exception as e:
            self.emit_signal(0.0)
            findings.append({"type": "error", "message": str(e)})
        self.emit_signal(0.9 if findings else 0.1)
        return {"agent_type": "probe", "surface": surface, "attack_class": attack_class, "findings": findings, "anomalies_found": len(findings)}
