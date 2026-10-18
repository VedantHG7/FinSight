"""
SQLAlchemy models for FinSight application.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, Text, Enum, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.db.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    USER = "USER"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.USER)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    clients = relationship("Client", back_populates="user", cascade="all, delete-orphan")
    analyses = relationship("Analysis", back_populates="user", cascade="all, delete-orphan")


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    company_name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="clients")
    analyses = relationship("Analysis", back_populates="client", cascade="all, delete-orphan")


class AnalysisStatus(str, enum.Enum):
    uploaded = "UPLOADED"
    preprocessed = "PREPROCESSED"
    rules_applied = "RULES_APPLIED"
    ml_completed = "ML_COMPLETED"
    xai_completed = "XAI_COMPLETED"
    completed = "COMPLETED"
    failed = "FAILED"


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    status = Column(Enum(AnalysisStatus), default=AnalysisStatus.uploaded)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="analyses")
    client = relationship("Client", back_populates="analyses")
    audit_findings = relationship("AuditFinding", back_populates="analysis", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="analysis", cascade="all, delete-orphan")


class AuditFinding(Base):
    __tablename__ = "audit_findings"

    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id"), nullable=False)
    year = Column(Integer, nullable=True)
    rule_id = Column(String(100), nullable=False)
    rule_name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=True)
    severity = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False)  # passed, failed, skipped, error
    evidence = Column(Text, nullable=True)
    actual_value = Column(Text, nullable=True)
    expected_value = Column(Text, nullable=True)
    explanation = Column(Text, nullable=True)
    recommendation = Column(Text, nullable=True)
    risk_impact = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    analysis = relationship("Analysis", back_populates="audit_findings")

    __table_args__ = (
        Index('ix_audit_findings_analysis_id', 'analysis_id'),
        Index('ix_audit_findings_year', 'year'),
        Index('ix_audit_findings_rule_id', 'rule_id'),
        Index('ix_audit_findings_severity', 'severity'),
    )


class ReportType(str, enum.Enum):
    EXPLAINABILITY = "EXPLAINABILITY"
    FULL_AUDIT = "FULL_AUDIT"
    SUMMARY = "SUMMARY"


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id"), nullable=False)
    report_type = Column(Enum(ReportType), nullable=False)
    storage_key = Column(String(500), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    analysis = relationship("Analysis", back_populates="reports")

    __table_args__ = (
        Index('ix_reports_analysis_id', 'analysis_id'),
        Index('ix_reports_report_type', 'report_type'),
    )


class AnalysisEvent(Base):
    __tablename__ = "analysis_events"

    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id"), nullable=False)
    stage = Column(String(100), nullable=False)
    status = Column(String(30), nullable=False)
    message = Column(Text, nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_analysis_events_analysis_id', 'analysis_id'),
        Index('ix_analysis_events_stage', 'stage'),
    )

# Additive workspace schema. Existing analyses and artifact paths are preserved.
class Organization(Base):
    __tablename__ = 'organizations'
    id = Column(Integer, primary_key=True)
    name = Column(String(160), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class Membership(Base):
    __tablename__ = 'memberships'
    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False, index=True)
    role = Column(String(20), nullable=False, default='analyst')


class AuthSession(Base):
    __tablename__ = 'auth_sessions'
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    csrf_token = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)


class PasswordReset(Base):
    __tablename__ = 'password_resets'
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)


class LoginAttempt(Base):
    __tablename__ = 'login_attempts'
    id = Column(Integer, primary_key=True)
    identity = Column(String(64), nullable=False, index=True)
    address = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, index=True)


class Invitation(Base):
    __tablename__ = 'workspace_invitations'
    token_hash = Column(String(64), primary_key=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False)
    email = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, nullable=False, default=False)


class AnalysisJob(Base):
    __tablename__ = 'analysis_jobs'
    analysis_id = Column(Integer, ForeignKey('analyses.id'), primary_key=True)
    state = Column(String(20), nullable=False, default='queued', index=True)
    stage = Column(String(100), nullable=False, default='Queued')
    progress = Column(Integer, nullable=False, default=0)
    attempts = Column(Integer, nullable=False, default=0)
    lease_token = Column(String(64), nullable=True)
    lease_until = Column(DateTime, nullable=True)
    cancel_requested = Column(Boolean, nullable=False, default=False)
    error = Column(Text, nullable=True)
    file_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class FindingReview(Base):
    __tablename__ = 'finding_reviews'
    analysis_id = Column(Integer, ForeignKey('analyses.id'), primary_key=True)
    finding_key = Column(String(160), primary_key=True)
    status = Column(String(24), nullable=False, default='open')
    assignee_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    updated_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class ReviewEvent(Base):
    __tablename__ = 'review_events'
    id = Column(Integer, primary_key=True)
    analysis_id = Column(Integer, ForeignKey('analyses.id'), nullable=False, index=True)
    finding_key = Column(String(160), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    message = Column(Text, nullable=False)
    changes = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
