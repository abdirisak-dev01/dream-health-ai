"""Somali is no longer offered: move existing Somali accounts to English.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-20
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE users SET preferred_language = 'en' WHERE preferred_language = 'so' "
               "OR preferred_language LIKE 'so-%'")


def downgrade() -> None:
    pass  # the old language choice is not kept
