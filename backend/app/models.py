from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

def now(): return datetime.now(timezone.utc)
class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(180))
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="engineer")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
class Site(Base):
    __tablename__ = "sites"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    location: Mapped[str] = mapped_column(String(255), default="")
class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    product: Mapped[str] = mapped_column(String(180))
    variant: Mapped[str] = mapped_column(String(180), default="")
    defects: Mapped[list] = mapped_column(JSON, default=list)
    capture: Mapped[dict] = mapped_column(JSON, default=dict)
    thresholds: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(32), default="draft")
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
class ImageRecord(Base):
    __tablename__ = "images"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    path: Mapped[str] = mapped_column(String(512))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    split: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24), default="draft")
    dataset_version: Mapped[str] = mapped_column(String(64))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
class Inspection(Base):
    __tablename__ = "inspections"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id"), nullable=True)
    model_version_id: Mapped[int | None] = mapped_column(ForeignKey("model_versions.id"), nullable=True)
    result: Mapped[str] = mapped_column(String(24))
    score: Mapped[float | None] = mapped_column(nullable=True)
    explanation: Mapped[str] = mapped_column(Text, default="")
    corrected_result: Mapped[str | None] = mapped_column(String(24), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
