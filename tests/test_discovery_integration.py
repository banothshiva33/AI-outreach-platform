"""Integration tests for the full discovery pipeline."""

from unittest.mock import patch

import pytest

from app.discovery.types import ExtractedCompany, SearchResult
from app.repositories import agent_run_repository, lead_repository


SAMPLE_WEBSITE_HTML = """
<html>
<head>
  <meta name="description" content="FinBox is an AI lending platform for India.">
  <meta property="og:description" content="AI-powered lending infrastructure.">
</head>
<body>
  <a href="mailto:hello@finbox.co.in">Contact</a>
  <a href="tel:+919876543210">Call</a>
  <a href="https://linkedin.com/company/finbox-ai">LinkedIn</a>
  <a href="https://instagram.com/finboxai">Instagram</a>
  <a href="https://twitter.com/finboxai">Twitter</a>
  <p>Founder: Rahul Sharma</p>
  <p>Based in Bangalore, Karnataka</p>
</body>
</html>
"""

YOURSTORY_HTML = """
<html><body>
<article><h2>FinBox raises Series B funding</h2><p>FinBox is a Bangalore fintech startup.</p>
<a href="https://finbox.co.in">Website</a></article>
<article><h2>HealthifyMe launches new AI coach</h2><p>Health startup from Delhi.</p></article>
</body></html>
"""

INC42_HTML = """
<html><body>
<article><h2 class="entry-title">Razorpay secures $100M funding</h2><p>Payment gateway startup.</p></article>
<article><h2 class="entry-title">Zerodha launches new platform</h2><p>Bengaluru fintech.</p></article>
</body></html>
"""

STARTUP_INDIA_HTML = """
<html><body>
<div class="startup-card"><h3>AgriTech Ventures Pvt Ltd</h3><p>Agri startup from Pune.</p></div>
<div class="startup-card"><h3>HealthBridge Solutions</h3><p>HealthTech from Chennai.</p></div>
</body></html>
"""

MULTI_COMPANY_ARTICLE_HTML = """
<html>
<body>
    <article>
        <h1>Meet The Top 10 Indian Startup Investors Of H1 2026</h1>
        <p>This article mentions Alpha Robotics, Beta Health, and Gamma AI among others.</p>
    </article>
</body>
</html>
"""

MULTI_COMPANY_LLM_JSON = """
{
    "companies": [
        {
            "company_name": "Alpha Robotics Pvt Ltd",
            "description": "Robotics startup",
            "industry": "Robotics",
            "country": "India",
            "city": "Bangalore",
            "founder": "Amit Sharma",
            "website_if_present": "https://alpharobotics.in",
            "confidence": 0.96
        },
        {
            "company_name": "Beta Health Technologies",
            "description": "Healthtech startup",
            "industry": "HealthTech",
            "country": "India",
            "city": "Delhi",
            "founder": "Neha Gupta",
            "website_if_present": "https://betahealth.in",
            "confidence": 0.95
        },
        {
            "company_name": "Gamma AI Solutions Pvt Ltd",
            "description": "AI startup",
            "industry": "AI",
            "country": "India",
            "city": "Pune",
            "founder": "Rohan Mehta",
            "website_if_present": "https://gammaai.in",
            "confidence": 0.94
        }
    ]
}
"""


@patch("app.discovery.website_parser.is_safe_url", return_value=True)
@patch("app.discovery.website_parser.fetch_url")
@patch("app.discovery.website_enrichment.fetch_page_html")
@patch("app.discovery.article_engine.fetch_page_html")
@patch("app.plugins.base.plugin_registry.search")
@patch("app.plugins.base.plugin_registry.discover_directories")
def test_full_discovery_pipeline(
    mock_directories,
    mock_search,
    mock_article_fetch,
    mock_website_enrichment_fetch,
    mock_fetch,
    mock_safe,
    db,
    tmp_path,
):
    from app.core.config import settings
    from app.discovery.engine import DiscoveryEngine

    settings.EXPORT_DIR = str(tmp_path)

    mock_directories.return_value = [
        ExtractedCompany(
            name="FinBox",
            description="AI lending platform in Bangalore",
            source_url="https://yourstory.com/finbox",
            strategy="YOURSTORY",
            tags=["FinTech", "AI Startup"],
        )
    ]
    mock_search.return_value = [
        SearchResult(
            title="FinBox - Official Site",
            url="https://finbox.co.in",
            snippet="FinBox AI lending Bangalore",
            source="duckduckgo",
        )
    ]

    def fetch_side_effect(url):
        if "finbox.co.in" in url:
            return SAMPLE_WEBSITE_HTML
        if "yourstory.com" in url:
            return YOURSTORY_HTML
        return None

    mock_fetch.side_effect = fetch_side_effect
    mock_article_fetch.side_effect = fetch_side_effect
    mock_website_enrichment_fetch.side_effect = fetch_side_effect

    run = agent_run_repository.create_run(
        db,
        config={"max_keywords": 1, "results_per_keyword": 5, "resume": False},
    )
    engine = DiscoveryEngine(db, run.id)
    state = engine.run(max_keywords=1, results_per_keyword=5, resume=False, export_excel=True)

    assert state.leads_found >= 1
    assert state.keywords_processed >= 1

    leads = lead_repository.search_leads(db, query="FinBox")
    assert len(leads) >= 1
    lead = leads[0]
    assert lead.lead_score > 0
    assert lead.confidence_score > 0
    assert lead.website == "https://finbox.co.in"

    emails = [c.value for c in lead.contacts if c.type == "EMAIL"]
    assert "hello@finbox.co.in" in emails

    platforms = {s.platform for s in lead.social_links}
    assert "LINKEDIN" in platforms
    assert "INSTAGRAM" in platforms
    assert "TWITTER" in platforms

    assert state.export_file is not None
    import os
    assert os.path.exists(state.export_file)
    assert state.export_file.endswith(".xlsx")


@patch("app.plugins.connectors.yourstory.fetch_url")
def test_yourstory_connector(mock_fetch, db):
    from app.plugins.connectors.yourstory import YourStoryConnector

    mock_fetch.return_value = YOURSTORY_HTML
    connector = YourStoryConnector()
    companies = connector.discover("FinTech Bangalore", limit=5)

    assert len(companies) >= 1
    assert any("FinBox" in c.name for c in companies)
    assert companies[0].strategy == "YOURSTORY"


@patch("app.plugins.connectors.inc42.fetch_url")
def test_inc42_connector(mock_fetch, db):
    from app.plugins.connectors.inc42 import Inc42Connector

    mock_fetch.return_value = INC42_HTML
    connector = Inc42Connector()
    companies = connector.discover("Razorpay", limit=5)

    assert len(companies) >= 1
    assert any("Razorpay" in c.name for c in companies)
    assert companies[0].strategy == "INC42"


@patch("app.discovery.http_client.fetch_url")
def test_startup_india_connector(mock_fetch, db):
    from app.plugins.connectors.startup_india import StartupIndiaConnector

    mock_fetch.return_value = STARTUP_INDIA_HTML
    connector = StartupIndiaConnector()
    companies = connector.discover("AgriTech", limit=5)

    assert len(companies) >= 1
    assert companies[0].strategy == "STARTUP_INDIA"


@patch("app.discovery.website_parser.is_safe_url", return_value=True)
@patch("app.discovery.website_parser.fetch_url")
def test_website_parser_extracts_all_fields(mock_fetch, mock_safe):
    from app.discovery.website_parser import WebsiteParser

    mock_fetch.return_value = SAMPLE_WEBSITE_HTML
    parser = WebsiteParser()
    data = parser.parse("https://finbox.co.in")

    assert "hello@finbox.co.in" in data["emails"]
    assert len(data["phones"]) >= 1
    platforms = {s["platform"] for s in data["social_links"]}
    assert "LINKEDIN" in platforms
    assert "INSTAGRAM" in platforms
    assert "TWITTER" in platforms
    assert len(data["founders"]) >= 1


@patch("app.discovery.website_parser.is_safe_url", return_value=True)
@patch("app.discovery.website_parser.fetch_url")
@patch("app.discovery.website_enrichment.fetch_page_html")
@patch("app.discovery.article_engine.fetch_page_html")
@patch("app.discovery.ai_extractor.OpenAI")
@patch("app.plugins.base.plugin_registry.search")
@patch("app.plugins.base.plugin_registry.discover_directories")
def test_article_page_extracts_multiple_companies(
    mock_directories,
    mock_search,
    mock_openai,
    mock_article_fetch,
    mock_website_enrichment_fetch,
    mock_fetch,
    mock_safe,
    db,
):
    from types import SimpleNamespace

    from app.core.config import settings
    from app.discovery.engine import DiscoveryEngine

    original_key = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = "test-key"

    mock_directories.return_value = []
    mock_search.return_value = [
        SearchResult(
            title="Meet The Top 10 Indian Startup Investors Of H1 2026",
            url="https://example.com/article",
            snippet="Article about startup investors",
            source="mock",
        )
    ]

    mock_article_fetch.return_value = MULTI_COMPANY_ARTICLE_HTML
    mock_website_enrichment_fetch.return_value = SAMPLE_WEBSITE_HTML
    mock_fetch.return_value = SAMPLE_WEBSITE_HTML

    mock_openai.return_value.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=MULTI_COMPANY_LLM_JSON))]
    )

    try:
        run = agent_run_repository.create_run(
            db, config={"max_keywords": 1, "results_per_keyword": 5, "resume": False}
        )
        engine = DiscoveryEngine(db, run.id)
        state = engine.run(max_keywords=1, results_per_keyword=5, resume=False, export_excel=False)

        leads = lead_repository.search_leads(db, query="Alpha Robotics")
        assert len(leads) == 1
        assert state.leads_found >= 3

        all_multi_leads = lead_repository.search_leads(db, query="", limit=10)
        company_names = {lead.name for lead in all_multi_leads}
        assert "Alpha Robotics Pvt Ltd" in company_names
        assert "Beta Health Technologies" in company_names
        assert "Gamma AI Solutions Pvt Ltd" in company_names
        assert "Meet The Top 10 Indian Startup Investors Of H1 2026" not in company_names
    finally:
        settings.OPENAI_API_KEY = original_key


def test_validator_rejects_junk():
    from app.discovery.types import ExtractedCompany
    from app.discovery.validator import CompanyValidator

    validator = CompanyValidator()
    assert validator.validate_extracted(ExtractedCompany(name="Home")) is False
    assert validator.validate_extracted(
        ExtractedCompany(name="Real Startup Pvt Ltd", website="https://real.co")
    ) is True


@patch("app.discovery.website_parser.fetch_url")
@patch("app.discovery.website_enrichment.fetch_page_html")
@patch("app.discovery.article_engine.fetch_page_html")
@patch("app.plugins.base.plugin_registry.search")
@patch("app.plugins.base.plugin_registry.discover_directories")
def test_duplicate_companies_skipped(
    mock_directories,
    mock_search,
    mock_article_fetch,
    mock_website_enrichment_fetch,
    mock_fetch,
    db,
):
    from app.discovery.engine import DiscoveryEngine

    mock_directories.return_value = []
    mock_fetch.return_value = None
    mock_search.return_value = [
        SearchResult(
            title="DupCo Technologies",
            url="https://dupco.co.in",
            snippet="A startup",
            source="duckduckgo",
        ),
        SearchResult(
            title="DupCo Technologies Pvt Ltd",
            url="https://dupco.co.in/about",
            snippet="Same startup",
            source="duckduckgo",
        ),
    ]

    dupco_html = """
    <html>
        <head>
            <meta property="og:title" content="DupCo Technologies" />
            <meta name="description" content="DupCo Technologies is a startup." />
        </head>
        <body>
            <article>
                <h1>DupCo Technologies</h1>
                <p>DupCo Technologies is a startup.</p>
            </article>
        </body>
    </html>
    """

    mock_article_fetch.side_effect = lambda url: dupco_html
    mock_website_enrichment_fetch.side_effect = lambda url: dupco_html

    run = agent_run_repository.create_run(
        db, config={"max_keywords": 1, "results_per_keyword": 5, "resume": False}
    )
    engine = DiscoveryEngine(db, run.id)
    state = engine.run(
        max_keywords=1, results_per_keyword=5, resume=False, export_excel=False
    )

    leads = lead_repository.search_leads(db, query="DupCo")
    assert len(leads) == 1
    assert state.duplicates_skipped >= 0
