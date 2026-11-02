from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---- Vocabularies (stored as plain strings so the DB stays portable) ----
PROVIDERS = ("wos", "scopus", "scholar")
PUB_STATUSES = ("published", "online_first", "accepted", "submitted", "unpublished")
LANGUAGES = ("english", "hebrew", "german", "other")
PUB_TYPES = ("journal_article", "book", "book_chapter", "conference", "report", "other")
CHECK_STATUSES = ("not_checked", "found", "not_indexed", "needs_verification")
CLASSIFICATIONS = ("self", "non_self", "needs_verification")
ROLES = ("admin", "librarian", "reviewer")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    role: Mapped[str] = mapped_column(String(20), default="librarian")
    password_hash: Mapped[str] = mapped_column(String(300))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SessionToken(Base):
    __tablename__ = "session_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user: Mapped[User] = relationship()


class Policy(Base):
    """Inclusion and calculation policy. case_id NULL = institutional default (admin only)."""
    __tablename__ = "policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), unique=True, nullable=True)
    included_languages: Mapped[list] = mapped_column(JSON, default=lambda: ["english"])
    included_statuses: Mapped[list] = mapped_column(JSON, default=lambda: ["published", "online_first", "accepted"])
    included_types: Mapped[list] = mapped_column(JSON, default=lambda: list(PUB_TYPES))
    # "A" = evaluated researcher appears in both; "B" = any shared author
    self_citation_definition: Mapped[str] = mapped_column(String(1), default="A")
    # exact full-name match without identifiers counts as self (True) or goes to review (False)
    full_name_match_is_self: Mapped[bool] = mapped_column(Boolean, default=True)
    # H/I columns: "sum" (sum of databases, NOT unique), "unique" (deduplicated), "max", "empty"
    summary_mode: Mapped[str] = mapped_column(String(10), default="sum")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    updated_by: Mapped[str] = mapped_column(String(80), default="")


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    researcher_name_en: Mapped[str] = mapped_column(String(200))
    researcher_name_he: Mapped[str] = mapped_column(String(200), default="")
    name_variants: Mapped[list] = mapped_column(JSON, default=list)  # e.g. ["E. Eizenberg", "Efrat Eisenberg"]
    orcid: Mapped[str] = mapped_column(String(40), default="")
    scopus_author_id: Mapped[str] = mapped_column(String(40), default="")
    wos_researcher_id: Mapped[str] = mapped_column(String(40), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    cv_filename: Mapped[str] = mapped_column(String(300), default="")
    cv_path: Mapped[str] = mapped_column(String(500), default="")
    cv_sha256: Mapped[str] = mapped_column(String(64), default="")
    cv_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    template_filename: Mapped[str] = mapped_column(String(300), default="")
    template_path: Mapped[str] = mapped_column(String(500), default="")
    extraction_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # QA approvals: preparer + second reviewer (must be a different user)
    prepared_by: Mapped[str] = mapped_column(String(80), default="")
    prepared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str] = mapped_column(String(80), default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")

    publications: Mapped[list["Publication"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="Publication.seq"
    )


class Publication(Base):
    __tablename__ = "publications"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)  # order in the CV (never changes on export)
    original_number: Mapped[str] = mapped_column(String(20), default="")
    raw_text: Mapped[str] = mapped_column(Text)  # verbatim from the CV, never modified
    section: Mapped[str] = mapped_column(String(300), default="")
    subsection: Mapped[str] = mapped_column(String(300), default="")
    title: Mapped[str] = mapped_column(Text, default="")
    authors: Mapped[list] = mapped_column(JSON, default=list)  # list[str]
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str] = mapped_column(Text, default="")
    pub_type: Mapped[str] = mapped_column(String(30), default="other")
    language: Mapped[str] = mapped_column(String(20), default="english")
    language_evidence: Mapped[str] = mapped_column(Text, default="")
    doi: Mapped[str] = mapped_column(String(200), default="")
    cv_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pub_status: Mapped[str] = mapped_column(String(20), default="published")
    status_evidence: Mapped[str] = mapped_column(Text, default="")
    # manual override of the policy: None = follow policy, True/False = forced
    manual_include: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    manual_include_reason: Mapped[str] = mapped_column(Text, default="")
    manually_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")

    case: Mapped[Case] = relationship(back_populates="publications")
    checks: Mapped[list["ProviderCheck"]] = relationship(cascade="all, delete-orphan", back_populates="publication")
    candidates: Mapped[list["SourceRecord"]] = relationship(cascade="all, delete-orphan", back_populates="publication")
    citing: Mapped[list["CitingRecord"]] = relationship(cascade="all, delete-orphan", back_populates="publication")


class ProviderCheck(Base):
    """Status of one publication in one database (procedure stage B recording rules)."""
    __tablename__ = "provider_checks"
    __table_args__ = (UniqueConstraint("publication_id", "provider"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    publication_id: Mapped[int] = mapped_column(ForeignKey("publications.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(25), default="not_checked")
    selected_record_id: Mapped[int | None] = mapped_column(ForeignKey("source_records.id", ondelete="SET NULL"), nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checked_by: Mapped[str] = mapped_column(String(80), default="")
    # citing list completeness: "none" | "partial" | "complete" | "unavailable"
    citing_list_status: Mapped[str] = mapped_column(String(15), default="none")
    notes: Mapped[str] = mapped_column(Text, default="")

    publication: Mapped[Publication] = relationship(back_populates="checks")
    selected_record: Mapped["SourceRecord | None"] = relationship(foreign_keys=[selected_record_id])


class SourceRecord(Base):
    """A candidate record found in a database (or entered manually) for a publication."""
    __tablename__ = "source_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    publication_id: Mapped[int] = mapped_column(ForeignKey("publications.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(10))
    record_id: Mapped[str] = mapped_column(String(200), default="")  # Scopus EID / WoS UID / Scholar cluster id
    found_title: Mapped[str] = mapped_column(Text, default="")
    found_authors: Mapped[list] = mapped_column(JSON, default=list)  # list[{name, orcid, scopus_id, researcher_id}]
    found_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    found_doi: Mapped[str] = mapped_column(String(200), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_explanation: Mapped[str] = mapped_column(Text, default="")
    total_citations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    record_status: Mapped[str] = mapped_column(String(25), default="candidate")  # candidate|selected|rejected
    source_url: Mapped[str] = mapped_column(Text, default="")
    method: Mapped[str] = mapped_column(String(10), default="api")  # api | manual | import
    entered_by: Mapped[str] = mapped_column(String(80), default="")

    publication: Mapped[Publication] = relationship(back_populates="candidates")


class CitingRecord(Base):
    __tablename__ = "citing_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    publication_id: Mapped[int] = mapped_column(ForeignKey("publications.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(Text, default="")
    doi: Mapped[str] = mapped_column(String(200), default="")
    external_id: Mapped[str] = mapped_column(String(200), default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    authors: Mapped[list] = mapped_column(JSON, default=list)  # list[{name, orcid, scopus_id, researcher_id}]
    authors_complete: Mapped[bool] = mapped_column(Boolean, default=True)
    source_url: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(20), default="import")  # api | import | manual
    origin_detail: Mapped[str] = mapped_column(Text, default="")
    # automatic classifications
    class_a: Mapped[str] = mapped_column(String(20), default="needs_verification")
    explain_a: Mapped[str] = mapped_column(Text, default="")
    class_b: Mapped[str] = mapped_column(String(20), default="needs_verification")
    explain_b: Mapped[str] = mapped_column(Text, default="")
    # manual overrides (None = use automatic)
    manual_a: Mapped[str | None] = mapped_column(String(20), nullable=True)
    manual_b: Mapped[str | None] = mapped_column(String(20), nullable=True)
    manual_note: Mapped[str] = mapped_column(Text, default="")
    manually_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_by: Mapped[str] = mapped_column(String(80), default="")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    publication: Mapped[Publication] = relationship(back_populates="citing")

    def final(self, definition: str) -> str:
        if definition == "B":
            return self.manual_b or self.class_b
        return self.manual_a or self.class_a


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    username: Mapped[str] = mapped_column(String(80), default="")
    case_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(40))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
