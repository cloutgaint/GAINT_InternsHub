from __future__ import annotations

import re
import hashlib
import json
import secrets
import uuid
import csv
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .certificate import build_certificate_pdf, build_evaluation_report_pdf
from .ai_assistant import safe_task_assistance, task_chat_assistance
from .config import settings
from .database import Base, SessionLocal, engine, get_db
from .dependencies import get_current_user, get_vscode_user, require_role
from .judge0 import Judge0Error, fetch_results, health as judge0_health, submit_tests
from .models import (
    AiInteraction, AssignmentValidation, AuditLog, Assignment, Attendance,
    Certificate, DeviceToken, JudgeRun, MouAccess, Payment, PaymentWebhookEvent,
    Project, ProjectTeam, ProjectTeamMember, Task, TeamArtifact, User,
    WorkspaceBootstrap, utcnow,
)
from .package_builder import starter_project_zip, team_completed_project_zip
from .payment_gateway import (
    RazorpayError,
    create_order as create_razorpay_order,
    fetch_payment as fetch_razorpay_payment,
    verify_checkout_signature,
    verify_webhook_signature,
)
from .project_upload import ProjectZipError, analyse_project_zip
from .project_validation import (
    ProjectValidationError,
    snapshot_hashes_from_zip,
    source_snapshot_zip,
    validate_source_snapshot,
)
from .project_generator import LEARNING_DAYS, TASK_COUNTS, personalised_variant, project_idea_from_prompt, project_ideas, task_specs
from .schemas import (
    AssignCoordinatorRequest,
    AssignMentorRequest,
    AttendanceOverrideRequest,
    AiChatRequest,
    AiTaskRequest,
    ChangePasswordRequest,
    CollegeStudentsGenerateRequest,
    CoordinatorCreateRequest,
    CompletionPackageRequest,
    GenerateProjectsRequest,
    JudgeSubmitRequest,
    LoginRequest,
    MentorCreateRequest,
    MouAccessRequest,
    PaymentConfirmRequest,
    PreferencesRequest,
    ProjectFingerprintRequest,
    ProjectCreateRequest,
    ProjectSelectRequest,
    PromptProjectRequest,
    RazorpayVerifyRequest,
    TeamCreateRequest,
    TaskCreateRequest,
    TECHNOLOGIES,
    WorkspaceBootstrapRequest,
)
from .security import create_token, hash_password, verify_password
from .seed import add_tasks, seed_database


INTERNSHIP_TYPES = {"FASTTRACK", "45_DAYS", "SEMESTER"}
INTERNSHIP_DAYS = {"FASTTRACK": 30, "45_DAYS": 45, "SEMESTER": 120}
GRACE_DAYS = {"FASTTRACK": 7, "45_DAYS": 15, "SEMESTER": 30}
DOCUMENT_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
INDIA_TZ = ZoneInfo("Asia/Kolkata")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    # create_all() does not add columns to an existing PostgreSQL volume.
    # Keep V7/V8 local installations compatible with the learning assistant.
    inspector = inspect(engine)
    if "ai_interactions" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("ai_interactions")}
        if "provider" not in columns:
            with engine.begin() as connection:
                if engine.dialect.name == "postgresql":
                    connection.execute(text(
                        "ALTER TABLE ai_interactions "
                        "ADD COLUMN IF NOT EXISTS provider VARCHAR(30) NOT NULL DEFAULT 'safe-local'"
                    ))
                else:
                    connection.execute(text(
                        "ALTER TABLE ai_interactions "
                        "ADD COLUMN provider VARCHAR(30) NOT NULL DEFAULT 'safe-local'"
                    ))
    inspector = inspect(engine)
    if "judge_runs" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("judge_runs")}
        additions = {
            "project_source_hashes": (
                "JSON NOT NULL DEFAULT '{}'::json"
                if engine.dialect.name == "postgresql"
                else "JSON NOT NULL DEFAULT '{}'"
            ),
            "project_validation_details": (
                "JSON NOT NULL DEFAULT '{}'::json"
                if engine.dialect.name == "postgresql"
                else "JSON NOT NULL DEFAULT '{}'"
            ),
            "project_snapshot_filename": "VARCHAR(255)",
        }
        with engine.begin() as connection:
            for name, definition in additions.items():
                if name not in columns:
                    if engine.dialect.name == "postgresql":
                        connection.execute(text(
                            f"ALTER TABLE judge_runs ADD COLUMN IF NOT EXISTS {name} {definition}"
                        ))
                    else:
                        connection.execute(text(
                            f"ALTER TABLE judge_runs ADD COLUMN {name} {definition}"
                        ))
    with SessionLocal() as db:
        seed_database(db)
    yield


app = FastAPI(title=settings.app_name, version="8.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


def public_user(user: User) -> dict:
    return {
        "id": user.id, "name": user.name, "email": user.email, "mobile": user.mobile,
        "role": user.role, "enrollment_type": user.enrollment_type,
        "college_name": user.college_name, "pursuing_year": user.pursuing_year,
        "internship_type": user.internship_type, "preferred_language": user.preferred_language,
        "area_interest": user.area_interest, "project_id": user.project_id, "mentor_id": user.mentor_id,
        "coordinator_id": user.coordinator_id, "must_change_password": user.must_change_password,
        "college_seat_active": user.college_seat_active,
        "email_verified": user.email_verified, "mobile_verified": user.mobile_verified,
        "created_at": user.created_at,
    }


def project_data(project: Project, task_count: int | None = None) -> dict:
    return {
        "id": project.id, "title": project.title, "technology": project.technology,
        "internship_type": project.internship_type, "domain": project.domain,
        "difficulty": project.difficulty, "description": project.description,
        "features": project.features, "available_tracks": project.available_tracks or ["FULL_STACK"],
        "stack_metadata": project.stack_metadata or {},
        "has_master_project": bool(project.master_zip_filename),
        "generated": project.generated, "status": project.status,
        "active": project.active, "task_count": task_count,
        "individual_fee_rupees": project.individual_fee_rupees,
    }


def audit(db: Session, actor_id: int | None, action: str, target_type: str, target_id: int | None = None, **details) -> None:
    db.add(AuditLog(actor_id=actor_id, action=action, target_type=target_type, target_id=target_id, details=details))


def payment_data(payment: Payment | None) -> dict | None:
    if not payment:
        return None
    # A pending payment follows the currently configured gateway. This lets an
    # Admin switch a local installation from demo to Razorpay without deleting
    # the student's assignment or payment row.
    provider = settings.payment_provider if payment.status != "PAID" else payment.provider
    return {
        "id": payment.id, "amount_rupees": payment.amount_rupees, "currency": payment.currency,
        "provider": provider, "status": payment.status,
        "receipt_number": payment.receipt_number, "paid_at": payment.paid_at,
        "policy_accepted_at": payment.policy_accepted_at,
    }


def assignment_payment(db: Session, assignment_id: int) -> Payment | None:
    return db.scalar(select(Payment).where(Payment.assignment_id == assignment_id))


def activate_paid_assignment(
    db: Session,
    payment: Payment,
    *,
    provider_payment_id: str,
    audit_action: str,
) -> None:
    if payment.status == "PAID":
        return
    assignment = db.get(Assignment, payment.assignment_id)
    if not assignment:
        raise HTTPException(status_code=409, detail="Payment assignment no longer exists")
    payment.status = "PAID"
    payment.provider_payment_id = provider_payment_id
    payment.receipt_number = payment.receipt_number or f"GAINT-RCPT-{utcnow():%Y%m%d}-{payment.id:06d}"
    payment.paid_at = payment.paid_at or utcnow()
    assignment.access_status = "ACTIVE"
    audit(
        db,
        payment.user_id,
        audit_action,
        "payment",
        payment.id,
        amount=payment.amount_rupees,
        provider=payment.provider,
    )


def assignment_enrollment_state(assignment: Assignment) -> str:
    if assignment.status == "COMPLETED":
        return "COMPLETED"
    now = utcnow()
    if assignment.grace_ends_at and now > assignment.grace_ends_at:
        return "INCOMPLETE"
    if assignment.access_ends_at and now > assignment.access_ends_at:
        return "GRACE"
    return "ACTIVE"


def assignment_access_allowed(db: Session, assignment: Assignment, user: User) -> bool:
    if assignment_enrollment_state(assignment) == "INCOMPLETE":
        return False
    if user.enrollment_type == "INDIVIDUAL":
        payment = assignment_payment(db, assignment.id)
        return bool(payment and payment.status == "PAID" and assignment.access_status == "ACTIVE")
    return assignment.access_status == "ACTIVE"


async def save_upload(upload: UploadFile | None, prefix: str, allowed: set[str], max_mb: int) -> str | None:
    if not upload or not upload.filename:
        return None
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix or 'unknown'}")
    content = await upload.read()
    if len(content) > max_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File must be {max_mb} MB or smaller")
    filename = f"{prefix}_{uuid.uuid4().hex}{suffix}"
    (settings.upload_dir / filename).write_bytes(content)
    return filename


def get_assignment(db: Session, user_id: int) -> Assignment | None:
    return db.scalar(select(Assignment).where(Assignment.user_id == user_id))


def project_tasks(db: Session, project_id: int) -> list[Task]:
    return list(db.scalars(select(Task).where(Task.project_id == project_id).order_by(Task.order_no)).all())


def completed_task_ids(db: Session, assignment_id: int) -> set[int]:
    return set(db.scalars(select(JudgeRun.task_id).where(
        JudgeRun.assignment_id == assignment_id,
        JudgeRun.status == "PASSED",
    )).all())


def latest_judge_run(db: Session, assignment_id: int, task_id: int) -> JudgeRun | None:
    return db.scalar(select(JudgeRun).where(
        JudgeRun.assignment_id == assignment_id, JudgeRun.task_id == task_id
    ).order_by(JudgeRun.created_at.desc()).limit(1))


def assignment_validation(
    db: Session, assignment_id: int, *, create: bool = False
) -> AssignmentValidation | None:
    validation = db.scalar(select(AssignmentValidation).where(
        AssignmentValidation.assignment_id == assignment_id
    ))
    if not validation and create:
        validation = AssignmentValidation(assignment_id=assignment_id)
        db.add(validation)
        db.flush()
    return validation


def assignment_team_member(db: Session, assignment_id: int) -> ProjectTeamMember | None:
    return db.scalar(select(ProjectTeamMember).where(
        ProjectTeamMember.assignment_id == assignment_id
    ))


def team_data(db: Session, assignment_id: int) -> dict | None:
    member = assignment_team_member(db, assignment_id)
    if not member:
        return None
    team = db.get(ProjectTeam, member.team_id)
    members = list(db.scalars(select(ProjectTeamMember).where(
        ProjectTeamMember.team_id == member.team_id
    ).order_by(ProjectTeamMember.id)).all())
    return {
        "id": team.id,
        "name": team.name,
        "status": team.status,
        "member_track": member.track,
        "members": [
            {
                "student": public_user(db.get(User, item.user_id)),
                "track": item.track,
                "assignment_id": item.assignment_id,
                "completed": certificate_ready(db, db.get(Assignment, item.assignment_id)),
            }
            for item in members
        ],
        "combined_package_ready": bool(team.combined_package_filename),
    }


def project_team_data(db: Session, team: ProjectTeam) -> dict:
    project = db.get(Project, team.project_id)
    members = list(db.scalars(select(ProjectTeamMember).where(
        ProjectTeamMember.team_id == team.id
    ).order_by(ProjectTeamMember.id)).all())
    member_rows = []
    for member in members:
        student = db.get(User, member.user_id)
        assignment = db.get(Assignment, member.assignment_id)
        tasks = project_tasks(db, assignment.project_id)
        passed = len(completed_task_ids(db, assignment.id).intersection({item.id for item in tasks}))
        member_rows.append({
            "student": public_user(student),
            "track": member.track,
            "assignment_id": assignment.id,
            "passed_tasks": passed,
            "total_tasks": len(tasks),
            "progress": round(passed / len(tasks) * 100) if tasks else 0,
            "completed": certificate_ready(db, assignment),
        })
    return {
        "id": team.id,
        "name": team.name,
        "college_name": team.college_name,
        "project": project_data(project),
        "coordinator_id": team.coordinator_id,
        "status": team.status,
        "members": member_rows,
        "combined_package_ready": bool(team.combined_package_filename),
        "completed_at": team.completed_at,
    }


def final_project_requirements(
    db: Session, project: Project, assignment: Assignment
) -> tuple[list[str], list[str]]:
    required_paths: list[str] = []
    local_checks: list[str] = []
    for task in project_tasks(db, project.id):
        task_paths, task_checks = task_project_requirements(project, assignment, task)
        required_paths.extend(task_paths)
        local_checks.extend(task_checks)
    return list(dict.fromkeys(required_paths)), list(dict.fromkeys(local_checks))


def save_source_snapshot(contents: dict[str, str], prefix: str) -> str:
    filename = f"{prefix}_{uuid.uuid4().hex}.zip"
    (settings.upload_dir / filename).write_bytes(source_snapshot_zip(contents))
    return filename


def judge_run_data(run: JudgeRun | None) -> dict | None:
    if not run:
        return None
    diagnostics = []
    for index, result in enumerate(run.results or [], start=1):
        detail = result.get("compile_output") or result.get("stderr") or result.get("message") or ""
        diagnostics.append({
            "case": index, "status": result.get("status", "Unknown"),
            "time": result.get("time"), "memory": result.get("memory"),
            "diagnostic": detail[:1_000],
        })
    return {
        "id": run.id, "language": run.language, "status": run.status,
        "file_names": run.file_names or [], "source_hash": run.source_hash,
        "required_file_hashes": run.required_file_hashes or {},
        "local_check_results": run.local_check_results or [],
        "project_validation": run.project_validation_details or {},
        "similarity_flagged": run.similarity_flagged,
        "explanation": run.explanation,
        "total_cases": run.total_cases, "passed_cases": run.passed_cases,
        "results": diagnostics, "created_at": run.created_at,
    }


def attendance_data(item: Attendance | None) -> dict | None:
    if not item:
        return None
    return {
        "id": item.id, "attendance_date": item.attendance_date, "check_in_at": item.check_in_at,
        "check_out_at": item.check_out_at, "work_minutes": item.work_minutes,
        "status": item.status, "notes": item.notes,
    }


def attendance_summary(db: Session, user_id: int) -> dict:
    records = list(db.scalars(select(Attendance).where(Attendance.user_id == user_id).order_by(Attendance.attendance_date.desc())).all())
    tracked = [item for item in records if item.status in {"PRESENT", "HALF_DAY", "ABSENT"}]
    present = sum(1 for item in tracked if item.status in {"PRESENT", "HALF_DAY"})
    percentage = round(present / len(tracked) * 100) if tracked else 0
    today = datetime.now(INDIA_TZ).date()
    current = next((item for item in records if item.attendance_date == today), None)
    return {
        "today": attendance_data(current), "percentage": percentage,
        "present_days": present, "tracked_days": len(tracked),
        "recent": [attendance_data(item) for item in records[:14]],
    }


def mou_is_active(mou: MouAccess | None) -> bool:
    today = datetime.now(INDIA_TZ).date()
    return bool(mou and mou.active and mou.starts_on <= today <= mou.ends_on)


def mou_for_coordinator(db: Session, coordinator_id: int | None) -> MouAccess | None:
    if not coordinator_id:
        return None
    return db.scalar(select(MouAccess).where(MouAccess.coordinator_id == coordinator_id))


def mou_data(db: Session, mou: MouAccess | None) -> dict | None:
    if not mou:
        return None
    used = db.scalar(select(func.count(User.id)).where(
        User.role == "student", User.enrollment_type == "COLLEGE",
        User.college_seat_active.is_(True), User.coordinator_id == mou.coordinator_id
    )) or 0
    provisioned = db.scalar(select(func.count(User.id)).where(
        User.role == "student", User.enrollment_type == "COLLEGE",
        User.active.is_(True), User.coordinator_id == mou.coordinator_id
    )) or 0
    return {
        "id": mou.id, "coordinator_id": mou.coordinator_id, "college_name": mou.college_name,
        "mou_number": mou.mou_number, "student_limit": mou.student_limit, "used_seats": used,
        "provisioned_accounts": provisioned,
        "available_seats": max(0, mou.student_limit - used),
        "allowed_project_ids": mou.allowed_project_ids or [],
        "starts_on": mou.starts_on, "ends_on": mou.ends_on,
        "active": mou.active, "currently_valid": mou_is_active(mou),
    }


def college_access_for_student(db: Session, user: User) -> dict:
    if user.enrollment_type != "COLLEGE":
        return {"allowed": True, "reason": None, "allowed_project_ids": []}
    if not user.coordinator_id:
        return {"allowed": False, "reason": "Your college MOU access has not been assigned by Admin."}
    coordinator = db.get(User, user.coordinator_id)
    mou = mou_for_coordinator(db, user.coordinator_id)
    if not coordinator or coordinator.role != "coordinator" or not mou:
        return {"allowed": False, "reason": "College Coordinator MOU access is not configured."}
    if coordinator.college_name.casefold() != (user.college_name or "").casefold():
        return {"allowed": False, "reason": "Student college does not match the Coordinator MOU."}
    if not user.college_seat_active and not mou_is_active(mou):
        return {"allowed": False, "reason": "The college MOU is inactive, not started or expired for new student activations."}
    if not user.college_seat_active:
        return {"allowed": False, "reason": "Log in with the Admin-provided credential to activate your college seat."}
    data = mou_data(db, mou)
    return {"allowed": True, "reason": None, **data}


def matching_coordinator_id(db: Session, college_name: str) -> int | None:
    mous = list(db.scalars(select(MouAccess).where(
        func.lower(MouAccess.college_name) == college_name.strip().lower()
    )).all())
    for mou in mous:
        data = mou_data(db, mou)
        if mou_is_active(mou) and data["used_seats"] < mou.student_limit:
            return mou.coordinator_id
    return None


def activate_college_seat(db: Session, user: User) -> None:
    if user.enrollment_type != "COLLEGE" or user.college_seat_active:
        return
    mou = mou_for_coordinator(db, user.coordinator_id)
    if not mou_is_active(mou):
        raise HTTPException(status_code=403, detail="New student activation is blocked because the college MOU is not currently active")
    access = mou_data(db, mou)
    if access["used_seats"] >= mou.student_limit:
        raise HTTPException(status_code=409, detail="This college has reached its Admin-approved student limit")
    user.college_seat_active = True
    audit(db, user.id, "COLLEGE_SEAT_ACTIVATED", "user", user.id, college=user.college_name)


def _email_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:40] or "college"


def sync_college_accounts(db: Session, mou: MouAccess, email_prefix: str = "student") -> list[dict]:
    """Provision up to the MOU limit and disable only unused excess accounts.

    New accounts share a one-time batch password and must change it on first
    login. The plaintext is returned once to Admin for the credential sheet.
    """
    accounts = list(db.scalars(select(User).where(
        User.role == "student", User.enrollment_type == "COLLEGE",
        User.coordinator_id == mou.coordinator_id,
    ).order_by(User.id)).all())
    enabled = [item for item in accounts if item.active]
    credentials: list[dict] = []
    if len(enabled) > mou.student_limit:
        removable = [item for item in reversed(enabled) if not item.college_seat_active and not item.project_id]
        needed = len(enabled) - mou.student_limit
        if len(removable) < needed:
            raise HTTPException(status_code=409, detail="Student limit cannot be below active or assigned college students")
        for item in removable[:needed]:
            item.active = False
            audit(db, mou.created_by_id, "UNUSED_COLLEGE_ACCOUNT_DISABLED", "user", item.id)
        return credentials

    needed = mou.student_limit - len(enabled)
    if needed <= 0:
        return credentials
    disabled = [item for item in accounts if not item.active and not item.college_seat_active and not item.project_id]
    for item in disabled[:needed]:
        item.active = True
        needed -= 1
    if needed <= 0:
        return credentials

    batch_password = f"Gaint@{secrets.token_hex(4)}"
    password_hash = hash_password(batch_password)
    college_slug = _email_slug(mou.college_name)
    next_number = len(accounts) + 1
    for _ in range(needed):
        while True:
            email = f"{email_prefix.lower()}{next_number:03d}.{college_slug}@students.gaintclout.com"
            next_number += 1
            if not db.scalar(select(User.id).where(User.email == email)):
                break
        student = User(
            name=f"{mou.college_name} Student {next_number - 1:03d}", email=email,
            password_hash=password_hash, role="student", enrollment_type="COLLEGE",
            college_name=mou.college_name, coordinator_id=mou.coordinator_id,
            must_change_password=True, email_verified=True, mobile_verified=True,
            active=True, college_seat_active=False,
        )
        db.add(student)
        db.flush()
        credentials.append({"student_id": student.id, "name": student.name, "email": email, "temporary_password": batch_password})
        audit(db, mou.created_by_id, "COLLEGE_CREDENTIAL_CREATED", "user", student.id, college=mou.college_name)
    return credentials


def learning_info(user: User) -> dict:
    # Internship type controls the number/depth of milestones, not an artificial
    # waiting timer. Students can begin the first task immediately after access.
    return {"required_days": LEARNING_DAYS.get(user.internship_type or "FASTTRACK", 0), "completed": True, "days_remaining": 0}


def task_unlocked(user: User, assignment: Assignment, task: Task, tasks: list[Task], completed: set[int]) -> bool:
    if not learning_info(user)["completed"]:
        return False
    if task.order_no == 1:
        return True
    previous = next((item for item in tasks if item.order_no == task.order_no - 1), None)
    return bool(previous and previous.id in completed)


def task_project_requirements(project: Project, assignment: Assignment, task: Task) -> tuple[list[str], list[str]]:
    metadata = project.stack_metadata or {}
    path_map = metadata.get("track_required_paths") or {}
    check_map = metadata.get("track_local_checks") or {}
    required_paths = path_map.get(assignment.selected_track) or task.required_paths or []
    local_checks = check_map.get(assignment.selected_track)
    if local_checks is None:
        local_checks = task.local_checks or []
    return list(dict.fromkeys(required_paths)), list(dict.fromkeys(local_checks))


def task_checkpoint(project: Project, assignment: Assignment, task: Task) -> tuple[str, str]:
    base_language = {
        "Python": "python", "Django": "python", "Java": "java",
        "Node.js": "javascript", "Next.js": "javascript",
    }[project.technology]
    language = (project.stack_metadata or {}).get("track_languages", {}).get(
        assignment.selected_track,
        base_language,
    )
    extension = {"python": "py", "javascript": "js", "java": "java"}[language]
    return language, f"gaint_checkpoints/task_{task.order_no}.{extension}"


def task_list_data(db: Session, user: User, assignment: Assignment) -> tuple[list[dict], int]:
    project = db.get(Project, assignment.project_id)
    tasks = project_tasks(db, assignment.project_id)
    completed = completed_task_ids(db, assignment.id)
    result = []
    for task in tasks:
        judge_run = latest_judge_run(db, assignment.id, task.id)
        sample = next((case for case in (task.judge0_cases or []) if case.get("visible")), None)
        unlocked = task_unlocked(user, assignment, task, tasks, completed)
        required_paths, local_checks = task_project_requirements(project, assignment, task)
        _, checkpoint_file = task_checkpoint(project, assignment, task)
        result.append({
            "id": task.id, "order_no": task.order_no, "title": task.title,
            "description": task.description if unlocked else "",
            "deliverables": task.deliverables if unlocked else [],
            "acceptance_criteria": task.acceptance_criteria if unlocked else [],
            "visible_tests": task.visible_tests if unlocked else [],
            "required_paths": required_paths if unlocked else [],
            "local_checks": local_checks if unlocked else [],
            "checkpoint_file": checkpoint_file if unlocked else "",
            "challenge_prompt": task.challenge_prompt if unlocked else "",
            "judge0_sample": (
                {"stdin": sample.get("stdin"), "expected_output": sample.get("expected_output")}
                if sample and unlocked else None
            ),
            "judge0": judge_run_data(judge_run),
            "unlocked": unlocked,
            "status": "PASSED" if task.id in completed else (judge_run.status if judge_run else "NOT_STARTED"),
        })
    return result, len(completed.intersection({task.id for task in tasks}))


def all_tasks_submitted(db: Session, assignment: Assignment) -> bool:
    tasks = project_tasks(db, assignment.project_id)
    return bool(tasks) and len(completed_task_ids(db, assignment.id).intersection({t.id for t in tasks})) == len(tasks)


def certificate_ready(db: Session, assignment: Assignment) -> bool:
    validation = assignment_validation(db, assignment.id)
    return bool(
        all_tasks_submitted(db, assignment)
        and validation
        and validation.status == "PASSED"
        and validation.validated_at
        and validation.final_snapshot_filename
        and assignment.completion_packaged_at
        and assignment.completion_package_hash
    )


def assignment_data(db: Session, assignment: Assignment) -> dict:
    project = db.get(Project, assignment.project_id)
    user = db.get(User, assignment.user_id)
    tasks, passed = task_list_data(db, user, assignment)
    validation = assignment_validation(db, assignment.id)
    final_required_paths, final_local_checks = final_project_requirements(db, project, assignment)
    return {
        "id": assignment.id, "student": public_user(user), "project": project_data(project, len(tasks)),
        "variant_title": assignment.variant_title, "variant_brief": assignment.variant_brief,
        "variant_seed": assignment.variant_seed, "selected_track": assignment.selected_track,
        "status": assignment.status, "enrollment_state": assignment_enrollment_state(assignment),
        "access_ends_at": assignment.access_ends_at, "grace_ends_at": assignment.grace_ends_at,
        "student_guide_acknowledged": bool(assignment.student_guide_acknowledged_at),
        "tasks": tasks, "passed_tasks": passed, "approved_tasks": passed,
        "all_tasks_passed": bool(tasks) and passed == len(tasks),
        "all_tasks_submitted": bool(tasks) and passed == len(tasks),
        "project_fingerprint": assignment.project_fingerprint,
        "completion_package_name": assignment.completion_package_name,
        "completion_package_hash": assignment.completion_package_hash,
        "completion_packaged_at": assignment.completion_packaged_at,
        "project_validation": {
            "status": validation.status if validation else "PENDING",
            "failure_reason": validation.failure_reason if validation else None,
            "details": validation.final_details if validation else {},
            "validated_at": validation.validated_at if validation else None,
        },
        "final_required_paths": final_required_paths,
        "final_local_checks": final_local_checks,
        "team": team_data(db, assignment.id),
        "access_enabled": assignment_access_allowed(db, assignment, user),
        "payment": payment_data(assignment_payment(db, assignment.id)),
        "certificate_ready": certificate_ready(db, assignment),
    }


def issue_certificate(db: Session, user: User, assignment: Assignment) -> Certificate:
    certificate = db.scalar(select(Certificate).where(Certificate.user_id == user.id))
    if not certificate:
        certificate = Certificate(
            user_id=user.id,
            certificate_no=f"GAINT-{utcnow():%Y}-{user.id:05d}-{uuid.uuid4().hex[:6].upper()}",
        )
        db.add(certificate)
        db.commit()
        db.refresh(certificate)
    return certificate


@app.get("/")
def root():
    return {"app": settings.app_name, "version": "8.1.0", "status": "running"}


@app.get("/api/health")
def health():
    return {"status": "healthy"}


@app.get("/api/judge0/health")
def judge_health(_: User = Depends(get_current_user)):
    return judge0_health()


@app.get("/api/meta")
def meta():
    return {"technologies": sorted(TECHNOLOGIES), "internship_types": sorted(INTERNSHIP_TYPES), "task_counts": TASK_COUNTS}


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
async def register(
    name: str = Form(...), email: str = Form(...), mobile: str = Form(...), password: str = Form(...),
    internship_type: str = Form(...), pursuing_year: str | None = Form(None),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    internship_type = internship_type.strip().upper()
    if len(name.strip()) < 2 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=400, detail="Enter a valid name and email")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must contain at least 8 characters")
    if internship_type not in INTERNSHIP_TYPES:
        raise HTTPException(status_code=400, detail="Invalid internship type")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account already exists for this email")
    user = User(
        name=name.strip(), email=email, mobile=mobile.strip(), password_hash=hash_password(password),
        role="student", enrollment_type="INDIVIDUAL", pursuing_year=(pursuing_year or "").strip() or None,
        internship_type=internship_type, email_verified=False, mobile_verified=False,
    )
    db.add(user)
    audit(db, None, "INDIVIDUAL_REGISTERED", "user", None, email=email)
    db.commit()
    db.refresh(user)
    return {"token": create_token(user.id, user.role), "user": public_user(user)}


@app.post("/api/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.active:
        raise HTTPException(status_code=403, detail="This account is disabled")
    if payload.role and payload.role.lower() != user.role:
        raise HTTPException(status_code=403, detail=f"This account is registered as {user.role}")
    if user.role == "student" and user.enrollment_type == "COLLEGE":
        activate_college_seat(db, user)
        db.commit()
    audit(db, user.id, "LOGIN", "user", user.id, role=user.role)
    db.commit()
    return {"token": create_token(user.id, user.role), "user": public_user(user)}


@app.get("/api/me")
def me(user: User = Depends(get_current_user)):
    return public_user(user)


@app.post("/api/auth/change-password")
def change_password(payload: ChangePasswordRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="Choose a different new password")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    audit(db, user.id, "PASSWORD_CHANGED", "user", user.id)
    db.commit()
    return public_user(user)


@app.put("/api/student/preferences")
def update_preferences(payload: PreferencesRequest, user: User = Depends(require_role("student")), db: Session = Depends(get_db)):
    if user.must_change_password:
        raise HTTPException(status_code=403, detail="Change the temporary password before continuing")
    user.preferred_language = payload.preferred_language
    user.area_interest = payload.area_interest.strip()
    if payload.internship_type:
        if user.project_id and user.internship_type != payload.internship_type:
            raise HTTPException(status_code=409, detail="Internship type cannot change after selecting a project")
        user.internship_type = payload.internship_type
    db.commit()
    db.refresh(user)
    return public_user(user)


@app.get("/api/student/projects")
def suggested_projects(user: User = Depends(require_role("student")), db: Session = Depends(get_db)):
    if not user.preferred_language or not user.internship_type:
        raise HTTPException(status_code=409, detail="Save internship type and technology first")
    query = select(Project).where(
        Project.active.is_(True), Project.status == "PUBLISHED",
        Project.technology == user.preferred_language,
        Project.internship_type == user.internship_type,
    )
    if user.enrollment_type == "COLLEGE":
        access = college_access_for_student(db, user)
        if not access["allowed"]:
            raise HTTPException(status_code=403, detail=access["reason"])
        query = query.where(Project.id.in_(access["allowed_project_ids"]))
    projects = db.scalars(query.order_by(Project.generated, Project.title)).all()
    return [project_data(project, db.scalar(select(func.count(Task.id)).where(Task.project_id == project.id)) or 0) for project in projects]


@app.post("/api/student/projects/{project_id}/select")
def select_project(
    project_id: int,
    payload: ProjectSelectRequest | None = None,
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project or not project.active or project.status != "PUBLISHED":
        raise HTTPException(status_code=404, detail="Project not found")
    if user.enrollment_type == "COLLEGE":
        access = college_access_for_student(db, user)
        if not access["allowed"] or project.id not in access.get("allowed_project_ids", []):
            raise HTTPException(status_code=403, detail="This project is not included in your college MOU access")
    if project.technology != user.preferred_language or project.internship_type != user.internship_type:
        raise HTTPException(status_code=400, detail="Project does not match your technology or internship type")
    existing = get_assignment(db, user.id)
    if existing:
        if existing.project_id == project.id:
            return {"message": "Project already selected", "assignment_id": existing.id}
        raise HTTPException(status_code=409, detail="Project cannot be changed after assignment")
    available_tracks = project.available_tracks or ["FULL_STACK"]
    selected_track = payload.selected_track if payload and payload.selected_track else available_tracks[0]
    if selected_track not in available_tracks:
        raise HTTPException(status_code=400, detail="The selected track is not available for this project")
    variant_title, variant_brief, seed = personalised_variant(user.id, project.title, project.domain)
    starts_at = utcnow()
    access_ends_at = starts_at + timedelta(days=INTERNSHIP_DAYS[user.internship_type])
    grace_ends_at = access_ends_at + timedelta(days=GRACE_DAYS[user.internship_type])
    assignment = Assignment(
        user_id=user.id, project_id=project.id, variant_title=variant_title,
        variant_brief=variant_brief, variant_seed=seed, selected_track=selected_track,
        access_ends_at=access_ends_at, grace_ends_at=grace_ends_at,
        access_status="PAYMENT_PENDING" if user.enrollment_type == "INDIVIDUAL" else "ACTIVE",
    )
    user.project_id = project.id
    user.learning_started_at = utcnow()
    db.add(assignment)
    db.flush()
    if user.enrollment_type == "INDIVIDUAL":
        db.add(Payment(
            user_id=user.id, assignment_id=assignment.id, project_id=project.id,
            amount_rupees=project.individual_fee_rupees, provider=settings.payment_provider,
            provider_order_id=(
                f"GAINT-ORDER-{assignment.id}-{uuid.uuid4().hex[:8].upper()}"
                if settings.payment_provider == "demo" else None
            ),
        ))
    audit(db, user.id, "PROJECT_SELECTED", "project", project.id, enrollment_type=user.enrollment_type)
    db.commit()
    db.refresh(assignment)
    return {
        "message": "Project selected. Complete the one-time project payment to start." if user.enrollment_type == "INDIVIDUAL" else "Personalised college project assigned",
        "assignment_id": assignment.id,
    }


@app.post("/api/student/payments/{payment_id}/demo-confirm")
def confirm_demo_payment(
    payment_id: int, payload: PaymentConfirmRequest,
    user: User = Depends(require_role("student")), db: Session = Depends(get_db),
):
    if settings.payment_provider != "demo":
        raise HTTPException(status_code=404, detail="Demo payment confirmation is disabled")
    if user.enrollment_type != "INDIVIDUAL":
        raise HTTPException(status_code=403, detail="College internships do not require payment")
    payment = db.get(Payment, payment_id)
    if not payment or payment.user_id != user.id:
        raise HTTPException(status_code=404, detail="Payment not found")
    if not payload.terms_accepted:
        raise HTTPException(
            status_code=400,
            detail="Accept that payment provides project access and evaluation; certification requires every task to pass",
        )
    if payment.status != "PAID":
        payment.provider = "demo"
        payment.policy_accepted_at = utcnow()
        activate_paid_assignment(
            db,
            payment,
            provider_payment_id=f"DEMO-{uuid.uuid4().hex[:12].upper()}",
            audit_action="DEMO_PAYMENT_CONFIRMED",
        )
        db.commit()
        db.refresh(payment)
    return payment_data(payment)


@app.post("/api/student/payments/{payment_id}/razorpay/order")
def create_student_razorpay_order(
    payment_id: int,
    payload: PaymentConfirmRequest,
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
):
    if settings.payment_provider != "razorpay":
        raise HTTPException(status_code=404, detail="Razorpay payments are disabled")
    if user.enrollment_type != "INDIVIDUAL":
        raise HTTPException(status_code=403, detail="College internships do not require payment")
    payment = db.get(Payment, payment_id)
    if not payment or payment.user_id != user.id:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status == "PAID":
        raise HTTPException(status_code=409, detail="This project payment is already complete")
    if not payload.terms_accepted:
        raise HTTPException(
            status_code=400,
            detail="Accept that payment provides project access; certification requires every task to pass",
        )
    project = db.get(Project, payment.project_id)
    if not project:
        raise HTTPException(status_code=409, detail="Payment project no longer exists")
    if not payment.provider_order_id or not payment.provider_order_id.startswith("order_"):
        try:
            order = create_razorpay_order(
                amount_rupees=payment.amount_rupees,
                currency=payment.currency,
                receipt=f"gaint-payment-{payment.id}",
                notes={
                    "payment_id": str(payment.id),
                    "student_id": str(user.id),
                    "project_id": str(payment.project_id),
                },
            )
        except RazorpayError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        order_id = str(order.get("id", ""))
        if not order_id.startswith("order_"):
            raise HTTPException(status_code=502, detail="Razorpay did not return a valid order")
        payment.provider = "razorpay"
        payment.provider_order_id = order_id
    payment.policy_accepted_at = payment.policy_accepted_at or utcnow()
    db.commit()
    return {
        "key_id": settings.razorpay_key_id,
        "order_id": payment.provider_order_id,
        "amount": payment.amount_rupees * 100,
        "currency": payment.currency,
        "business_name": settings.app_name,
        "description": project.title,
        "prefill": {"name": user.name, "email": user.email, "contact": user.mobile or ""},
    }


@app.post("/api/student/payments/{payment_id}/razorpay/verify")
def verify_student_razorpay_payment(
    payment_id: int,
    payload: RazorpayVerifyRequest,
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
):
    if settings.payment_provider != "razorpay":
        raise HTTPException(status_code=404, detail="Razorpay payments are disabled")
    payment = db.get(Payment, payment_id)
    if not payment or payment.user_id != user.id:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status == "PAID":
        return payment_data(payment)
    if not payment.policy_accepted_at:
        raise HTTPException(status_code=400, detail="Payment policy was not accepted")
    if payload.razorpay_order_id != payment.provider_order_id:
        raise HTTPException(status_code=400, detail="Payment order does not match")
    try:
        valid_signature = verify_checkout_signature(
            order_id=payment.provider_order_id,
            payment_id=payload.razorpay_payment_id,
            signature=payload.razorpay_signature,
        )
    except RazorpayError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not valid_signature:
        raise HTTPException(status_code=400, detail="Razorpay payment signature is invalid")
    try:
        provider_payment = fetch_razorpay_payment(payload.razorpay_payment_id)
    except RazorpayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if (
        provider_payment.get("order_id") != payment.provider_order_id
        or int(provider_payment.get("amount", 0)) != payment.amount_rupees * 100
        or provider_payment.get("currency") != payment.currency
    ):
        raise HTTPException(status_code=400, detail="Razorpay payment details do not match this project")
    if provider_payment.get("status") != "captured":
        raise HTTPException(
            status_code=409,
            detail="Payment is not captured yet. Enable automatic capture in Razorpay and try verification again.",
        )
    activate_paid_assignment(
        db,
        payment,
        provider_payment_id=payload.razorpay_payment_id,
        audit_action="RAZORPAY_PAYMENT_VERIFIED",
    )
    db.commit()
    db.refresh(payment)
    return payment_data(payment)


@app.post("/api/payments/razorpay/webhook")
async def receive_razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(default=""),
    x_razorpay_event_id: str = Header(default=""),
    db: Session = Depends(get_db),
):
    raw_body = await request.body()
    try:
        if not verify_webhook_signature(raw_body=raw_body, signature=x_razorpay_signature):
            raise HTTPException(status_code=400, detail="Invalid Razorpay webhook signature")
    except RazorpayError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        event = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid Razorpay webhook body") from exc
    event_name = event.get("event")
    event_id = x_razorpay_event_id.strip() or hashlib.sha256(raw_body).hexdigest()
    if db.scalar(select(PaymentWebhookEvent.id).where(
        PaymentWebhookEvent.event_id == event_id
    )):
        return {"accepted": True, "processed": False, "duplicate": True}
    webhook_event = PaymentWebhookEvent(
        provider="razorpay",
        event_id=event_id,
        event_name=str(event_name or "unknown")[:100],
    )
    db.add(webhook_event)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return {"accepted": True, "processed": False, "duplicate": True}
    if event_name not in {"payment.captured", "order.paid"}:
        webhook_event.processed = True
        db.commit()
        return {"accepted": True, "processed": False}
    payload = event.get("payload") or {}
    payment_entity = ((payload.get("payment") or {}).get("entity") or {})
    order_entity = ((payload.get("order") or {}).get("entity") or {})
    provider_order_id = payment_entity.get("order_id") or order_entity.get("id")
    payment = db.scalar(select(Payment).where(Payment.provider_order_id == provider_order_id))
    if not payment:
        webhook_event.processed = True
        db.commit()
        return {"accepted": True, "processed": False}
    amount = payment_entity.get("amount") or order_entity.get("amount_paid")
    currency = payment_entity.get("currency") or order_entity.get("currency")
    if int(amount or 0) != payment.amount_rupees * 100 or currency != payment.currency:
        raise HTTPException(status_code=400, detail="Webhook payment details do not match")
    was_paid = payment.status == "PAID"
    activate_paid_assignment(
        db,
        payment,
        provider_payment_id=payment_entity.get("id") or payment.provider_payment_id or provider_order_id,
        audit_action="RAZORPAY_WEBHOOK_CONFIRMED",
    )
    if x_razorpay_event_id:
        audit(
            db,
            payment.user_id,
            "RAZORPAY_WEBHOOK_RECEIVED",
            "payment",
            payment.id,
            event_id=x_razorpay_event_id,
            event=event_name,
        )
    webhook_event.processed = True
    db.commit()
    return {"accepted": True, "processed": not was_paid}


@app.get("/api/student/guide")
def student_guide(user: User = Depends(require_role("student")), db: Session = Depends(get_db)):
    assignment = get_assignment(db, user.id)
    if not assignment or not assignment_access_allowed(db, assignment, user):
        raise HTTPException(status_code=403, detail="Select an accessible project before opening the Student Guide")
    project = db.get(Project, assignment.project_id)
    return {
        "title": "Read this guide before Task 1",
        "acknowledged": bool(assignment.student_guide_acknowledged_at),
        "project": assignment.variant_title,
        "technology": project.technology,
        "track": assignment.selected_track,
        "steps": [
            "Install Visual Studio Code once from code.visualstudio.com/download",
            "Download the project ZIP and use Extract All; never work inside the ZIP",
            "Double-click OPEN_IN_VSCODE.bat; it installs the GAINT extension and opens the correct folder",
            "Read CURRENT_TASK.md and the red Current Task Question before writing code",
            "Test the required checkpoint and real project modules in the VS Code terminal",
            "Press Ctrl+Shift+P and run GAINT: Submit Current Task; no token, Task ID or Git is required",
            "Correct failed checks and resubmit; a pass unlocks the next task automatically",
            "After every task passes, receive the certificate and clean runnable ZIP",
        ],
    }


@app.post("/api/student/guide/acknowledge")
def acknowledge_student_guide(
    user: User = Depends(require_role("student")), db: Session = Depends(get_db),
):
    assignment = get_assignment(db, user.id)
    if not assignment or not assignment_access_allowed(db, assignment, user):
        raise HTTPException(status_code=403, detail="Project access is not active")
    assignment.student_guide_acknowledged_at = assignment.student_guide_acknowledged_at or utcnow()
    audit(db, user.id, "STUDENT_GUIDE_ACKNOWLEDGED", "assignment", assignment.id)
    db.commit()
    return {"acknowledged": True}


def create_workspace_bootstrap(db: Session, user: User, assignment: Assignment) -> str:
    raw = f"gaint_boot_{secrets.token_urlsafe(32)}"
    configured_expiry = utcnow() + timedelta(minutes=settings.workspace_bootstrap_minutes)
    # Keep automatic repair available for the complete internship/grace period.
    # The installed device token itself has no time expiry by default.
    expires_at = max(
        configured_expiry,
        assignment.grace_ends_at or assignment.access_ends_at or configured_expiry,
    )
    db.add(WorkspaceBootstrap(
        user_id=user.id,
        assignment_id=assignment.id,
        token_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        expires_at=expires_at,
    ))
    audit(db, user.id, "WORKSPACE_BOOTSTRAP_CREATED", "assignment", assignment.id)
    db.commit()
    return raw


@app.get("/api/student/dashboard")
def student_dashboard(user: User = Depends(require_role("student")), db: Session = Depends(get_db)):
    assignment = get_assignment(db, user.id)
    college_access = college_access_for_student(db, user)
    if not assignment:
        return {"user": public_user(user), "assignment": None, "learning": learning_info(user), "progress": 0, "attendance": attendance_summary(db, user.id) if user.enrollment_type == "COLLEGE" else None, "college_access": college_access}
    data = assignment_data(db, assignment)
    total = len(data["tasks"])
    return {"user": public_user(user), "assignment": data, "learning": learning_info(user), "progress": round(data["approved_tasks"] / total * 100) if total else 0, "attendance": attendance_summary(db, user.id) if user.enrollment_type == "COLLEGE" else None, "college_access": college_access}


@app.post("/api/student/attendance/check-in", status_code=201)
def student_check_in(user: User = Depends(require_role("student")), db: Session = Depends(get_db)):
    if user.enrollment_type != "COLLEGE":
        raise HTTPException(status_code=403, detail="Attendance is only used for college internships")
    today = datetime.now(INDIA_TZ).date()
    record = db.scalar(select(Attendance).where(Attendance.user_id == user.id, Attendance.attendance_date == today))
    if record and record.check_in_at:
        raise HTTPException(status_code=409, detail="Attendance check-in is already recorded for today")
    if not record:
        record = Attendance(user_id=user.id, attendance_date=today, status="PRESENT")
        db.add(record)
    record.check_in_at = utcnow()
    record.status = "PRESENT"
    db.commit()
    db.refresh(record)
    return attendance_data(record)


@app.post("/api/student/attendance/check-out")
def student_check_out(user: User = Depends(require_role("student")), db: Session = Depends(get_db)):
    if user.enrollment_type != "COLLEGE":
        raise HTTPException(status_code=403, detail="Attendance is only used for college internships")
    today = datetime.now(INDIA_TZ).date()
    record = db.scalar(select(Attendance).where(Attendance.user_id == user.id, Attendance.attendance_date == today))
    if not record or not record.check_in_at:
        raise HTTPException(status_code=409, detail="Check in before checking out")
    if record.check_out_at:
        raise HTTPException(status_code=409, detail="Attendance check-out is already recorded for today")
    record.check_out_at = utcnow()
    record.work_minutes = max(0, int((record.check_out_at - record.check_in_at).total_seconds() // 60))
    record.status = "PRESENT" if record.work_minutes >= 240 else "HALF_DAY"
    db.commit()
    db.refresh(record)
    return attendance_data(record)


@app.get("/api/student/attendance")
def student_attendance(user: User = Depends(require_role("student")), db: Session = Depends(get_db)):
    if user.enrollment_type != "COLLEGE":
        raise HTTPException(status_code=403, detail="Attendance is only used for college internships")
    return attendance_summary(db, user.id)


@app.get("/api/student/flow-status")
def flow_status(user: User = Depends(require_role("student")), db: Session = Depends(get_db)):
    assignment = get_assignment(db, user.id)
    preferences = bool(user.preferred_language and user.area_interest)
    learning = learning_info(user)
    if not preferences:
        stage = "preferences"
    elif user.enrollment_type == "COLLEGE" and not college_access_for_student(db, user)["allowed"]:
        stage = "college_access"
    elif not assignment:
        stage = "project_selection"
    elif not assignment_access_allowed(db, assignment, user):
        stage = "incomplete" if assignment_enrollment_state(assignment) == "INCOMPLETE" else "payment"
    elif not all_tasks_submitted(db, assignment):
        stage = "internship"
    elif not certificate_ready(db, assignment):
        stage = "final_validation"
    else:
        stage = "completed"
    return {"stage": stage, "internship": user.internship_type, "preferred_language": user.preferred_language, "project": user.project_id}


@app.get("/api/student/starter-project")
def download_starter(user: User = Depends(require_role("student")), db: Session = Depends(get_db)):
    assignment = get_assignment(db, user.id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Select a project first")
    if not assignment_access_allowed(db, assignment, user):
        raise HTTPException(status_code=402, detail="Complete and verify the project payment before downloading the starter")
    if not assignment.student_guide_acknowledged_at:
        raise HTTPException(status_code=409, detail="Read and acknowledge the Student Guide before downloading the project")
    project = db.get(Project, assignment.project_id)
    tasks = project_tasks(db, project.id)
    bootstrap = create_workspace_bootstrap(db, user, assignment)
    content, filename = starter_project_zip(user, project, assignment, tasks, bootstrap)
    validation = assignment_validation(db, assignment.id, create=True)
    validation.starter_hashes = snapshot_hashes_from_zip(content)
    validation.status = "PENDING"
    validation.failure_reason = None
    assignment.starter_downloaded_at = utcnow()
    db.commit()
    return Response(content=content, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/vscode/assignment")
def vscode_assignment(user: User = Depends(get_vscode_user), db: Session = Depends(get_db)):
    assignment = get_assignment(db, user.id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Select a project in GAINT Interns Hub first")
    if not assignment_access_allowed(db, assignment, user):
        raise HTTPException(status_code=403, detail="Project access is not active")
    return assignment_data(db, assignment)


@app.post("/api/vscode/bootstrap", status_code=201)
def bootstrap_vscode_workspace(payload: WorkspaceBootstrapRequest, db: Session = Depends(get_db)):
    token_hash = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()
    bootstrap = db.scalar(select(WorkspaceBootstrap).where(
        WorkspaceBootstrap.token_hash == token_hash,
    ))
    if not bootstrap or bootstrap.expires_at < utcnow():
        raise HTTPException(status_code=401, detail="Workspace connection expired; download a fresh starter")
    assignment = db.get(Assignment, bootstrap.assignment_id)
    user = db.get(User, bootstrap.user_id)
    if not assignment or not user or not assignment_access_allowed(db, assignment, user):
        raise HTTPException(status_code=403, detail="Project access is not active")
    raw = f"gaint_vsc_{secrets.token_urlsafe(32)}"
    expires_at = (
        datetime.max.replace(microsecond=0)
        if settings.vscode_token_days <= 0
        else utcnow() + timedelta(days=settings.vscode_token_days)
    )
    db.add(DeviceToken(
        user_id=user.id,
        token_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        expires_at=expires_at,
        label=f"Workspace {assignment.id}",
    ))
    bootstrap.used_at = utcnow()
    audit(db, user.id, "WORKSPACE_CONNECTED", "assignment", assignment.id)
    db.commit()
    return {"token": raw, "expires_at": expires_at}


@app.post("/api/vscode/tasks/{task_id}/evaluate", status_code=201)
def submit_vscode_evaluation(
    task_id: int, payload: JudgeSubmitRequest,
    x_gaint_client: str | None = Header(None),
    user: User = Depends(get_vscode_user), db: Session = Depends(get_db),
):
    if x_gaint_client != "vscode-extension":
        raise HTTPException(status_code=403, detail="Task code can only be submitted through the GAINT VS Code extension")
    assignment = get_assignment(db, user.id)
    task = db.get(Task, task_id)
    if not assignment or not task or task.project_id != assignment.project_id:
        raise HTTPException(status_code=404, detail="Task not found")
    if not assignment_access_allowed(db, assignment, user):
        raise HTTPException(status_code=403, detail="Project access is not active")
    tasks = project_tasks(db, assignment.project_id)
    if not task_unlocked(user, assignment, task, tasks, completed_task_ids(db, assignment.id)):
        raise HTTPException(status_code=403, detail="This task is locked until the previous task passes")
    if task.id in completed_task_ids(db, assignment.id):
        raise HTTPException(status_code=409, detail="This task has already passed")
    project = db.get(Project, assignment.project_id)
    expected_language, expected_checkpoint = task_checkpoint(project, assignment, task)
    if payload.language != expected_language:
        raise HTTPException(status_code=400, detail=f"Use {expected_language} for this {project.technology} checkpoint")
    submitted_file = payload.file_name.replace("\\", "/").lstrip("./")
    if submitted_file != expected_checkpoint:
        raise HTTPException(status_code=400, detail=f"Open and submit the required task file: {expected_checkpoint}")
    cases = task.judge0_cases or []
    if not cases:
        raise HTTPException(status_code=409, detail="No Judge0 checkpoint is configured for this milestone")
    required_paths, required_local_checks = task_project_requirements(project, assignment, task)
    evidence_paths = [path.replace("\\", "/").lstrip("./") for path in payload.required_file_hashes]
    missing_paths = [
        required for required in required_paths
        if not any(path == required or path.startswith(required.rstrip("/") + "/") for path in evidence_paths)
    ]
    if missing_paths:
        raise HTTPException(
            status_code=400,
            detail=f"Required project modules were not found in the local evidence: {', '.join(missing_paths)}",
        )
    result_by_command = {
        str(item.get("command", "")).strip(): bool(item.get("passed"))
        for item in payload.local_check_results
    }
    failed_local_checks = [
        command for command in required_local_checks
        if not result_by_command.get(command, False)
    ]
    if failed_local_checks:
        raise HTTPException(
            status_code=400,
            detail=f"Required local checks must pass before Judge0: {', '.join(failed_local_checks)}",
        )
    validation = assignment_validation(db, assignment.id, create=True)
    try:
        source_hashes, validation_details = validate_source_snapshot(
            contents=payload.project_file_contents,
            declared_hashes=payload.required_file_hashes,
            required_paths=required_paths,
            baseline_hashes=validation.starter_hashes or {},
            previous_hashes=validation.last_source_hashes or {},
            # The checkpoint is the task submission. Keep validating project
            # evidence, but never require an unrelated README/source edit.
            require_change=False,
        )
    except ProjectValidationError as exc:
        validation.status = "FAILED"
        validation.failure_reason = str(exc)
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    snapshot_filename = save_source_snapshot(
        payload.project_file_contents,
        f"task_source_{assignment.id}_{task.id}",
    )
    source_hash = hashlib.sha256(payload.source_code.encode("utf-8")).hexdigest()
    similar = bool(db.scalar(select(JudgeRun.id).where(
        JudgeRun.source_hash == source_hash,
        JudgeRun.user_id != user.id,
    ).limit(1)))
    try:
        tokens = submit_tests(payload.source_code, payload.language, cases)
    except Judge0Error as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    run = JudgeRun(
        user_id=user.id, assignment_id=assignment.id, task_id=task.id,
        language=payload.language,
        source_hash=source_hash,
        file_names=[payload.file_name], explanation=payload.explanation.strip(),
        required_file_hashes=payload.required_file_hashes,
        local_check_results=payload.local_check_results,
        project_source_hashes=source_hashes,
        project_validation_details=validation_details,
        project_snapshot_filename=snapshot_filename,
        similarity_flagged=similar,
        judge_tokens=tokens, status="QUEUED", total_cases=len(cases), passed_cases=0,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return judge_run_data(run)


@app.get("/api/vscode/evaluations/{run_id}")
def vscode_evaluation_result(
    run_id: int, user: User = Depends(get_vscode_user), db: Session = Depends(get_db),
):
    run = db.get(JudgeRun, run_id)
    if not run or run.user_id != user.id:
        raise HTTPException(status_code=404, detail="Judge0 evaluation not found")
    if run.status in {"QUEUED", "PROCESSING"}:
        try:
            results = fetch_results(run.judge_tokens)
        except Judge0Error as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        pending = any(item["status_id"] in {1, 2} for item in results)
        passed = sum(1 for item in results if item["status_id"] == 3)
        run.results = results
        run.passed_cases = passed
        run.status = "PROCESSING" if pending else ("PASSED" if passed == run.total_cases else "FAILED")
        assignment = db.get(Assignment, run.assignment_id)
        if run.status == "PASSED" and assignment:
            validation = assignment_validation(db, assignment.id, create=True)
            validation.last_source_hashes = run.project_source_hashes or {}
            validation.status = "TASKS_PASSED" if all_tasks_submitted(db, assignment) else "IN_PROGRESS"
            validation.failure_reason = None
            member = assignment_team_member(db, assignment.id)
            if member and run.project_snapshot_filename:
                artifact = db.scalar(select(TeamArtifact).where(
                    TeamArtifact.team_id == member.team_id,
                    TeamArtifact.assignment_id == assignment.id,
                    TeamArtifact.task_id == run.task_id,
                ))
                if not artifact:
                    artifact = TeamArtifact(
                        team_id=member.team_id,
                        assignment_id=assignment.id,
                        task_id=run.task_id,
                        user_id=user.id,
                        track=member.track,
                        source_hashes=run.project_source_hashes or {},
                        snapshot_filename=run.project_snapshot_filename,
                    )
                    db.add(artifact)
                else:
                    artifact.source_hashes = run.project_source_hashes or {}
                    artifact.snapshot_filename = run.project_snapshot_filename
        db.commit()
        db.refresh(run)
    return judge_run_data(run)


@app.post("/api/vscode/final-fingerprint")
def save_project_fingerprint(
    payload: ProjectFingerprintRequest,
    user: User = Depends(get_vscode_user), db: Session = Depends(get_db),
):
    assignment = get_assignment(db, user.id)
    if not assignment or not all_tasks_submitted(db, assignment):
        raise HTTPException(status_code=403, detail="Every task must pass before the final local fingerprint is recorded")
    assignment.project_fingerprint = payload.fingerprint.lower()
    assignment.fingerprinted_at = utcnow()
    db.commit()
    return {"message": "Local project fingerprint recorded", "fingerprint": assignment.project_fingerprint}


@app.post("/api/vscode/final-package")
def record_completion_package(
    payload: CompletionPackageRequest,
    user: User = Depends(get_vscode_user),
    db: Session = Depends(get_db),
):
    assignment = get_assignment(db, user.id)
    if not assignment or not all_tasks_submitted(db, assignment):
        raise HTTPException(status_code=403, detail="Every task must pass before packaging the completed project")
    project = db.get(Project, assignment.project_id)
    required_paths, required_local_checks = final_project_requirements(db, project, assignment)
    result_by_command = {
        str(item.get("command", "")).strip(): bool(item.get("passed"))
        for item in payload.local_check_results
    }
    failed_local_checks = [
        command for command in required_local_checks
        if not result_by_command.get(command, False)
    ]
    validation = assignment_validation(db, assignment.id, create=True)
    if failed_local_checks:
        validation.status = "FAILED"
        validation.failure_reason = (
            "Final local checks failed or were not run: " + ", ".join(failed_local_checks)
        )
        db.commit()
        raise HTTPException(status_code=400, detail=validation.failure_reason)
    try:
        source_hashes, validation_details = validate_source_snapshot(
            contents=payload.project_file_contents,
            declared_hashes=payload.required_file_hashes,
            required_paths=required_paths,
            baseline_hashes=validation.starter_hashes or {},
            previous_hashes={},
            require_change=False,
        )
    except ProjectValidationError as exc:
        validation.status = "FAILED"
        validation.failure_reason = str(exc)
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    final_snapshot_filename = save_source_snapshot(
        payload.project_file_contents,
        f"final_source_{assignment.id}",
    )
    validation.final_source_hashes = source_hashes
    validation.final_check_results = payload.local_check_results
    validation.final_details = validation_details
    validation.final_snapshot_filename = final_snapshot_filename
    validation.status = "PASSED"
    validation.failure_reason = None
    validation.validated_at = utcnow()
    member = assignment_team_member(db, assignment.id)
    tasks = project_tasks(db, project.id)
    if member and tasks:
        final_task_id = tasks[-1].id
        artifact = db.scalar(select(TeamArtifact).where(
            TeamArtifact.team_id == member.team_id,
            TeamArtifact.assignment_id == assignment.id,
            TeamArtifact.task_id == final_task_id,
        ))
        if not artifact:
            artifact = TeamArtifact(
                team_id=member.team_id,
                assignment_id=assignment.id,
                task_id=final_task_id,
                user_id=user.id,
                track=member.track,
                source_hashes=source_hashes,
                snapshot_filename=final_snapshot_filename,
            )
            db.add(artifact)
        else:
            artifact.source_hashes = source_hashes
            artifact.snapshot_filename = final_snapshot_filename
    assignment.project_fingerprint = payload.fingerprint.lower()
    assignment.fingerprinted_at = utcnow()
    assignment.completion_package_name = payload.filename
    assignment.completion_package_hash = payload.fingerprint.lower()
    assignment.completion_packaged_at = utcnow()
    assignment.status = "COMPLETED"
    user.completed_at = user.completed_at or utcnow()
    certificate = issue_certificate(db, user, assignment)
    audit(db, user.id, "COMPLETION_PACKAGE_CREATED", "assignment", assignment.id, filename=payload.filename)
    db.commit()
    return {
        "message": "Completed project package recorded",
        "certificate_no": certificate.certificate_no,
        "filename": assignment.completion_package_name,
    }


@app.post("/api/student/ai/current-task")
def current_task_ai_assistance(
    payload: AiTaskRequest,
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
):
    assignment = get_assignment(db, user.id)
    if not assignment or not assignment_access_allowed(db, assignment, user):
        raise HTTPException(status_code=403, detail="Project access is not active")
    tasks = project_tasks(db, assignment.project_id)
    completed = completed_task_ids(db, assignment.id)
    task = next((item for item in tasks if task_unlocked(user, assignment, item, tasks, completed) and item.id not in completed), None)
    if not task:
        raise HTTPException(status_code=409, detail="No current task requires AI assistance")
    if payload.task_id is not None and payload.task_id != task.id:
        raise HTTPException(status_code=409, detail="Open the current unlocked task to request help")
    response_text = safe_task_assistance(task, payload.action, payload.error_message)
    db.add(AiInteraction(
        user_id=user.id,
        assignment_id=assignment.id,
        task_id=task.id,
        action=payload.action,
        prompt_summary=payload.error_message[:500],
        response_text=response_text,
    ))
    audit(db, user.id, "AI_TASK_ASSISTANCE", "task", task.id, assistance_action=payload.action)
    db.commit()
    return {
        "action": payload.action,
        "task_id": task.id,
        "response": response_text,
        "guardrail": "AI provides explanations and hints only; Judge0 and local checks decide PASS or FAIL.",
    }


def current_learning_task(db: Session, user: User) -> tuple[Assignment, Project, Task]:
    assignment = get_assignment(db, user.id)
    if not assignment or not assignment_access_allowed(db, assignment, user):
        raise HTTPException(status_code=403, detail="Select and activate a project before using the learning assistant")
    project = db.get(Project, assignment.project_id)
    tasks = project_tasks(db, assignment.project_id)
    completed = completed_task_ids(db, assignment.id)
    task = next(
        (item for item in tasks if task_unlocked(user, assignment, item, tasks, completed) and item.id not in completed),
        None,
    )
    if not task:
        raise HTTPException(status_code=409, detail="All project tasks are completed. Your certificate is ready.")
    return assignment, project, task


def ai_chat_turns(db: Session, user_id: int, assignment_id: int, task_id: int, limit: int = 30) -> list[AiInteraction]:
    return list(db.scalars(
        select(AiInteraction).where(
            AiInteraction.user_id == user_id,
            AiInteraction.assignment_id == assignment_id,
            AiInteraction.task_id == task_id,
            AiInteraction.action == "CHAT",
        ).order_by(AiInteraction.created_at.desc()).limit(limit)
    ).all())[::-1]


def ai_chat_message_data(item: AiInteraction) -> list[dict]:
    return [
        {"id": f"{item.id}-user", "role": "user", "text": item.prompt_summary, "created_at": item.created_at},
        {"id": f"{item.id}-assistant", "role": "assistant", "text": item.response_text, "created_at": item.created_at},
    ]


@app.get("/api/student/ai/chat/history")
def student_ai_chat_history(
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
):
    assignment, _, task = current_learning_task(db, user)
    turns = ai_chat_turns(db, user.id, assignment.id, task.id)
    messages = [message for turn in turns for message in ai_chat_message_data(turn)]
    recent_count = db.scalar(select(func.count(AuditLog.id)).where(
        AuditLog.actor_id == user.id,
        AuditLog.action == "AI_CHAT_MESSAGE",
        AuditLog.created_at >= utcnow() - timedelta(hours=24),
    )) or 0
    return {
        "task_id": task.id,
        "task_title": task.title,
        "messages": messages,
        "daily_limit": settings.ai_chat_daily_limit,
        "remaining_messages": max(0, settings.ai_chat_daily_limit - recent_count),
        "provider": "openai" if settings.ai_provider == "openai" and settings.openai_api_key else "safe-local",
        "guardrail": "Hints and explanations only. The assistant cannot provide complete answers, hidden tests, task passes or unlocks.",
    }


@app.post("/api/student/ai/chat")
def student_ai_chat(
    payload: AiChatRequest,
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
):
    assignment, project, task = current_learning_task(db, user)
    recent_count = db.scalar(select(func.count(AuditLog.id)).where(
        AuditLog.actor_id == user.id,
        AuditLog.action == "AI_CHAT_MESSAGE",
        AuditLog.created_at >= utcnow() - timedelta(hours=24),
    )) or 0
    if recent_count >= settings.ai_chat_daily_limit:
        raise HTTPException(
            status_code=429,
            detail=f"Daily learning-assistant limit reached ({settings.ai_chat_daily_limit}). Try again after 24 hours.",
        )
    turns = ai_chat_turns(db, user.id, assignment.id, task.id, limit=8)
    history = [{"question": item.prompt_summary, "response": item.response_text} for item in turns]
    response_text, provider = task_chat_assistance(
        task=task,
        project=project,
        assignment=assignment,
        message=payload.message,
        history=history,
        user_id=user.id,
    )
    interaction = AiInteraction(
        user_id=user.id,
        assignment_id=assignment.id,
        task_id=task.id,
        action="CHAT",
        prompt_summary=payload.message,
        response_text=response_text,
        provider=provider,
    )
    db.add(interaction)
    audit(db, user.id, "AI_CHAT_MESSAGE", "task", task.id, provider=provider)
    db.commit()
    db.refresh(interaction)
    return {
        "task_id": task.id,
        "task_title": task.title,
        "message": ai_chat_message_data(interaction)[1],
        "provider": provider,
        "remaining_messages": max(0, settings.ai_chat_daily_limit - recent_count - 1),
        "guardrail": "Judge0 and required local project checks alone decide PASS or FAIL.",
    }


@app.delete("/api/student/ai/chat/history", status_code=204)
def clear_student_ai_chat_history(
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
):
    assignment, _, task = current_learning_task(db, user)
    turns = ai_chat_turns(db, user.id, assignment.id, task.id, limit=10_000)
    for turn in turns:
        db.delete(turn)
    audit(db, user.id, "AI_CHAT_HISTORY_CLEARED", "task", task.id, messages=len(turns))
    db.commit()
    return Response(status_code=204)


@app.get("/api/student/certificate")
def download_certificate(user: User = Depends(require_role("student")), db: Session = Depends(get_db)):
    assignment = get_assignment(db, user.id)
    if not assignment or not certificate_ready(db, assignment):
        raise HTTPException(status_code=403, detail="Certificate is enabled automatically after every required task passes")
    project = db.get(Project, assignment.project_id)
    certificate = issue_certificate(db, user, assignment)
    pdf = build_certificate_pdf(
        name=user.name,
        project=assignment.variant_title,
        duration=project.internship_type.replace("_", " "),
        certificate_no=certificate.certificate_no,
        issued_date=certificate.issued_at.strftime("%d %B %Y"),
        verification_url=f"{settings.certificate_verify_base_url}/{certificate.certificate_no}",
        college=user.college_name or "Individual Internship",
        technology=project.technology,
        track=assignment.selected_track.replace("_", " ").title(),
        starts_on=(user.learning_started_at or assignment.created_at).strftime("%d %B %Y"),
        completed_on=(user.completed_at or certificate.issued_at).strftime("%d %B %Y"),
    )
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{certificate.certificate_no}.pdf"'})


@app.get("/api/student/evaluation-report")
def download_evaluation_report(user: User = Depends(require_role("student")), db: Session = Depends(get_db)):
    assignment = get_assignment(db, user.id)
    if not assignment or not certificate_ready(db, assignment):
        raise HTTPException(status_code=403, detail="Evaluation report is enabled automatically after every required task passes")
    attendance = attendance_summary(db, user.id) if user.enrollment_type == "COLLEGE" else {"percentage": None, "recent": []}
    pdf = build_evaluation_report_pdf(public_user(user), assignment_data(db, assignment), attendance)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="GAINT-{user.id}-Evaluation-Report.pdf"'},
    )


@app.get("/api/certificates/verify/{certificate_no}")
def verify_certificate(certificate_no: str, db: Session = Depends(get_db)):
    certificate = db.scalar(select(Certificate).where(Certificate.certificate_no == certificate_no))
    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")
    student = db.get(User, certificate.user_id)
    assignment = get_assignment(db, student.id)
    project = db.get(Project, assignment.project_id) if assignment else None
    return {
        "valid": bool(assignment and certificate_ready(db, assignment)),
        "certificate_no": certificate.certificate_no,
        "student": student.name,
        "college": student.college_name,
        "project": assignment.variant_title if assignment else None,
        "technology": project.technology if project else None,
        "project_fingerprint": assignment.project_fingerprint if assignment else None,
        "issued_at": certificate.issued_at,
    }


@app.get("/api/mentor/dashboard")
def mentor_dashboard(mentor: User = Depends(require_role("mentor")), db: Session = Depends(get_db)):
    # Mentors are GAINT company-wide aggregate analytics users. They do not
    # receive student-level review, viva, approval, pass or unlock controls.
    students = db.scalars(select(User).where(
        User.role == "student", User.active.is_(True),
        (User.enrollment_type == "INDIVIDUAL") | (User.college_seat_active.is_(True)),
    ).order_by(User.name)).all()
    assignments = [assignment for student in students if (assignment := get_assignment(db, student.id))]
    colleges = {
        student.college_name
        for student in students
        if student.enrollment_type == "COLLEGE" and student.college_name
    }
    technology_counts: dict[str, int] = {}
    period_counts: dict[str, int] = {}
    completed = 0
    for assignment in assignments:
        student = db.get(User, assignment.user_id)
        project = db.get(Project, assignment.project_id)
        technology = project.technology if project else None
        period = student.internship_type if student else None
        if technology:
            technology_counts[technology] = technology_counts.get(technology, 0) + 1
        if period:
            period_counts[period] = period_counts.get(period, 0) + 1
        if assignment.status == "COMPLETED":
            completed += 1
    active_mous = sum(1 for mou in db.scalars(select(MouAccess)).all() if mou_is_active(mou))
    return {
        "mentor": public_user(mentor),
        "summary": {
            "colleges": len(colleges),
            "active_mous": active_mous,
            "students": len(students),
            "college_students": sum(1 for item in students if item.enrollment_type == "COLLEGE"),
            "individual_students": sum(1 for item in students if item.enrollment_type == "INDIVIDUAL"),
            "started_projects": len(assignments),
            "in_progress": max(0, len(assignments) - completed),
            "completed": completed,
            "technologies": technology_counts,
            "periods": period_counts,
        },
        "permissions": {
            "analytics_only": True,
            "can_review_tasks": False,
            "can_unlock_tasks": False,
            "can_issue_certificate": False,
        },
    }


@app.get("/api/coordinator/dashboard")
def coordinator_dashboard(
    coordinator: User = Depends(require_role("coordinator")), db: Session = Depends(get_db),
):
    students = list(db.scalars(select(User).where(
        User.role == "student", User.enrollment_type == "COLLEGE", User.college_seat_active.is_(True),
        User.coordinator_id == coordinator.id
    ).order_by(User.name)).all())
    rows = []
    for student in students:
        assignment = get_assignment(db, student.id)
        assignment_payload = assignment_data(db, assignment) if assignment else None
        total = len(assignment_payload["tasks"]) if assignment_payload else 0
        rows.append({
            "student": public_user(student),
            "attendance": attendance_summary(db, student.id),
            "assignment": assignment_payload,
            "progress": round(assignment_payload["passed_tasks"] / total * 100) if total else 0,
        })
    today = datetime.now(INDIA_TZ).date()
    present_today = db.scalar(select(func.count(Attendance.id)).where(
        Attendance.user_id.in_([student.id for student in students]) if students else Attendance.user_id == -1,
        Attendance.attendance_date == today,
        Attendance.status.in_(["PRESENT", "HALF_DAY"]),
    )) or 0
    mou = mou_for_coordinator(db, coordinator.id)
    allowed_projects = []
    if mou and mou.allowed_project_ids:
        allowed_projects = [
            {"id": project.id, "title": project.title, "technology": project.technology}
            for project in db.scalars(select(Project).where(Project.id.in_(mou.allowed_project_ids))).all()
        ]
    return {
        "coordinator": public_user(coordinator), "students": rows,
        "mou_access": mou_data(db, mou), "allowed_projects": allowed_projects,
        "summary": {"students": len(students), "present_today": present_today, "absent_or_pending": max(0, len(students) - present_today)},
    }


@app.put("/api/coordinator/students/{student_id}/attendance")
def coordinator_mark_attendance(
    student_id: int, payload: AttendanceOverrideRequest,
    coordinator: User = Depends(require_role("coordinator")), db: Session = Depends(get_db),
):
    student = db.get(User, student_id)
    if not student or student.role != "student" or student.enrollment_type != "COLLEGE" or student.coordinator_id != coordinator.id:
        raise HTTPException(status_code=404, detail="Student not assigned to this Coordinator")
    if payload.attendance_date > datetime.now(INDIA_TZ).date():
        raise HTTPException(status_code=400, detail="Future attendance cannot be marked")
    record = db.scalar(select(Attendance).where(
        Attendance.user_id == student.id, Attendance.attendance_date == payload.attendance_date
    ))
    if not record:
        record = Attendance(user_id=student.id, attendance_date=payload.attendance_date)
        db.add(record)
    record.status = payload.status
    record.notes = payload.notes.strip() or None
    record.marked_by_id = coordinator.id
    audit(db, coordinator.id, "COLLEGE_ATTENDANCE_UPDATED", "attendance", record.id, student_id=student.id, status=payload.status)
    db.commit()
    db.refresh(record)
    return attendance_data(record)


@app.get("/api/coordinator/progress-report")
def coordinator_progress_report(
    coordinator: User = Depends(require_role("coordinator")), db: Session = Depends(get_db),
):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Student", "Email", "Project", "Technology", "Task progress", "Attendance", "Status"])
    students = db.scalars(select(User).where(
        User.role == "student", User.enrollment_type == "COLLEGE", User.college_seat_active.is_(True),
        User.coordinator_id == coordinator.id
    ).order_by(User.name)).all()
    for student in students:
        assignment = get_assignment(db, student.id)
        data = assignment_data(db, assignment) if assignment else None
        total = len(data["tasks"]) if data else 0
        progress = round(data["passed_tasks"] / total * 100) if total else 0
        writer.writerow([
            student.name, student.email, data["variant_title"] if data else "Not selected",
            data["project"]["technology"] if data else "-", f"{progress}%",
            f"{attendance_summary(db, student.id)['percentage']}%", assignment.status if assignment else "NOT_ASSIGNED",
        ])
    return Response(
        content=output.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="GAINT-College-Progress.csv"'},
    )


@app.get("/api/admin/dashboard")
def admin_dashboard(_: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return {
        "student": db.scalar(select(func.count(User.id)).where(User.role == "student")) or 0,
        "college_students": db.scalar(select(func.count(User.id)).where(User.role == "student", User.enrollment_type == "COLLEGE")) or 0,
        "individual_students": db.scalar(select(func.count(User.id)).where(User.role == "student", User.enrollment_type == "INDIVIDUAL")) or 0,
        "mentor": db.scalar(select(func.count(User.id)).where(User.role == "mentor")) or 0,
        "coordinator": db.scalar(select(func.count(User.id)).where(User.role == "coordinator")) or 0,
        "projects": db.scalar(select(func.count(Project.id)).where(Project.active.is_(True))) or 0,
        "submissions": db.scalar(select(func.count(JudgeRun.id))) or 0,
        "certificates": db.scalar(select(func.count(Certificate.id))) or 0,
        "final_reviews": db.scalar(select(func.count(Assignment.id)).where(Assignment.status == "COMPLETED")) or 0,
        "judge_runs": db.scalar(select(func.count(JudgeRun.id))) or 0,
        "mou_seats": db.scalar(select(func.coalesce(func.sum(MouAccess.student_limit), 0)).where(MouAccess.active.is_(True))) or 0,
        "paid_projects": db.scalar(select(func.count(Payment.id)).where(Payment.status == "PAID")) or 0,
    }


@app.get("/api/admin/users")
def admin_users(role: str | None = Query(None), _: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    query = select(User)
    if role:
        query = query.where(User.role == role.lower())
    return [public_user(user) for user in db.scalars(query.order_by(User.created_at.desc())).all()]


@app.post("/api/admin/mentors", status_code=201)
def create_mentor(payload: MentorCreateRequest, _: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    email = str(payload.email).lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Email already exists")
    mentor = User(name=payload.name.strip(), email=email, password_hash=hash_password(payload.password), role="mentor")
    db.add(mentor)
    db.commit()
    db.refresh(mentor)
    return public_user(mentor)


@app.post("/api/admin/coordinators", status_code=201)
def create_coordinator(
    payload: CoordinatorCreateRequest, admin: User = Depends(require_role("admin")), db: Session = Depends(get_db),
):
    email = str(payload.email).lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Email already exists")
    if db.scalar(select(MouAccess).where(MouAccess.mou_number == payload.mou_number.strip())):
        raise HTTPException(status_code=409, detail="MOU number already exists")
    project_ids = list(dict.fromkeys(payload.allowed_project_ids))
    existing_projects = set(db.scalars(select(Project.id).where(Project.id.in_(project_ids))).all())
    if existing_projects != set(project_ids):
        raise HTTPException(status_code=400, detail="One or more selected projects do not exist")
    coordinator = User(
        name=payload.name.strip(), email=email, password_hash=hash_password(payload.password),
        role="coordinator", college_name=payload.college_name.strip(),
    )
    db.add(coordinator)
    db.flush()
    mou = MouAccess(
        coordinator_id=coordinator.id, college_name=coordinator.college_name,
        mou_number=payload.mou_number.strip(), student_limit=payload.student_limit,
        allowed_project_ids=project_ids, starts_on=payload.starts_on, ends_on=payload.ends_on,
        active=True, created_by_id=admin.id,
    )
    db.add(mou)
    db.flush()
    credentials = sync_college_accounts(db, mou)
    audit(db, admin.id, "COLLEGE_MOU_CREATED", "mou", mou.id, student_limit=mou.student_limit)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Coordinator email or MOU number already exists") from exc
    db.refresh(coordinator)
    return {
        "coordinator": public_user(coordinator),
        "mou_access": mou_data(db, mou_for_coordinator(db, coordinator.id)),
        "student_credentials": credentials,
    }


@app.get("/api/admin/coordinators/access")
def coordinator_access_list(_: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    coordinators = list(db.scalars(select(User).where(User.role == "coordinator").order_by(User.college_name, User.name)).all())
    result = []
    for coordinator in coordinators:
        access = mou_data(db, mou_for_coordinator(db, coordinator.id))
        allowed = []
        if access:
            projects = list(db.scalars(select(Project).where(Project.id.in_(access["allowed_project_ids"]))).all())
            allowed = [{"id": project.id, "title": project.title, "technology": project.technology} for project in projects]
        result.append({"coordinator": public_user(coordinator), "mou_access": access, "allowed_projects": allowed})
    return result


@app.put("/api/admin/coordinators/{coordinator_id}/mou")
def update_coordinator_mou(
    coordinator_id: int, payload: MouAccessRequest,
    admin: User = Depends(require_role("admin")), db: Session = Depends(get_db),
):
    coordinator = db.get(User, coordinator_id)
    if not coordinator or coordinator.role != "coordinator":
        raise HTTPException(status_code=404, detail="Coordinator not found")
    project_ids = list(dict.fromkeys(payload.allowed_project_ids))
    existing_projects = set(db.scalars(select(Project.id).where(Project.id.in_(project_ids))).all())
    if existing_projects != set(project_ids):
        raise HTTPException(status_code=400, detail="One or more selected projects do not exist")
    mou = mou_for_coordinator(db, coordinator.id)
    used = mou_data(db, mou)["used_seats"] if mou else 0
    if payload.student_limit < used:
        raise HTTPException(status_code=409, detail=f"Student limit cannot be below the {used} seats already used")
    if not mou:
        mou = MouAccess(coordinator_id=coordinator.id, college_name=coordinator.college_name, created_by_id=admin.id)
        db.add(mou)
    mou.mou_number = payload.mou_number.strip()
    mou.student_limit = payload.student_limit
    mou.allowed_project_ids = project_ids
    mou.starts_on = payload.starts_on
    mou.ends_on = payload.ends_on
    mou.active = payload.active
    credentials = sync_college_accounts(db, mou)
    audit(db, admin.id, "COLLEGE_MOU_UPDATED", "mou", mou.id, student_limit=mou.student_limit, active=mou.active)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="MOU number already exists") from exc
    db.refresh(mou)
    return {"mou_access": mou_data(db, mou), "student_credentials": credentials}


@app.post("/api/admin/coordinators/{coordinator_id}/student-credentials", status_code=201)
def provision_college_credentials(
    coordinator_id: int, payload: CollegeStudentsGenerateRequest,
    admin: User = Depends(require_role("admin")), db: Session = Depends(get_db),
):
    coordinator = db.get(User, coordinator_id)
    mou = mou_for_coordinator(db, coordinator_id)
    if not coordinator or coordinator.role != "coordinator" or not mou:
        raise HTTPException(status_code=404, detail="Coordinator MOU not found")
    if payload.count:
        used = mou_data(db, mou)["used_seats"]
        if payload.count < used:
            raise HTTPException(status_code=409, detail=f"Limit cannot be below {used} active seats")
        mou.student_limit = payload.count
    mou.created_by_id = admin.id
    credentials = sync_college_accounts(db, mou, payload.email_prefix)
    db.commit()
    return {"mou_access": mou_data(db, mou), "student_credentials": credentials}


@app.put("/api/admin/students/{student_id}/mentor")
def assign_mentor(
    student_id: int, payload: AssignMentorRequest,
    _: User = Depends(require_role("admin")), db: Session = Depends(get_db),
):
    student, mentor = db.get(User, student_id), db.get(User, payload.mentor_id)
    if not student or student.role != "student" or not mentor or mentor.role != "mentor":
        raise HTTPException(status_code=404, detail="Student or mentor not found")
    student.mentor_id = mentor.id
    db.commit()
    return {"message": "Mentor assigned"}


@app.put("/api/admin/students/{student_id}/coordinator")
def assign_coordinator(
    student_id: int, payload: AssignCoordinatorRequest,
    _: User = Depends(require_role("admin")), db: Session = Depends(get_db),
):
    student, coordinator = db.get(User, student_id), db.get(User, payload.coordinator_id)
    if not student or student.role != "student" or not coordinator or coordinator.role != "coordinator":
        raise HTTPException(status_code=404, detail="Student or Coordinator not found")
    if student.enrollment_type != "COLLEGE":
        raise HTTPException(status_code=403, detail="Individual students are never assigned to a College Coordinator")
    mou = mou_for_coordinator(db, coordinator.id)
    if not mou_is_active(mou):
        raise HTTPException(status_code=403, detail="Coordinator requires a currently active Admin-approved MOU")
    if (student.college_name or "").casefold() != (coordinator.college_name or "").casefold():
        raise HTTPException(status_code=409, detail="Student college must match the Coordinator MOU college")
    access = mou_data(db, mou)
    if student.coordinator_id != coordinator.id and access["used_seats"] >= mou.student_limit:
        raise HTTPException(status_code=409, detail="This college has reached its Admin-approved MOU student limit")
    if student.project_id and student.project_id not in (mou.allowed_project_ids or []):
        raise HTTPException(status_code=409, detail="The student's selected project is not allowed by this MOU")
    student.coordinator_id = coordinator.id
    db.commit()
    return {"message": "College Coordinator assigned"}


@app.get("/api/admin/projects")
def admin_projects(_: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    projects = db.scalars(select(Project).order_by(Project.technology, Project.internship_type, Project.title)).all()
    return [project_data(project, db.scalar(select(func.count(Task.id)).where(Task.project_id == project.id)) or 0) for project in projects]


@app.post("/api/admin/projects/generate", status_code=201)
def generate_projects(
    payload: GenerateProjectsRequest,
    _: User = Depends(require_role("admin")), db: Session = Depends(get_db),
):
    created = []
    for idea in project_ideas(payload.technology, payload.domain.strip(), payload.count):
        title = idea["title"]
        base_title = title
        suffix = 2
        while db.scalar(select(Project.id).where(
            Project.title == title, Project.technology == payload.technology,
            Project.internship_type == payload.internship_type,
        )):
            title = f"{base_title} {suffix}"
            suffix += 1
        project = Project(
            title=title, technology=payload.technology, internship_type=payload.internship_type,
            domain=payload.domain.strip(), difficulty=payload.difficulty.strip(),
            description=idea["description"], features=idea["features"], generated=True,
            available_tracks=["FULL_STACK"], status="DRAFT",
        )
        db.add(project)
        db.flush()
        add_tasks(db, project)
        created.append(project)
    db.commit()
    return [project_data(project, TASK_COUNTS[project.internship_type]) for project in created]


@app.post("/api/admin/projects/generate-from-prompt", status_code=201)
def generate_project_from_prompt(
    payload: PromptProjectRequest,
    _: User = Depends(require_role("admin")), db: Session = Depends(get_db),
):
    idea = project_idea_from_prompt(payload.prompt, payload.technology, payload.domain.strip())
    title = idea["title"]
    base_title = title
    suffix = 2
    while db.scalar(select(Project.id).where(
        Project.title == title, Project.technology == payload.technology,
        Project.internship_type == payload.internship_type,
    )):
        title = f"{base_title} {suffix}"
        suffix += 1
    project = Project(
        title=title, technology=payload.technology, internship_type=payload.internship_type,
        domain=payload.domain.strip(), difficulty=payload.difficulty.strip(),
        description=idea["description"], features=idea["features"], generated=True,
        available_tracks=["FULL_STACK"], status="DRAFT",
    )
    db.add(project)
    db.flush()
    add_tasks(db, project)
    db.commit()
    db.refresh(project)
    return project_data(project, TASK_COUNTS[project.internship_type])


@app.post("/api/admin/projects", status_code=201)
def create_project(
    payload: ProjectCreateRequest,
    _: User = Depends(require_role("admin")), db: Session = Depends(get_db),
):
    if payload.technology not in TECHNOLOGIES or payload.internship_type.upper() not in INTERNSHIP_TYPES:
        raise HTTPException(status_code=400, detail="Invalid technology or internship type")
    project = Project(
        title=payload.title.strip(), technology=payload.technology,
        internship_type=payload.internship_type.upper(), domain=payload.domain.strip(),
        difficulty=payload.difficulty.strip(), description=payload.description.strip(),
        features=payload.features, generated=False, status="PUBLISHED",
        individual_fee_rupees=payload.individual_fee_rupees,
        available_tracks=payload.available_tracks,
    )
    db.add(project)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Project already exists for this technology and internship type") from exc
    if payload.auto_generate_tasks:
        add_tasks(db, project)
    db.commit()
    db.refresh(project)
    return project_data(project, TASK_COUNTS[project.internship_type] if payload.auto_generate_tasks else 0)


@app.post("/api/admin/projects/upload-complete", status_code=201)
async def upload_complete_project(
    title: str = Form(..., min_length=3, max_length=180),
    internship_type: str = Form(...),
    domain: str = Form("General", max_length=80),
    difficulty: str = Form("Intermediate", max_length=30),
    description: str = Form(..., min_length=10, max_length=4_000),
    individual_fee_rupees: int = Form(999, ge=1, le=100_000),
    technology: str = Form("AUTO"),
    project_zip: UploadFile = File(...),
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    internship_type = internship_type.upper().strip()
    if internship_type not in INTERNSHIP_TYPES:
        raise HTTPException(status_code=400, detail="Invalid internship type")
    if not project_zip.filename or Path(project_zip.filename).suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="Upload the complete runnable project as a ZIP")
    content = await project_zip.read()
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Project ZIP must be 100 MB or smaller")
    try:
        metadata = analyse_project_zip(content)
    except ProjectZipError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    detected_technology = metadata["technology"] if technology.upper() == "AUTO" else technology
    if detected_technology not in TECHNOLOGIES:
        raise HTTPException(status_code=400, detail="Unsupported or undetected technology")
    if db.scalar(select(Project.id).where(
        Project.title == title.strip(),
        Project.technology == detected_technology,
        Project.internship_type == internship_type,
    )):
        raise HTTPException(status_code=409, detail="This project already exists for the selected internship")

    stored_name = f"project_{uuid.uuid4().hex}.zip"
    (settings.upload_dir / stored_name).write_bytes(content)
    project = Project(
        title=title.strip(),
        technology=detected_technology,
        internship_type=internship_type,
        domain=domain.strip() or "General",
        difficulty=difficulty.strip() or "Intermediate",
        description=description.strip(),
        features=["Complete runnable source", "Local database", "Sequential evaluated tasks"],
        available_tracks=metadata["available_tracks"],
        master_zip_filename=stored_name,
        stack_metadata=metadata,
        generated=False,
        status="DRAFT",
        individual_fee_rupees=individual_fee_rupees,
    )
    db.add(project)
    db.flush()
    add_tasks(db, project)
    audit(
        db,
        admin.id,
        "COMPLETE_PROJECT_UPLOADED",
        "project",
        project.id,
        source_file_count=metadata["source_file_count"],
        tracks=metadata["available_tracks"],
    )
    db.commit()
    db.refresh(project)
    return {
        "project": project_data(project, TASK_COUNTS[internship_type]),
        "analysis": metadata,
        "message": (
            "Project analysed. PostgreSQL schema/seed placeholders, local SQLite data, "
            "setup guides, sequential tasks and hidden Judge0 cases will be included."
        ),
    }


@app.post("/api/admin/projects/{project_id}/publish")
def publish_project(project_id: int, _: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    expected = TASK_COUNTS[project.internship_type]
    actual = db.scalar(select(func.count(Task.id)).where(Task.project_id == project.id)) or 0
    if actual != expected:
        raise HTTPException(status_code=409, detail=f"Project requires exactly {expected} tasks before publishing")
    issues = (project.stack_metadata or {}).get("validation_issues") or []
    if project.master_zip_filename and issues:
        raise HTTPException(
            status_code=409,
            detail="Project ZIP is not publish-ready: " + "; ".join(issues),
        )
    project.status = "PUBLISHED"
    db.commit()
    return {"message": "Project published"}


@app.post("/api/admin/projects/{project_id}/tasks", status_code=201)
def create_task(
    project_id: int, payload: TaskCreateRequest,
    _: User = Depends(require_role("admin")), db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if db.scalar(select(Task.id).where(Task.project_id == project_id, Task.order_no == payload.order_no)):
        raise HTTPException(status_code=409, detail="This task order already exists")
    task = Task(project_id=project_id, **payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return {"id": task.id, "title": task.title}


@app.post("/api/admin/teams", status_code=201)
def create_college_project_team(
    payload: TeamCreateRequest,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    project = db.get(Project, payload.project_id)
    coordinator = db.get(User, payload.coordinator_id)
    mou = mou_for_coordinator(db, payload.coordinator_id)
    if not project or not project.active or project.status != "PUBLISHED":
        raise HTTPException(status_code=404, detail="Published project not found")
    if not coordinator or coordinator.role != "coordinator" or not mou_is_active(mou):
        raise HTTPException(status_code=409, detail="Coordinator requires an active MOU")
    if project.id not in (mou.allowed_project_ids or []):
        raise HTTPException(status_code=403, detail="This project is not approved for the college MOU")
    available_tracks = set(project.available_tracks or [])
    requested_tracks = {member.track for member in payload.members}
    if not requested_tracks.issubset(available_tracks):
        missing = ", ".join(sorted(requested_tracks - available_tracks))
        raise HTTPException(status_code=400, detail=f"Project does not support these team tracks: {missing}")
    students: list[tuple[User, str]] = []
    for item in payload.members:
        student = db.get(User, item.student_id)
        if (
            not student
            or student.role != "student"
            or student.enrollment_type != "COLLEGE"
            or student.coordinator_id != coordinator.id
            or (student.college_name or "").casefold() != mou.college_name.casefold()
            or not student.college_seat_active
        ):
            raise HTTPException(
                status_code=400,
                detail=f"Student {item.student_id} is not an active member of this college",
            )
        if get_assignment(db, student.id) or db.scalar(select(ProjectTeamMember.id).where(
            ProjectTeamMember.user_id == student.id
        )):
            raise HTTPException(
                status_code=409,
                detail=f"{student.name} already has a project assignment",
            )
        students.append((student, item.track))
    team = ProjectTeam(
        name=payload.name.strip(),
        college_name=mou.college_name,
        project_id=project.id,
        coordinator_id=coordinator.id,
        created_by_id=admin.id,
    )
    db.add(team)
    db.flush()
    for student, track in students:
        variant_title, variant_brief, seed = personalised_variant(
            student.id, project.title, project.domain
        )
        starts_at = utcnow()
        assignment = Assignment(
            user_id=student.id,
            project_id=project.id,
            variant_title=variant_title,
            variant_brief=(
                f"{variant_brief} Team: {team.name}. Your owned track is "
                f"{track.replace('_', ' ').title()}."
            ),
            variant_seed=seed,
            selected_track=track,
            access_ends_at=starts_at + timedelta(days=INTERNSHIP_DAYS[project.internship_type]),
            grace_ends_at=(
                starts_at
                + timedelta(days=INTERNSHIP_DAYS[project.internship_type])
                + timedelta(days=GRACE_DAYS[project.internship_type])
            ),
            access_status="ACTIVE",
        )
        student.project_id = project.id
        student.internship_type = project.internship_type
        student.preferred_language = project.technology
        student.learning_started_at = starts_at
        db.add(assignment)
        db.flush()
        db.add(ProjectTeamMember(
            team_id=team.id,
            user_id=student.id,
            assignment_id=assignment.id,
            track=track,
        ))
        db.add(AssignmentValidation(assignment_id=assignment.id))
    audit(
        db,
        admin.id,
        "COLLEGE_PROJECT_TEAM_CREATED",
        "project_team",
        team.id,
        project_id=project.id,
        coordinator_id=coordinator.id,
        member_count=len(students),
    )
    db.commit()
    db.refresh(team)
    return project_team_data(db, team)


@app.get("/api/admin/teams")
def admin_project_teams(
    _: User = Depends(require_role("admin")), db: Session = Depends(get_db)
):
    teams = db.scalars(select(ProjectTeam).order_by(ProjectTeam.created_at.desc())).all()
    return [project_team_data(db, team) for team in teams]


@app.get("/api/coordinator/teams")
def coordinator_project_teams(
    coordinator: User = Depends(require_role("coordinator")),
    db: Session = Depends(get_db),
):
    teams = db.scalars(select(ProjectTeam).where(
        ProjectTeam.coordinator_id == coordinator.id
    ).order_by(ProjectTeam.created_at.desc())).all()
    return [project_team_data(db, team) for team in teams]


@app.get("/api/student/team")
def student_project_team(
    student: User = Depends(require_role("student")), db: Session = Depends(get_db)
):
    assignment = get_assignment(db, student.id)
    return team_data(db, assignment.id) if assignment else None


@app.get("/api/teams/{team_id}/completed-project")
def download_completed_team_project(
    team_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    team = db.get(ProjectTeam, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="College project team not found")
    member = db.scalar(select(ProjectTeamMember).where(
        ProjectTeamMember.team_id == team.id,
        ProjectTeamMember.user_id == user.id,
    ))
    if not (
        user.role == "admin"
        or (user.role == "coordinator" and team.coordinator_id == user.id)
        or (user.role == "student" and member)
    ):
        raise HTTPException(status_code=403, detail="You cannot download this team project")
    members = list(db.scalars(select(ProjectTeamMember).where(
        ProjectTeamMember.team_id == team.id
    )).all())
    archives: list[tuple[str, bytes]] = []
    for item in members:
        assignment = db.get(Assignment, item.assignment_id)
        validation = assignment_validation(db, assignment.id)
        student = db.get(User, item.user_id)
        if not certificate_ready(db, assignment) or not validation:
            raise HTTPException(
                status_code=409,
                detail=f"{student.name} has not completed and validated the {item.track} track",
            )
        snapshot = settings.upload_dir / validation.final_snapshot_filename
        if not snapshot.exists():
            raise HTTPException(status_code=409, detail=f"Validated source is missing for {student.name}")
        archives.append((f"{student.name} ({item.track})", snapshot.read_bytes()))
    project = db.get(Project, team.project_id)
    try:
        content, filename = team_completed_project_zip(project, team.name, archives)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    stored_name = f"team_completed_{team.id}_{uuid.uuid4().hex}.zip"
    (settings.upload_dir / stored_name).write_bytes(content)
    team.combined_package_filename = stored_name
    team.combined_package_hash = hashlib.sha256(content).hexdigest()
    team.status = "COMPLETED"
    team.completed_at = team.completed_at or utcnow()
    audit(db, user.id, "TEAM_PROJECT_PACKAGED", "project_team", team.id)
    db.commit()
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/admin/completions")
def admin_completions(_: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    assignments = db.scalars(select(Assignment).order_by(Assignment.created_at.desc())).all()
    return [assignment_data(db, assignment) for assignment in assignments if certificate_ready(db, assignment)]


@app.get("/api/admin/reports")
def admin_reports(_: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    students = db.scalars(select(User).where(User.role == "student").order_by(User.name)).all()
    reports = []
    for student in students:
        assignment = get_assignment(db, student.id)
        if not assignment:
            reports.append({"student_id": student.id, "name": student.name, "enrollment_type": student.enrollment_type, "college": student.college_name, "project": None, "progress": 0, "attendance": attendance_summary(db, student.id)["percentage"] if student.enrollment_type == "COLLEGE" else None, "status": "NOT_ASSIGNED"})
            continue
        data = assignment_data(db, assignment)
        total = len(data["tasks"])
        reports.append({
            "student_id": student.id, "name": student.name, "enrollment_type": student.enrollment_type, "college": student.college_name,
            "project": data["variant_title"], "technology": data["project"]["technology"],
            "internship_type": student.internship_type,
            "progress": round(data["passed_tasks"] / total * 100) if total else 0,
            "attendance": attendance_summary(db, student.id)["percentage"] if student.enrollment_type == "COLLEGE" else None,
            "status": assignment.status,
        })
    return reports


@app.get("/api/admin/certificates")
def admin_certificates(_: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    certificates = db.scalars(select(Certificate).order_by(Certificate.issued_at.desc())).all()
    return [{"certificate_no": item.certificate_no, "student": db.get(User, item.user_id).name, "issued_at": item.issued_at} for item in certificates]


@app.get("/api/admin/payments")
def admin_payments(_: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    payments = db.scalars(select(Payment).order_by(Payment.created_at.desc())).all()
    return [{
        **payment_data(item),
        "student": public_user(db.get(User, item.user_id)),
        "project": project_data(db.get(Project, item.project_id)),
    } for item in payments]


@app.get("/api/admin/audit-logs")
def admin_audit_logs(_: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    logs = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(500)).all()
    return [{
        "id": item.id, "actor_id": item.actor_id, "action": item.action,
        "target_type": item.target_type, "target_id": item.target_id,
        "details": item.details, "created_at": item.created_at,
    } for item in logs]
