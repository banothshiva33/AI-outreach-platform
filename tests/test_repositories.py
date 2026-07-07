from unittest.mock import MagicMock, patch

import pytest

from app.discovery.types import SearchResult
from app.repositories import (
    lead_repository,
    search_history_repository,
    exclude_memory_repository,
    category_repository,
)
from app.schemas import LeadCreate, ContactSchema, SocialLinkSchema


def test_create_and_search_lead(db):
    payload = LeadCreate(
        name="Test Startup Pvt Ltd",
        website="https://teststartup.com",
        description="An AI startup in Bangalore",
        city="Bangalore",
        state="Karnataka",
        country="India",
        lead_score=75,
        confidence_score=0.8,
        categories=["AI Startup", "SaaS"],
        contacts=[ContactSchema(type="EMAIL", value="hello@teststartup.com")],
        social_links=[
            SocialLinkSchema(
                platform="LINKEDIN",
                url="https://linkedin.com/company/teststartup",
            )
        ],
    )
    company = lead_repository.create_or_update_lead(
        db,
        company_data=payload.model_dump(
            exclude={"categories", "contacts", "social_links", "profiles", "sources"}
        ),
        categories=payload.categories,
        contacts=[c.model_dump() for c in payload.contacts],
        social_links=[s.model_dump() for s in payload.social_links],
    )
    assert company.id is not None
    assert company.name == "Test Startup Pvt Ltd"

    results = lead_repository.search_leads(db, query="Test Startup", city="Bangalore")
    assert len(results) >= 1
    assert results[0].lead_score == 75


def test_lead_deduplication_by_website(db):
    lead_repository.create_or_update_lead(
        db,
        company_data={"name": "Company A", "website": "https://dedup-test.com"},
    )
    updated = lead_repository.create_or_update_lead(
        db,
        company_data={
            "name": "Company A Updated",
            "website": "https://dedup-test.com",
            "lead_score": 90,
        },
    )
    assert updated.name == "Company A Updated"
    assert updated.lead_score == 90


def test_search_history_memory(db):
    search_history_repository.mark_searched(db, keyword="AI Startup Bangalore")
    assert search_history_repository.is_processed(db, "AI Startup Bangalore")

    search_history_repository.mark_searched(
        db, keyword="failed keyword", status="FAILED", error_message="timeout"
    )
    assert not search_history_repository.is_processed(db, "failed keyword")


def test_exclude_memory(db):
    exclude_memory_repository.add_exclusion(
        db, entity_type="URL", entity_value="https://dead-site.com", reason="DEAD_URL"
    )
    assert exclude_memory_repository.is_excluded(db, "URL", "https://dead-site.com")


def test_category_repository(db):
    cat = category_repository.get_or_create(db, "FinTech")
    assert cat.name == "FinTech"
    same = category_repository.get_or_create(db, "FinTech")
    assert cat.id == same.id


def test_lead_scorer():
    from app.discovery.scorer import LeadScorer
    from app.discovery.types import EnrichedLead

    scorer = LeadScorer()
    lead = EnrichedLead(
        name="Acme AI",
        website="https://acme.ai",
        description="AI platform for enterprises in India",
        city="Bangalore",
        state="Karnataka",
        country="India",
        categories=["AI Startup"],
        contacts=[{"type": "EMAIL", "value": "info@acme.ai"}],
        social_links=[{"platform": "LINKEDIN", "url": "https://linkedin.com/company/acme"}],
        profiles=[{"name": "Jane Doe", "title": "Founder"}],
        sources=[{"url": "https://example.com", "strategy": "WEB_SEARCH", "reliability_score": 50}],
    )
    scored = scorer.score(lead)
    assert scored.lead_score > 50
    assert scored.confidence_score > 0.5


def test_keyword_generator(db):
    from app.discovery.keyword_generator import KeywordGenerator

    gen = KeywordGenerator(db)
    keywords = gen.generate_all(max_keywords=20)
    assert len(keywords) == 20
    assert any("Startup" in kw or "startup" in kw.lower() for kw in keywords)


@patch("app.discovery.website_parser.fetch_url")
@patch("app.discovery.website_enrichment.fetch_page_html")
@patch("app.discovery.article_engine.fetch_page_html")
@patch("app.plugins.base.plugin_registry.search")
@patch("app.plugins.base.plugin_registry.discover_directories")
def test_discovery_engine_with_mock_search(
    mock_directories,
    mock_search,
    mock_article_fetch,
    mock_website_enrichment_fetch,
    mock_fetch,
    db,
):
    from app.discovery.engine import DiscoveryEngine
    from app.repositories import agent_run_repository

    mock_directories.return_value = []
    mock_fetch.return_value = None
    mock_search.return_value = [
        SearchResult(
            title="InnovateTech Solutions Pvt Ltd - AI Startup",
            url="https://innovatetech.co.in",
            snippet="InnovateTech is an AI startup based in Bangalore.",
            source="mock",
        )
    ]

    html = """
    <html>
        <head>
            <meta property="og:title" content="InnovateTech Solutions Pvt Ltd" />
            <meta name="description" content="InnovateTech is an AI startup based in Bangalore." />
        </head>
        <body>
            <article>
                <h1>InnovateTech Solutions Pvt Ltd</h1>
                <p>InnovateTech is an AI startup based in Bangalore.</p>
            </article>
        </body>
    </html>
    """
    mock_article_fetch.side_effect = lambda url: html
    mock_website_enrichment_fetch.side_effect = lambda url: html

    run = agent_run_repository.create_run(
        db, config={"max_keywords": 1, "results_per_keyword": 5, "resume": False}
    )
    engine = DiscoveryEngine(db, run.id)
    state = engine.run(max_keywords=1, results_per_keyword=5, resume=False, export_excel=False)

    assert state.keywords_processed >= 1
    leads = lead_repository.search_leads(db, query="InnovateTech")
    assert len(leads) >= 1
