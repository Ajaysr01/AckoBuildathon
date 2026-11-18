from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint

from .database import Base


class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False, unique=True, index=True)
    role = Column(String(20), nullable=False)
    owner = Column(String(160), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SpecVersion(Base):
    __tablename__ = "spec_versions"
    __table_args__ = (UniqueConstraint("service_id", "version", "source_filename", name="uq_spec_source_version"),)

    id = Column(Integer, primary_key=True)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False, index=True)
    version = Column(String(80), nullable=False, index=True)
    source_filename = Column(String(255), nullable=True)
    document = Column(JSON, nullable=False)
    raw_content = Column(Text, nullable=False)
    validation_status = Column(String(20), nullable=False)
    validation_errors = Column(JSON, nullable=False, default=list)
    imported = Column(Boolean, nullable=False, default=False)
    published = Column(Boolean, nullable=False, default=False)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ConsumerUsage(Base):
    __tablename__ = "consumer_usages"
    id = Column(Integer, primary_key=True)
    consumer_service_id = Column(Integer, ForeignKey("services.id"), nullable=False, index=True)
    provider_service_id = Column(Integer, ForeignKey("services.id"), nullable=False, index=True)
    method = Column(String(10), nullable=False)
    path = Column(String(500), nullable=False)
    sends = Column(JSON, nullable=False, default=list)
    reads = Column(JSON, nullable=False, default=list)


class ImportRun(Base):
    __tablename__ = "import_runs"
    id = Column(Integer, primary_key=True)
    imported_specs = Column(Integer, nullable=False, default=0)
    invalid_specs = Column(Integer, nullable=False, default=0)
    imported_consumers = Column(Integer, nullable=False, default=0)
    warnings = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PublishAttempt(Base):
    __tablename__ = "publish_attempts"
    id = Column(Integer, primary_key=True)
    proposed_spec_id = Column(Integer, ForeignKey("spec_versions.id"), nullable=False, index=True)
    baseline_spec_id = Column(Integer, ForeignKey("spec_versions.id"), nullable=False)
    outcome = Column(String(20), nullable=False)
    reason = Column(Text, nullable=False)
    findings = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
