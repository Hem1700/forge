# backend/app/validator/scorer.py
from dataclasses import dataclass
from app.config import settings


@dataclass
class ConfidenceScorer:
    threshold: float = None

    def __post_init__(self):
        if self.threshold is None:
            self.threshold = settings.confidence_threshold

    def score(
        self,
        challenger_result: dict,
        context_result: dict,
        severity_result: dict,
    ) -> dict:
        if not context_result.get("in_scope", True):
            return {"final_score": 0.0, "passes_gate": False, "reason": "out_of_scope"}
        if context_result.get("is_known_false_positive", False):
            return {"final_score": 0.0, "passes_gate": False, "reason": "known_false_positive"}
        if not challenger_result.get("reproduced", False):
            return {"final_score": challenger_result.get("confidence", 0.0) * 0.3, "passes_gate": False, "reason": "not_reproduced"}

        challenger_score = challenger_result.get("confidence", 0.0)
        severity_boost = {
            "critical": 0.1, "high": 0.05, "medium": 0.0, "low": -0.05, "info": -0.1
        }.get(severity_result.get("severity", "medium"), 0.0)

        final_score = min(1.0, challenger_score + severity_boost)
        passes_gate = final_score >= self.threshold

        return {
            "final_score": round(final_score, 3),
            "passes_gate": passes_gate,
            "reason": "passed" if passes_gate else f"score_{final_score:.2f}_below_threshold_{self.threshold}",
            "severity": severity_result.get("severity"),
            "cvss_score": severity_result.get("cvss_score"),
            "business_impact": severity_result.get("business_impact"),
        }
