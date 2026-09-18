"""User accounts.

Deliberately in its own MetaData: the synthetic-data generator drops and rebuilds
the analytics tables on every run, and accounts must survive that.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean, Column, DateTime, MetaData, String, Table, UniqueConstraint,
)

auth_metadata = MetaData()

users = Table(
    "users", auth_metadata,
    Column("user_id", String(32), primary_key=True),
    Column("email", String(254), nullable=False),          # stored lower-cased
    Column("full_name", String(120), nullable=False),
    Column("company", String(120)),
    Column("role", String(32), nullable=False, default="analyst"),
    # Format: scrypt$n$r$p$<salt-hex>$<hash-hex>. No plaintext, ever.
    Column("password_hash", String(320), nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("last_login_at", DateTime),
    Column("is_demo", Boolean, nullable=False, default=False),
    UniqueConstraint("email", name="uq_users_email"),
)
