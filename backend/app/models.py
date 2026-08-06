from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    mobile: Mapped[str | None] = mapped_column(String(20), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="student", index=True)
    enrollment_type: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    college_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pursuing_year: Mapped[str | None] = mapped_column(String(50), nullable=True)
    memo_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    allotment_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    internship_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    preferred_language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    area_interest: Mapped[str | None] = mapped_column(String(250), nullable=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    mentor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    coordinator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    learning_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    college_seat_active: Mapped[bool] = mapped_column(Boolean, default=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    mobile_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("title", "technology", "internship_type", name="uq_project_technology_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(180), index=True)
    technology: Mapped[str] = mapped_column(String(50), index=True)
    internship_type: Mapped[str] = mapped_column(String(30), index=True)
    domain: Mapped[str] = mapped_column(String(80), default="General")
    difficulty: Mapped[str] = mapped_column(String(30), default="Intermediate")
    description: Mapped[str] = mapped_column(Text)
    features: Mapped[list] = mapped_column(JSON, default=list)
    available_tracks: Mapped[list] = mapped_column(JSON, default=lambda: ["FULL_STACK"])
    master_zip_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stack_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    generated: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="PUBLISHED")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    individual_fee_rupees: Mapped[int] = mapped_column(Integer, default=999)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("project_id", "order_no", name="uq_project_task_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    order_no: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text)
    deliverables: Mapped[list] = mapped_column(JSON, default=list)
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list)
    visible_tests: Mapped[list] = mapped_column(JSON, default=list)
    hidden_checks: Mapped[list] = mapped_column(JSON, default=list)
    checkpoint_file: Mapped[str] = mapped_column(String(500), default="gaint_checkpoints/task_1.py")
    challenge_prompt: Mapped[str] = mapped_column(Text, default="")
    judge0_cases: Mapped[list] = mapped_column(JSON, default=list)
    required_paths: Mapped[list] = mapped_column(JSON, default=list)
    local_checks: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    variant_title: Mapped[str] = mapped_column(String(220))
    variant_brief: Mapped[str] = mapped_column(Text)
    variant_seed: Mapped[str] = mapped_column(String(40))
    selected_track: Mapped[str] = mapped_column(String(30), default="FULL_STACK")
    status: Mapped[str] = mapped_column(String(30), default="IN_PROGRESS")
    access_status: Mapped[str] = mapped_column(String(30), default="ACTIVE")
    access_ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    grace_ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    incomplete_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    student_guide_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    starter_downloaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    project_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fingerprinted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completion_package_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    completion_package_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completion_packaged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Certificate(Base):
    __tablename__ = "certificates"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    certificate_no: Mapped[str] = mapped_column(String(80), unique=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("user_id", "attendance_date", name="uq_student_attendance_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    attendance_date: Mapped[date] = mapped_column(Date, index=True)
    check_in_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    work_minutes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="PRESENT")
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    marked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class JudgeRun(Base):
    __tablename__ = "judge_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    language: Mapped[str] = mapped_column(String(30))
    source_hash: Mapped[str] = mapped_column(String(64))
    file_names: Mapped[list] = mapped_column(JSON, default=list)
    required_file_hashes: Mapped[dict] = mapped_column(JSON, default=dict)
    local_check_results: Mapped[list] = mapped_column(JSON, default=list)
    project_source_hashes: Mapped[dict] = mapped_column(JSON, default=dict)
    project_validation_details: Mapped[dict] = mapped_column(JSON, default=dict)
    project_snapshot_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    similarity_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    explanation: Mapped[str] = mapped_column(Text, default="Submitted from the GAINT VS Code extension")
    judge_tokens: Mapped[list] = mapped_column(JSON, default=list)
    results: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="QUEUED")
    total_cases: Mapped[int] = mapped_column(Integer, default=0)
    passed_cases: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class TaskReview(Base):
    __tablename__ = "task_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    judge_run_id: Mapped[int] = mapped_column(ForeignKey("judge_runs.id"), unique=True, index=True)
    mentor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="VERIFIED")
    feedback: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class MouAccess(Base):
    __tablename__ = "mou_access"

    id: Mapped[int] = mapped_column(primary_key=True)
    coordinator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    college_name: Mapped[str] = mapped_column(String(200), index=True)
    mou_number: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    student_limit: Mapped[int] = mapped_column(Integer, default=1)
    allowed_project_ids: Mapped[list] = mapped_column(JSON, default=list)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id"), unique=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    amount_rupees: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    provider: Mapped[str] = mapped_column(String(30), default="demo")
    status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    provider_order_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    receipt_number: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    policy_accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(100), default="VS Code")
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WorkspaceBootstrap(Base):
    __tablename__ = "workspace_bootstraps"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AiInteraction(Base):
    __tablename__ = "ai_interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    action: Mapped[str] = mapped_column(String(30))
    prompt_summary: Mapped[str] = mapped_column(String(500), default="")
    response_text: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(30), default="safe-local")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    target_type: Mapped[str] = mapped_column(String(60))
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AssignmentValidation(Base):
    __tablename__ = "assignment_validations"

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("assignments.id"), unique=True, index=True
    )
    starter_hashes: Mapped[dict] = mapped_column(JSON, default=dict)
    last_source_hashes: Mapped[dict] = mapped_column(JSON, default=dict)
    final_source_hashes: Mapped[dict] = mapped_column(JSON, default=dict)
    final_check_results: Mapped[list] = mapped_column(JSON, default=list)
    final_details: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_snapshot_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ProjectTeam(Base):
    __tablename__ = "project_teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    college_name: Mapped[str] = mapped_column(String(200), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    coordinator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", index=True)
    combined_package_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    combined_package_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ProjectTeamMember(Base):
    __tablename__ = "project_team_members"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_student"),
        UniqueConstraint("user_id", name="uq_student_active_team"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("project_teams.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id"), unique=True)
    track: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE")
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TeamArtifact(Base):
    __tablename__ = "team_artifacts"
    __table_args__ = (
        UniqueConstraint("team_id", "assignment_id", "task_id", name="uq_team_task_artifact"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("project_teams.id"), index=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    track: Mapped[str] = mapped_column(String(30))
    source_hashes: Mapped[dict] = mapped_column(JSON, default=dict)
    snapshot_filename: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PaymentWebhookEvent(Base):
    __tablename__ = "payment_webhook_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(30), default="razorpay")
    event_id: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    event_name: Mapped[str] = mapped_column(String(100))
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
