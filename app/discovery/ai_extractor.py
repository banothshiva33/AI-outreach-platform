import json
import logging
import re
from typing import Any, Dict, List, Optional

from openai import OpenAI

from app.core.config import settings
from app.discovery.article_engine import ArticleDocument, ArticleUnderstandingEngine
from app.discovery.types import ExtractedCompany, StartupMention

logger = logging.getLogger(__name__)


TITLE_RE = re.compile(
    r"\b(top|best|guide|how to|news|report|analysis|review|market|ranking|list|blog|magazine|conference)\b",
    re.I,
)

LEGAL_SUFFIX_RE = re.compile(
    r"^(.+?\b(?:Pvt\.?\s*Ltd\.?|Private Limited|LLP|Inc\.?|Corp\.?))\b",
    re.I,
)


class AIExtractionAgent:
    """Uses an LLM first, then deterministic extraction, to turn article text into startup mentions."""

    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self.article_engine = ArticleUnderstandingEngine()

    def extract_from_url(self, url: str, *, html: Optional[str] = None) -> List[ExtractedCompany]:
        document = self.article_engine.load(url, html=html)
        if not document or not document.body_text:
            return []

        raw_mentions = self._extract_mentions(document)
        companies = [self._to_company(mention, document) for mention in raw_mentions]
        logger.info(
            json.dumps(
                {
                    "stage": "ai_extractor",
                    "event": "companies_extracted",
                    "article_url": document.url,
                    "article_title": document.title,
                    "article_body_length": len(document.body_text),
                    "raw_article_text": document.body_text,
                    "llm_prompt": self._build_prompt(),
                    "llm_article_text": document.body_text[:18000],
                    "llm_request_size": len(document.body_text[:18000]),
                    "exact_llm_input": getattr(self, "_last_llm_input", None),
                    "llm_error": getattr(self, "_last_llm_error", None),
                    "raw_llm_response": getattr(self, "_last_raw_llm_response", None),
                    "parsed_json": [self._mention_to_trace_payload(mention) for mention in raw_mentions],
                    "parsed_companies": [
                        {
                            "name": company.name,
                            "website": company.website,
                            "industry": company.industry,
                            "country": company.country,
                            "city": company.location,
                            "founder": company.founder,
                            "confidence": company.confidence,
                            "entity_type": company.entity_type,
                            "occurrence_count": company.occurrence_count,
                        }
                        for company in companies
                    ],
                    "number_of_companies": len(companies),
                }
            ),
        )
        return self._dedupe(companies)

    def _build_prompt(self) -> str:
        return (
            "Extract every startup mentioned in the article. Do not summarize. Do not return the article title. "
            "Return STRICT JSON with exactly one top-level key named companies. Its value must be an array of "
            "objects with keys company_name, founder, website_if_present, email, phone, linkedin, instagram, twitter, "
            "location, country, industry, description, funding, employee_size, confidence, entity_type, occurrence_count. "
            "If website is missing, set it to null."
        )

    def _extract_mentions(self, document: ArticleDocument) -> List[StartupMention]:
        llm_mentions = self._extract_with_llm(document)
        if llm_mentions:
            return llm_mentions
        return self._heuristic_mentions(document)

    def _extract_with_llm(self, document: ArticleDocument) -> List[StartupMention]:
        if not settings.OPENAI_API_KEY:
            self._last_llm_input = None
            self._last_raw_llm_response = None
            self._last_llm_error = "OPENAI_API_KEY is not configured"
            return []

        prompt = self._build_prompt()
        user_content = {
            "url": document.url,
            "article_text": document.body_text[:18000],
        }
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
        ]
        self._last_llm_input = {
            "model": self.model,
            "temperature": 0,
            "messages": messages,
        }
        self._last_raw_llm_response = None
        self._last_llm_error = None

        try:
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            response = client.chat.completions.create(
                model=self.model,
                temperature=0,
                messages=messages,
            )
            content = response.choices[0].message.content or "{}"
            self._last_raw_llm_response = content
            payload = self._parse_json(content)
            return [self._mention_from_payload(item, document.url, document.body_text) for item in payload]
        except Exception as exc:
            self._last_llm_error = str(exc)
            logger.debug("LLM extraction failed for %s: %s", document.url, exc)
            return []

    def _parse_json(self, content: str) -> List[Dict[str, Any]]:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.I | re.S).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\[[\s\S]*\]", text)
            if not match:
                match = re.search(r"\{[\s\S]*\}", text)
                if not match:
                    return []
                data = json.loads(match.group(0))
            else:
                data = json.loads(match.group(0))
        if isinstance(data, dict):
            companies = data.get("companies", [])
            return companies if isinstance(companies, list) else []
        return data if isinstance(data, list) else [data]

    def _mention_from_payload(self, payload: Dict[str, Any], source_url: str, article_text: str) -> StartupMention:
        company_name = str(payload.get("company_name") or payload.get("company") or "").strip()
        return StartupMention(
            company_name=company_name,
            article_context=self._clean_optional(payload.get("article_context") or payload.get("context")) or self._context_for_candidate(company_name, article_text),
            occurrence_count=self._parse_occurrence_count(payload.get("occurrence_count"), company_name, article_text),
            entity_type=self._clean_optional(payload.get("entity_type") or payload.get("type")),
            founder=self._clean_optional(payload.get("founder")),
            email=self._clean_optional(payload.get("email")),
            phone=self._clean_optional(payload.get("phone")),
            linkedin=self._clean_optional(payload.get("linkedin")),
            instagram=self._clean_optional(payload.get("instagram")),
            twitter=self._clean_optional(payload.get("twitter")),
            location=self._clean_optional(payload.get("location")),
            country=self._clean_optional(payload.get("country")),
            industry=self._clean_optional(payload.get("industry")),
            website_if_present=self._clean_optional(payload.get("website_if_present") or payload.get("website")),
            description=self._clean_optional(payload.get("description")),
            funding=self._clean_optional(payload.get("funding")),
            employee_size=self._clean_optional(payload.get("employee_size")),
            confidence=self._parse_confidence(payload.get("confidence")),
            source_url=source_url,
        )

    def _heuristic_mentions(self, document: ArticleDocument) -> List[StartupMention]:
        text = document.body_text
        candidates: List[str] = []
        patterns = [
            r"\b([A-Z][A-Za-z0-9&]+(?:\s+[A-Z][A-Za-z0-9&]+){0,4}(?:Pvt\.?\s*Ltd\.?|Private Limited|LLP|Inc\.?|Technologies|Solutions|Labs|Ventures)?)\b",
            r"\b([A-Z][A-Za-z0-9&]+(?:\s+[A-Z][A-Za-z0-9&]+){1,4})\b",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                candidate = self._normalize_candidate(match.group(1))
                if candidate and candidate not in candidates:
                    candidates.append(candidate)

        mentions: List[StartupMention] = []
        for candidate in candidates:
            if TITLE_RE.search(candidate):
                continue
            if not self._looks_like_business_entity(candidate):
                continue
            if not self._looks_like_company(candidate):
                continue
            context = self._context_for_candidate(candidate, document.body_text)
            mentions.append(
                StartupMention(
                    company_name=candidate,
                    article_context=context,
                    occurrence_count=self._parse_occurrence_count(None, candidate, document.body_text),
                    entity_type=self._infer_entity_type(candidate, context),
                    founder=self._extract_field(r"(?:Founder|Co-founder|CEO|Managing Director)[:\s]+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})", context),
                    industry=self._extract_field(r"(?:industry|sector|category)[:\s]+([A-Za-z0-9 &/-]{3,60})", context),
                    website_if_present=self._extract_field(r"https?://[^\s\"]+", context),
                    description=context[:300].strip() or None,
                    source_url=document.url,
                )
            )
            if len(mentions) >= 30:
                break
        return mentions

    def _mention_to_trace_payload(self, mention: StartupMention) -> Dict[str, Any]:
        return {
            "company_name": mention.company_name,
            "article_context": mention.article_context,
            "occurrence_count": mention.occurrence_count,
            "entity_type": mention.entity_type,
            "founder": mention.founder,
            "email": mention.email,
            "phone": mention.phone,
            "linkedin": mention.linkedin,
            "instagram": mention.instagram,
            "twitter": mention.twitter,
            "location": mention.location,
            "country": mention.country,
            "industry": mention.industry,
            "website_if_present": mention.website_if_present,
            "description": mention.description,
            "funding": mention.funding,
            "employee_size": mention.employee_size,
            "confidence": mention.confidence,
            "source_url": mention.source_url,
        }

    def _to_company(self, mention: StartupMention, document: ArticleDocument) -> ExtractedCompany:
        description = mention.description or document.body_text[:500]
        website = mention.website_if_present if self._looks_like_website(mention.website_if_present) else None
        confidence = mention.confidence or (0.75 if website else 0.45)
        social_links = []
        if mention.linkedin:
            social_links.append({"platform": "LINKEDIN", "url": mention.linkedin})
        if mention.instagram:
            social_links.append({"platform": "INSTAGRAM", "url": mention.instagram})
        if mention.twitter:
            social_links.append({"platform": "TWITTER", "url": mention.twitter})
        return ExtractedCompany(
            name=mention.company_name,
            website=website,
            description=description,
            article_context=mention.article_context,
            occurrence_count=mention.occurrence_count,
            entity_type=mention.entity_type,
            founder=mention.founder,
            industry=mention.industry,
            email=mention.email,
            phone=mention.phone,
            location=mention.location,
            country=mention.country,
            funding=mention.funding,
            employee_size=mention.employee_size,
            source_url=document.url,
            source_urls=[document.url],
            confidence=confidence,
            social_links=social_links,
            strategy="ARTICLE_AI",
        )

    def _dedupe(self, companies: List[ExtractedCompany]) -> List[ExtractedCompany]:
        seen = set()
        unique: List[ExtractedCompany] = []
        for company in companies:
            key = company.name.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(company)
        return unique

    def _normalize_candidate(self, candidate: str) -> str:
        candidate = re.sub(r"\s+", " ", candidate).strip(" ,;:.-")
        legal_suffix_match = LEGAL_SUFFIX_RE.match(candidate)
        if legal_suffix_match:
            candidate = legal_suffix_match.group(1)
        candidate = candidate.replace("  ", " ")
        return candidate

    def _looks_like_company(self, candidate: str) -> bool:
        words = candidate.split()
        if not (2 <= len(words) <= 12):
            return False
        if re.search(r"[|/\\]", candidate):
            return False
        if len(candidate) > 100:
            return False
        return any(token[0].isupper() for token in words if token)

    def _looks_like_business_entity(self, candidate: str) -> bool:
        lowered = candidate.lower().strip()
        reject_terms = (
            "article",
            "startup investors",
            "top",
            "best",
            "guide",
            "news",
            "report",
            "analysis",
            "review",
            "blog",
            "magazine",
            "conference",
            "event",
            "how to",
            "what is",
        )
        if any(term in lowered for term in reject_terms):
            return False
        if candidate.endswith("?"):
            return False
        if len(candidate.split()) > 12:
            return False
        return True

    def _infer_entity_type(self, candidate: str, context: str) -> Optional[str]:
        combined = f"{candidate} {context}".lower()
        if any(term in combined for term in ("team", "department", "committee")):
            return "TEAM"
        if any(term in combined for term in ("program", "initiative", "scheme")):
            return "PROGRAM"
        if any(term in combined for term in ("department", "division", "office")):
            return "DEPARTMENT"
        if any(term in combined for term in ("initiative", "campaign")):
            return "INITIATIVE"
        return None

    def _context_for_candidate(self, candidate: str, text: str) -> str:
        index = text.lower().find(candidate.lower())
        if index < 0:
            return text[:500]
        start = max(index - 180, 0)
        end = min(index + 320, len(text))
        return text[start:end]

    def _extract_field(self, pattern: str, text: str) -> Optional[str]:
        match = re.search(pattern, text, flags=re.I)
        if not match:
            return None
        value = match.group(1) if match.lastindex else match.group(0)
        value = value.strip().strip(".,;:")
        return value or None

    def _looks_like_website(self, value: Optional[str]) -> bool:
        return bool(value and value.startswith("http"))

    def _clean_optional(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _parse_occurrence_count(self, value: Any, candidate: str, text: str) -> int:
        try:
            parsed = int(value)
            if parsed >= 0:
                return parsed
        except (TypeError, ValueError):
            pass
        pattern = re.compile(rf"\b{re.escape(candidate)}\b", re.I)
        return len(pattern.findall(text))

    def _parse_confidence(self, value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.0
        if confidence < 0:
            return 0.0
        if confidence > 1:
            return 1.0
        return round(confidence, 2)
