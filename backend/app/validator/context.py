# backend/app/validator/context.py
from urllib.parse import urlparse

FALSE_POSITIVE_PATTERNS = {
    "xss": ["alert(1) in non-reflected context", "CSP blocks execution"],
    "sqli": ["input sanitized before query", "ORM parameterized"],
}


class ContextChecker:
    async def check(self, finding: dict, scope: list[str], out_of_scope: list[str]) -> dict:
        surface = finding.get("affected_surface", "")
        vuln_class = finding.get("vulnerability_class", "")

        in_scope = False
        if scope:
            try:
                parsed = urlparse(surface if surface.startswith("http") else f"https://{surface}")
                hostname = parsed.hostname or ""
                in_scope = any(
                    hostname == s or hostname.endswith(f".{s}") for s in scope
                )
            except Exception:
                in_scope = False
        else:
            in_scope = True

        for oos in out_of_scope:
            if oos in surface:
                in_scope = False
                break

        is_known_false_positive = False
        description = finding.get("description", "").lower()
        for pattern in FALSE_POSITIVE_PATTERNS.get(vuln_class, []):
            if pattern.lower() in description:
                is_known_false_positive = True
                break

        return {
            "in_scope": in_scope,
            "is_known_false_positive": is_known_false_positive,
            "surface": surface,
        }
