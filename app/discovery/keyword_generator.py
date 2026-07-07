import itertools
import json
import logging
from typing import Generator, Iterable, List, Optional, Set

from sqlalchemy.orm import Session

from app.models.models import SearchHistory
from app.repositories import search_history_repository

logger = logging.getLogger(__name__)

CITIES = [
    "Bangalore", "Mumbai", "Delhi", "Hyderabad", "Chennai", "Pune", "Kolkata",
    "Ahmedabad", "Jaipur", "Kochi", "Indore", "Noida", "Gurgaon", "Chandigarh",
    "Lucknow", "Bhopal", "Coimbatore", "Vizag", "Nagpur", "Surat",
]

STATES = [
    "Karnataka", "Maharashtra", "Telangana", "Tamil Nadu", "Delhi", "Gujarat",
    "Rajasthan", "Kerala", "Uttar Pradesh", "West Bengal", "Punjab", "Haryana",
]

INDUSTRIES = [
    "Startup", "AI Startup", "FinTech", "EdTech", "HealthTech", "SaaS",
    "DeepTech", "AgriTech", "PropTech", "D2C", "E-commerce", "Cybersecurity",
    "Blockchain", "Marketing Agency", "Product Company", "Tech Company",
    "Manufacturing Startup", "Innovation Lab", "Recruitment Company", "HR Company",
]

FOUNDER_ROLES = [
    "Founder", "Co-founder", "CEO", "Women Founder", "Tech Founder",
    "Serial Entrepreneur", "First-time Founder",
]

BUSINESS_TYPES = [
    "Startup India", "Business News", "Startup News", "Accelerator",
    "Incubator", "Angel Investor", "VC", "Business Coach", "Business Mentor",
]

TECH_DOMAINS = [
    "AI", "Machine Learning", "Cloud", "IoT", "Robotics", "Data Analytics",
    "Generative AI", "LLM", "Automation", "DevTools",
]


class KeywordGenerator:
    """
    Autonomously generates thousands of keyword combinations for discovery.
    Remembers processed keywords via SearchHistory to avoid duplicate work.
    """

    def __init__(self, db: Session):
        self.db = db
        self._seen: Set[str] = set()
        self._processed_cache: Set[str] = set()

    def _normalize(self, keyword: str) -> str:
        return " ".join(keyword.strip().split()).lower()

    def _is_known(self, keyword: str) -> bool:
        normalized = self._normalize(keyword)
        if normalized in self._seen:
            return True
        if normalized in self._processed_cache:
            return True
        return False

    def _load_processed_cache(self, keywords: Iterable[str]) -> None:
        batch = [self._normalize(kw) for kw in keywords]
        processed = search_history_repository.get_processed_keywords(self.db, batch)
        self._processed_cache.update(processed)

    def _yield_unique(self, keywords: Iterable[str]) -> Generator[str, None, None]:
        for kw in keywords:
            normalized = self._normalize(kw)
            if not normalized or normalized in self._seen:
                continue
            if self._is_known(normalized):
                self._seen.add(normalized)
                continue
            self._seen.add(normalized)
            yield kw.strip()

    def generate_base_keywords(self) -> Generator[str, None, None]:
        """Single-dimension keywords."""
        yield from self._yield_unique(INDUSTRIES)
        yield from self._yield_unique(BUSINESS_TYPES)
        yield from self._yield_unique([f"Startup {city}" for city in CITIES])
        yield from self._yield_unique([f"Startup {state}" for state in STATES])
        yield from self._yield_unique(
            [f"{role} {city}" for role in FOUNDER_ROLES for city in CITIES[:10]]
        )

    def generate_two_word_combos(self) -> Generator[str, None, None]:
        """Industry + City, Business Type + City, etc."""
        for industry, city in itertools.product(INDUSTRIES, CITIES):
            yield from self._yield_unique(f"{industry} {city}")

        for biz, city in itertools.product(BUSINESS_TYPES, CITIES):
            yield from self._yield_unique(f"{biz} {city}")

        for role, city in itertools.product(FOUNDER_ROLES, CITIES):
            yield from self._yield_unique(f"{role} {city}")

    def generate_three_word_combos(self) -> Generator[str, None, None]:
        """Tech + Industry + City combinations."""
        for tech, industry, city in itertools.product(
            TECH_DOMAINS, INDUSTRIES[:12], CITIES[:12]
        ):
            yield from self._yield_unique(f"{tech} {industry} {city}")

        for industry, city, state in itertools.product(
            INDUSTRIES[:10], CITIES[:8], STATES[:6]
        ):
            yield from self._yield_unique(f"{industry} {city} {state}")

    def generate_all(self, *, max_keywords: Optional[int] = None) -> List[str]:
        completed = (
            self.db.query(SearchHistory.keyword)
            .filter(SearchHistory.status == "COMPLETED")
            .all()
        )
        self._processed_cache = {row[0] for row in completed}
        generators = [
            self.generate_base_keywords,
            self.generate_two_word_combos,
            self.generate_three_word_combos,
        ]
        results: List[str] = []
        for gen_fn in generators:
            for kw in gen_fn():
                results.append(kw)
                if max_keywords and len(results) >= max_keywords:
                    return results
        return results

    def queue_pending(self, keywords: List[str]) -> int:
        """Persist keywords as PENDING in search_history for checkpointing."""
        queued = 0
        for kw in keywords:
            normalized = self._normalize(kw)
            existing = search_history_repository.get_by_keyword(self.db, normalized)
            if not existing:
                record = SearchHistory(keyword=normalized, status="PENDING")
                self.db.add(record)
                queued += 1
        self.db.commit()
        return queued

    def get_next_batch(
        self, *, limit: int = 50, after_keyword: Optional[str] = None
    ) -> List[str]:
        pending = search_history_repository.get_pending_keywords(
            self.db, limit=limit, after_keyword=after_keyword
        )
        return [p.keyword for p in pending]
