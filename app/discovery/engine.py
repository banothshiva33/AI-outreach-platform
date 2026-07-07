import logging
import os
import json
from collections import deque
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.discovery.checkpoint import CheckpointManager, CheckpointState
from app.discovery.ai_extractor import AIExtractionAgent
from app.discovery.article_engine import ArticleUnderstandingEngine
from app.discovery.enricher import LeadEnricher
from app.discovery.keyword_generator import KeywordGenerator
from app.discovery.memory import AgentMemory
from app.discovery.scorer import LeadScorer
from app.discovery.types import EnrichedLead, ExtractedCompany
from app.discovery.validator import CompanyValidator
from app.discovery.website_finder import WebsiteFinder
from app.plugins.base import plugin_registry
import app.plugins  # noqa: F401
from app.repositories import agent_run_repository, lead_repository
from app.services.export_service import ExportService

logger = logging.getLogger(__name__)


class DiscoveryEngine:
    """
    Full discovery pipeline:
    Keywords → Connectors → Extract → Website Discovery → Validate →
    Enrich → Social → Score → Save → Checkpoint → Excel Export
    """

    def __init__(self, db: Session, run_id: UUID):
        self.db = db
        self.run_id = run_id
        self.keyword_gen = KeywordGenerator(db)
        self.article_engine = ArticleUnderstandingEngine()
        self.extractor = AIExtractionAgent()
        self.enricher = LeadEnricher()
        self.scorer = LeadScorer()
        self.validator = CompanyValidator()
        self.website_finder = WebsiteFinder()
        self.memory = AgentMemory(db)
        self.checkpoint_mgr = CheckpointManager(db, run_id)
        self.export_service = ExportService(export_dir=settings.EXPORT_DIR)
        self._pending_logs: list[tuple[str, str, str]] = []

    def run(
        self,
        *,
        max_keywords: int = 50,
        results_per_keyword: int = 10,
        resume: bool = True,
        export_excel: bool = True,
    ) -> CheckpointState:
        run = agent_run_repository.get(self.db, self.run_id)
        if not run:
            raise ValueError(f"Agent run {self.run_id} not found")

        state = (
            self.checkpoint_mgr.load()
            if resume
            else CheckpointState(run_id=str(self.run_id))
        )

        self._log("INFO", "discovery.engine", f"Starting discovery run {self.run_id}")
        self._trace(
            "engine_start",
            run_id=str(self.run_id),
            max_keywords=max_keywords,
            results_per_keyword=results_per_keyword,
            resume=resume,
        )

        keywords = self.keyword_gen.get_next_batch(
            limit=max_keywords, after_keyword=state.last_keyword if resume else None
        )
        if not keywords:
            new_keywords = self.keyword_gen.generate_all(max_keywords=max_keywords)
            self.keyword_gen.queue_pending(new_keywords)
            keywords = self.keyword_gen.get_next_batch(limit=max_keywords)

        for keyword in keywords:
            run = agent_run_repository.get(self.db, self.run_id)
            if run and run.status == "PAUSED":
                self._flush_logs()
                self.checkpoint_mgr.save(state)
                self._log("INFO", "discovery.engine", "Run paused, saving checkpoint")
                self._flush_logs()
                self.db.commit()
                return state

            if self.memory.is_keyword_processed(keyword):
                state.keywords_processed += 1
                state.last_keyword = keyword
                continue

            try:
                leads_found = self._process_keyword(
                    keyword, results_per_keyword=results_per_keyword, state=state
                )
                state.keywords_processed += 1
                state.leads_found += leads_found
                state.last_keyword = keyword
                self.memory.mark_keyword_done(keyword, commit=False)
            except Exception as exc:
                state.errors += 1
                self.memory.mark_keyword_done(
                    keyword, status="FAILED", error=str(exc), commit=False
                )
                self._log("ERROR", "discovery.engine", f"Keyword '{keyword}' failed: {exc}")
                logger.exception("Discovery error for keyword: %s", keyword)

            state.batch_index += 1
            self._flush_logs()
            self.checkpoint_mgr.save(state, commit=False)
            self.db.commit()

        if export_excel and state.leads_found > 0:
            self._export_to_excel(state)

        run = agent_run_repository.get(self.db, self.run_id)
        final_status = "COMPLETED_WITH_ERRORS" if state.errors else "COMPLETED"
        if run and run.status != "PAUSED":
            agent_run_repository.complete_run(self.db, run=run, status=final_status)
        self._log("INFO", "discovery.engine", f"Discovery finished. Leads: {state.leads_found}")
        self._trace(
            "final_summary",
            keywords_processed=state.keywords_processed,
            leads_found=state.leads_found,
            duplicates_skipped=state.duplicates_skipped,
            errors=state.errors,
            batch_index=state.batch_index,
        )
        self._flush_logs()
        self.db.commit()
        return state

    def _process_keyword(
        self, keyword: str, *, results_per_keyword: int, state: CheckpointState
    ) -> int:
        self._log("INFO", "discovery.search", f"Processing keyword: {keyword}")

        companies = self._collect_companies(keyword, limit=results_per_keyword)
        leads_saved = 0

        for company in companies:
            extracted_reasons = self.validator.explain_extracted(company)
            if extracted_reasons:
                self._trace(
                    "validation",
                    outcome="rejected_extracted",
                    company_name=company.name,
                    extracted_company=self._extracted_trace(company),
                    reasons=extracted_reasons,
                    source_url=company.source_url,
                    occurrence_count=company.occurrence_count,
                    entity_type=company.entity_type,
                    article_context=company.article_context,
                )
                continue

            self._trace(
                "validation",
                outcome="accepted_extracted",
                company_name=company.name,
                extracted_company=self._extracted_trace(company),
                source_url=company.source_url,
                website=company.website,
                occurrence_count=company.occurrence_count,
                entity_type=company.entity_type,
                article_context=company.article_context,
            )

            if self.memory.is_company_duplicate(website=company.website, name=company.name):
                state.duplicates_skipped += 1
                continue

            if company.website and self.memory.is_url_excluded(company.website):
                state.duplicates_skipped += 1
                continue

            if not company.website:
                company.website = self.website_finder.find_website(company)

            enriched = self.enricher.enrich(company)
            enriched = self.scorer.score(enriched)

            enriched_reasons = self.validator.explain_enriched(enriched)
            if enriched_reasons:
                self._trace(
                    "validation",
                    outcome="rejected_enriched",
                    company_name=enriched.name,
                    enriched_lead=self._enriched_trace(enriched),
                    reasons=enriched_reasons,
                    website=enriched.website,
                    website_intro=enriched.website_intro,
                    article_context=enriched.article_context,
                )
                continue

            self._trace(
                "validation",
                outcome="accepted_enriched",
                company_name=enriched.name,
                enriched_lead=self._enriched_trace(enriched),
                website=enriched.website,
                lead_score=enriched.lead_score,
                confidence_score=enriched.confidence_score,
                website_intro=enriched.website_intro,
                article_context=enriched.article_context,
            )

            self._persist_lead(enriched)
            self.memory.remember_company(
                name=enriched.name,
                website=enriched.website,
                linkedin=next((s["url"] for s in enriched.social_links if s["platform"] == "LINKEDIN"), None),
                instagram=next((s["url"] for s in enriched.social_links if s["platform"] == "INSTAGRAM"), None),
                email=next((c["value"] for c in enriched.contacts if c["type"] == "EMAIL"), None),
                domain=(enriched.website or "").replace("https://", "").replace("http://", "").split("/")[0] or None,
                source=company.source_url or company.website,
                commit=False,
            )
            leads_saved += 1

        return leads_saved

    def _collect_companies(self, keyword: str, *, limit: int) -> list[ExtractedCompany]:
        companies: list[ExtractedCompany] = []
        seen_urls: set[str] = set()

        directory_companies = plugin_registry.discover_directories(keyword, limit=limit)
        for company in directory_companies:
            companies.append(company)
            if company.source_url:
                seen_urls.add(company.source_url.strip())
            if company.website:
                seen_urls.add(company.website.strip())

        source_urls = self._collect_source_urls(keyword, limit=limit)
        for url in source_urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            try:
                extracted = self.extractor.extract_from_url(url)
            except Exception as exc:
                self._log("WARNING", "discovery.extractor", f"Extraction failed for {url}: {exc}")
                continue

            for company in extracted:
                if url not in company.source_urls:
                    company.source_urls.append(url)
                if company.source_url is None:
                    company.source_url = url
                companies.append(company)
                if len(companies) >= limit * 8:
                    return companies

        return companies

    def _collect_source_urls(self, keyword: str, *, limit: int) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()

        search_results = plugin_registry.search(keyword, limit=limit)
        self._trace(
            "search_connector",
            keyword=keyword,
            result_count=len(search_results),
            results=[
                {"url": result.url, "title": result.title, "source": result.source}
                for result in search_results
            ],
        )
        for result in search_results:
            url = result.url.strip()
            if url and url not in seen:
                seen.add(url)
                urls.append(url)

        directory_companies = plugin_registry.discover_directories(keyword, limit=limit)
        for company in directory_companies:
            for candidate in [company.source_url, company.website]:
                if candidate:
                    candidate = candidate.strip()
                    if candidate not in seen:
                        seen.add(candidate)
                        urls.append(candidate)

        return urls[: max(limit * 3, limit)]

    def _persist_lead(self, lead: EnrichedLead) -> None:
        persistence_payload = {
            "company_data": {
                "name": lead.name,
                "website": lead.website,
                "description": lead.description,
                "country": lead.country,
                "state": lead.state,
                "city": lead.city,
                "company_size": lead.company_size,
                "funding_stage": lead.funding_stage,
                "lead_score": lead.lead_score,
                "confidence_score": lead.confidence_score,
            },
            "categories": lead.categories,
            "contacts": lead.contacts,
            "social_links": lead.social_links,
            "profiles": lead.profiles,
            "sources": lead.sources,
        }
        self._trace(
            "persistence",
            event="saving_company",
            company={
                "name": lead.name,
                "website": lead.website,
                "description": lead.description,
                "article_context": lead.article_context,
                "website_intro": lead.website_intro,
                "country": lead.country,
                "state": lead.state,
                "city": lead.city,
                "lead_score": lead.lead_score,
                "confidence_score": lead.confidence_score,
            },
            repository_payload=persistence_payload,
        )
        saved_company = lead_repository.create_or_update_lead(
            self.db,
            company_data=persistence_payload["company_data"],
            categories=persistence_payload["categories"],
            contacts=persistence_payload["contacts"],
            social_links=persistence_payload["social_links"],
            profiles=persistence_payload["profiles"],
            sources=persistence_payload["sources"],
            commit=True,
        )
        self._trace(
            "persistence",
            event="saved_company",
            company_id=saved_company.id,
            company_name=saved_company.name,
            website=saved_company.website,
        )
        self._log(
            "INFO",
            "discovery.persist",
            f"Saved lead: {lead.name} (score={lead.lead_score}, confidence={lead.confidence_score})",
        )

    def _export_to_excel(self, state: CheckpointState) -> None:
        companies = lead_repository.search_leads(self.db, limit=10000)
        if not companies:
            return
        excel_name, excel_path, count = self.export_service.export_leads(
            companies, format="EXCEL"
        )
        csv_name, csv_path, _ = self.export_service.export_leads(companies, format="CSV")
        state.export_file = excel_path
        self._log(
            "INFO",
            "discovery.export",
            f"Exports created: {excel_name}, {csv_name} ({count} leads)",
        )

    def _extracted_trace(self, company: ExtractedCompany) -> dict:
        return {
            "name": company.name,
            "website": company.website,
            "description": company.description,
            "article_context": company.article_context,
            "occurrence_count": company.occurrence_count,
            "entity_type": company.entity_type,
            "founder": company.founder,
            "industry": company.industry,
            "email": company.email,
            "phone": company.phone,
            "location": company.location,
            "country": company.country,
            "funding": company.funding,
            "employee_size": company.employee_size,
            "confidence": company.confidence,
            "source_url": company.source_url,
            "source_urls": company.source_urls,
            "strategy": company.strategy,
            "tags": company.tags,
            "social_links": company.social_links,
        }

    def _enriched_trace(self, lead: EnrichedLead) -> dict:
        return {
            "name": lead.name,
            "website": lead.website,
            "description": lead.description,
            "article_context": lead.article_context,
            "website_intro": lead.website_intro,
            "llm_confidence": lead.llm_confidence,
            "founder": lead.founder,
            "industry": lead.industry,
            "country": lead.country,
            "state": lead.state,
            "city": lead.city,
            "funding_stage": lead.funding_stage,
            "company_size": lead.company_size,
            "categories": lead.categories,
            "contacts": lead.contacts,
            "social_links": lead.social_links,
            "profiles": lead.profiles,
            "sources": lead.sources,
            "lead_score": lead.lead_score,
            "confidence_score": lead.confidence_score,
        }

    def _trace(self, stage: str, **payload) -> None:
        trace = {"stage": stage, **payload}
        logger.info(json.dumps(trace, default=str))
        self._pending_logs.append(("DEBUG", "discovery.trace", json.dumps(trace, default=str)))

    def _log(self, level: str, module: str, message: str) -> None:
        self._pending_logs.append((level, module, message))

    def _flush_logs(self) -> None:
        for level, module, message in self._pending_logs:
            agent_run_repository.add_log(
                self.db,
                run_id=self.run_id,
                level=level,
                module=module,
                message=message,
                commit=False,
            )
        self._pending_logs.clear()
