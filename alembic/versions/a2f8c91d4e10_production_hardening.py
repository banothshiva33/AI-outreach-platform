"""production hardening

Revision ID: a2f8c91d4e10
Revises: 941b16552d66
Create Date: 2026-07-05 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a2f8c91d4e10"
down_revision: Union[str, None] = "941b16552d66"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_contacts_value", table_name="contacts")
    op.drop_index("ix_social_links_url", table_name="social_links")
    op.drop_index("ix_exclude_memory_entity_value", table_name="exclude_memory")

    op.create_index("ix_contacts_value", "contacts", ["value"], unique=False)
    op.create_index("ix_social_links_url", "social_links", ["url"], unique=False)
    op.create_index("ix_exclude_memory_entity_value", "exclude_memory", ["entity_value"], unique=False)

    op.create_unique_constraint("uq_contacts_company_value", "contacts", ["company_id", "value"])
    op.create_unique_constraint("uq_social_links_company_url", "social_links", ["company_id", "url"])
    op.create_unique_constraint(
        "uq_exclude_memory_type_value", "exclude_memory", ["entity_type", "entity_value"]
    )

    op.create_index("ix_search_history_status", "search_history", ["status"], unique=False)
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"], unique=False)
    op.create_index("ix_logs_run_id_timestamp", "logs", ["run_id", "timestamp"], unique=False)
    op.create_index("ix_social_links_platform", "social_links", ["platform"], unique=False)
    op.create_index("ix_contacts_type", "contacts", ["type"], unique=False)
    op.create_index("ix_exclude_memory_entity_type", "exclude_memory", ["entity_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_exclude_memory_entity_type", table_name="exclude_memory")
    op.drop_index("ix_contacts_type", table_name="contacts")
    op.drop_index("ix_social_links_platform", table_name="social_links")
    op.drop_index("ix_logs_run_id_timestamp", table_name="logs")
    op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    op.drop_index("ix_search_history_status", table_name="search_history")

    op.drop_constraint("uq_exclude_memory_type_value", "exclude_memory", type_="unique")
    op.drop_constraint("uq_social_links_company_url", "social_links", type_="unique")
    op.drop_constraint("uq_contacts_company_value", "contacts", type_="unique")

    op.drop_index("ix_exclude_memory_entity_value", table_name="exclude_memory")
    op.drop_index("ix_social_links_url", table_name="social_links")
    op.drop_index("ix_contacts_value", table_name="contacts")

    op.create_index("ix_contacts_value", "contacts", ["value"], unique=True)
    op.create_index("ix_social_links_url", "social_links", ["url"], unique=True)
    op.create_index("ix_exclude_memory_entity_value", "exclude_memory", ["entity_value"], unique=True)
