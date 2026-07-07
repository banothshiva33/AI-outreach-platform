from app.discovery.types import EnrichedLead


class LeadScorer:
    """Computes lead score, confidence score, and source reliability."""

    def score(self, lead: EnrichedLead) -> EnrichedLead:
        lead.lead_score = self._compute_lead_score(lead)
        lead.confidence_score = self._compute_confidence_score(lead)
        for source in lead.sources:
            source["reliability_score"] = self._compute_source_reliability(source, lead)
        return lead

    def _compute_lead_score(self, lead: EnrichedLead) -> int:
        score = 0
        if lead.website:
            score += 20
        if any(s["platform"] == "LINKEDIN" for s in lead.social_links):
            score += 15
        if any(s["platform"] == "INSTAGRAM" for s in lead.social_links):
            score += 10
        if any(c["type"] == "EMAIL" for c in lead.contacts):
            score += 20
        if any(c["type"] == "PHONE" for c in lead.contacts):
            score += 15
        if lead.profiles:
            score += 10
        if lead.city or lead.state or lead.country:
            score += 5
        if lead.funding_stage:
            score += 5
        if lead.sources and any(src.get("strategy") == "STARTUP_INDIA" for src in lead.sources):
            score += 10
        if lead.company_size:
            score += 5

        return min(score, 100)

    def _compute_confidence_score(self, lead: EnrichedLead) -> float:
        weighted_signals = 0.0
        total = 8.0

        if lead.website:
            weighted_signals += 1.0
        if any(s["platform"] == "LINKEDIN" for s in lead.social_links):
            weighted_signals += 1.0
        if any(s["platform"] == "INSTAGRAM" for s in lead.social_links):
            weighted_signals += 0.5
        if any(c["type"] == "EMAIL" for c in lead.contacts):
            weighted_signals += 1.0
        if any(c["type"] == "PHONE" for c in lead.contacts):
            weighted_signals += 0.5
        if lead.profiles:
            weighted_signals += 1.0
        if lead.city or lead.state or lead.country:
            weighted_signals += 0.5
        if lead.description and len(lead.description) > 40:
            weighted_signals += 1.0
        if lead.funding_stage:
            weighted_signals += 0.5
        if lead.company_size:
            weighted_signals += 0.5

        if lead.sources and any(src.get("strategy") == "STARTUP_INDIA" for src in lead.sources):
            weighted_signals += 1.0

        return round(min(weighted_signals / total, 1.0), 2)

    def _compute_source_reliability(
        self, source: dict, lead: EnrichedLead
    ) -> int:
        base = source.get("reliability_score", 50)
        strategy = source.get("strategy", "")

        if strategy == "WEB_SEARCH" and lead.website:
            base += 15
        elif strategy in ("STARTUP_INDIA", "YOURSTORY", "INC42"):
            base += 20
        elif strategy == "GOOGLE_SEARCH":
            base += 10
        elif strategy == "DIRECTORY":
            base += 5

        if lead.confidence_score >= 0.7:
            base += 10
        elif lead.confidence_score >= 0.4:
            base += 5

        return min(base, 100)
