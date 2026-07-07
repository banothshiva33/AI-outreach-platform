import uuid
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, Table, Text, JSON, TypeDecorator, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.time import utc_now

class SafeJSON(TypeDecorator):
    """
    Custom JSON type that uses PostgreSQL's JSONB type in production,
    but falls back to standard SQLAlchemy JSON in testing/SQLite.
    """
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())

# Association table for many-to-many relationship between Companies and Categories
company_category_association = Table(
    "company_categories",
    Base.metadata,
    Column("company_id", UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True)
)

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)

    exports = relationship("Export", back_populates="user", cascade="all, delete-orphan")

class Company(Base):
    __tablename__ = "companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, index=True)
    website = Column(String, unique=True, nullable=True, index=True)
    description = Column(Text, nullable=True)
    country = Column(String, nullable=True, index=True)
    state = Column(String, nullable=True, index=True)
    city = Column(String, nullable=True, index=True)
    company_size = Column(String, nullable=True)
    funding_stage = Column(String, nullable=True)
    
    # Lead quality and scoring fields
    lead_score = Column(Integer, default=0, index=True)
    confidence_score = Column(Float, default=0.0)
    
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    profiles = relationship("Profile", back_populates="company", cascade="all, delete-orphan")
    social_links = relationship("SocialLink", back_populates="company", cascade="all, delete-orphan")
    contacts = relationship("Contact", back_populates="company", cascade="all, delete-orphan")
    sources = relationship("Source", back_populates="company", cascade="all, delete-orphan")
    categories = relationship("Category", secondary=company_category_association, back_populates="companies")

class Profile(Base):
    """Stores Founder / Key Personnel details associated with a company."""
    __tablename__ = "profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    title = Column(String, nullable=True)  # Founder, CEO, etc.
    profile_url = Column(String, nullable=True)  # Founder LinkedIn page URL
    created_at = Column(DateTime, default=utc_now)

    company = relationship("Company", back_populates="profiles")

class SocialLink(Base):
    """Stores company's official social media pages and metrics."""
    __tablename__ = "social_links"
    __table_args__ = (
        UniqueConstraint("company_id", "url", name="uq_social_links_company_url"),
        Index("ix_social_links_platform", "platform"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    platform = Column(String, nullable=False)
    url = Column(String, nullable=False, index=True)
    username = Column(String, nullable=True)
    followers_count = Column(Integer, nullable=True)
    following_count = Column(Integer, nullable=True)
    posts_count = Column(Integer, nullable=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now)

    company = relationship("Company", back_populates="social_links")

class Contact(Base):
    """Stores company's contact numbers or emails."""
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("company_id", "value", name="uq_contacts_company_value"),
        Index("ix_contacts_type", "type"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)
    value = Column(String, nullable=False, index=True)
    is_verified = Column(Boolean, default=False)
    source = Column(String, nullable=True)  # Scraped website, LinkedIn, etc.
    created_at = Column(DateTime, default=utc_now)

    company = relationship("Company", back_populates="contacts")

class Category(Base):
    """Stores industries/topics (e.g. AI Startup, FinTech)."""
    __tablename__ = "categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False, index=True)

    companies = relationship("Company", secondary=company_category_association, back_populates="categories")

class Source(Base):
    """Tracks how a company was discovered (for reliability calculations)."""
    __tablename__ = "sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    url = Column(String, nullable=False)
    strategy = Column(String, nullable=False)  # GOOGLE_SEARCH, DIRECTORY, WEB_SCRAPING
    reliability_score = Column(Integer, default=50)  # Reliability score of source
    discovered_at = Column(DateTime, default=utc_now)

    company = relationship("Company", back_populates="sources")

class SearchHistory(Base):
    """Remembers already-searched keywords to avoid duplicate planning work."""
    __tablename__ = "search_history"
    __table_args__ = (Index("ix_search_history_status", "status"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    keyword = Column(String, unique=True, nullable=False, index=True)
    status = Column(String, default="PENDING")  # PENDING, COMPLETED, FAILED
    search_count = Column(Integer, default=0)
    last_searched = Column(DateTime, nullable=True)
    error_message = Column(String, nullable=True)
    is_expanded = Column(Boolean, default=False)

class Job(Base):
    """Tracks Celery background workers tasks."""
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    status = Column(String, default="PENDING")  # PENDING, RUNNING, SUCCESS, FAILURE, RETRY
    run_id = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    run = relationship("AgentRun", back_populates="jobs")

class AgentRun(Base):
    """Logs the history, config and performance of autonomous agent executions."""
    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_status", "status"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(String, default="RUNNING")  # RUNNING, COMPLETED, FAILED, PAUSED
    trigger_type = Column(String, default="MANUAL")  # MANUAL, SCHEDULED
    config = Column(SafeJSON, nullable=True)  # Seed keywords, limits, model config
    stats = Column(SafeJSON, default=lambda: {"leads_found": 0, "duplicates_skipped": 0, "errors": 0})
    last_checkpoint = Column(String, nullable=True)  # Resumable workflow checkpoint state
    started_at = Column(DateTime, default=utc_now)
    ended_at = Column(DateTime, nullable=True)

    jobs = relationship("Job", back_populates="run", cascade="all, delete-orphan")
    logs = relationship("Log", back_populates="run", cascade="all, delete-orphan")

class Export(Base):
    """Tracks report generation history and filter criteria."""
    __tablename__ = "exports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    format = Column(String, nullable=False)  # EXCEL, CSV, JSON
    records_count = Column(Integer, default=0)
    filters = Column(SafeJSON, nullable=True)  # Filters applied during export
    created_at = Column(DateTime, default=utc_now)

    user = relationship("User", back_populates="exports")

class Log(Base):
    """Persists execution logs emitted during specific agent runs."""
    __tablename__ = "logs"
    __table_args__ = (Index("ix_logs_run_id_timestamp", "run_id", "timestamp"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    level = Column(String, nullable=False)
    module = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    extra = Column(SafeJSON, nullable=True)
    timestamp = Column(DateTime, default=utc_now)

    run = relationship("AgentRun", back_populates="logs")

class ExcludeMemory(Base):
    """Remembers failed entities, dead links and duplicates to prevent repeating work."""
    __tablename__ = "exclude_memory"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_value", name="uq_exclude_memory_type_value"),
        Index("ix_exclude_memory_entity_type", "entity_type"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(String, nullable=False)
    entity_value = Column(String, nullable=False, index=True)
    reason = Column(String, nullable=True)  # DEAD_URL, BLACKLISTED, DUPLICATE_COMPANY
    created_at = Column(DateTime, default=utc_now)
