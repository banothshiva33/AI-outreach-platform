import pytest

from app.core.url_utils import is_safe_url, normalize_website


def test_normalize_website():
    assert normalize_website("https://WWW.Example.com/") == "https://example.com"
    assert normalize_website("example.com") == "https://example.com"


def test_block_private_urls():
    assert is_safe_url("http://127.0.0.1/admin") is False
    assert is_safe_url("http://localhost/internal") is False


def test_allow_public_urls():
    assert is_safe_url("https://example.com") is True


def test_search_leads_distinct_with_multiple_contacts(db):
    from app.repositories import lead_repository

    company = lead_repository.create_or_update_lead(
        db,
        company_data={"name": "Multi Contact Co", "website": "https://multico.example.com"},
        contacts=[
            {"type": "EMAIL", "value": "a@multico.example.com"},
            {"type": "EMAIL", "value": "b@multico.example.com"},
        ],
    )
    results = lead_repository.search_leads(
        db, only_with_email=True, query="Multi Contact"
    )
    assert len(results) == 1
    assert results[0].id == company.id


def test_contact_scoped_to_company(db):
    from app.repositories import lead_repository

    lead_repository.create_or_update_lead(
        db,
        company_data={"name": "Company One", "website": "https://one.example.com"},
        contacts=[{"type": "EMAIL", "value": "shared@example.com"}],
    )
    second = lead_repository.create_or_update_lead(
        db,
        company_data={"name": "Company Two", "website": "https://two.example.com"},
        contacts=[{"type": "EMAIL", "value": "shared@example.com"}],
    )
    assert any(contact.value == "shared@example.com" for contact in second.contacts)
