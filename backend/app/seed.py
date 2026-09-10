from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import MouAccess, Project, Task, User
from .project_generator import TECH_CATALOG, task_specs
from .security import hash_password


def add_tasks(db: Session, project: Project) -> None:
    if db.scalar(select(Task.id).where(Task.project_id == project.id).limit(1)):
        return
    for spec in task_specs(project.title, project.technology, project.features, project.internship_type):
        db.add(Task(project_id=project.id, **spec))


def seed_database(
    db: Session,
    *,
    include_demo_users: bool = True,
    bootstrap_admin_email: str = "",
    bootstrap_admin_password: str = "",
) -> None:
    demo_users = [
        ("GAINT Administrator", "admin@gaint.com", "Admin@123", "admin"),
        ("GAINT Mentor", "mentor@gaint.com", "Mentor@123", "mentor"),
        ("Demo College Coordinator", "coordinator@gaint.com", "Coordinator@123", "coordinator"),
    ] if include_demo_users else []
    if bootstrap_admin_email and bootstrap_admin_password:
        demo_users.append(("GAINT Administrator", bootstrap_admin_email, bootstrap_admin_password, "admin"))
    for name, email, password, role in demo_users:
        if not db.scalar(select(User).where(User.email == email)):
            db.add(User(
                name=name, email=email, password_hash=hash_password(password), role=role,
                college_name="GAINT Demo College" if role == "coordinator" else None,
            ))
    db.commit()

    for technology, catalogue in TECH_CATALOG.items():
        for internship_type in ("FASTTRACK", "45_DAYS", "SEMESTER"):
            for title, features in catalogue[:2]:
                project = db.scalar(select(Project).where(
                    Project.title == title,
                    Project.technology == technology,
                    Project.internship_type == internship_type,
                ))
                if not project:
                    project = Project(
                        title=title,
                        technology=technology,
                        internship_type=internship_type,
                        domain="General",
                        difficulty="Intermediate",
                        description=f"Build a complete {title} using {technology}, with connected milestones completed locally in VS Code.",
                        features=features,
                        generated=False,
                        status="PUBLISHED",
                    )
                    db.add(project)
                    db.flush()
                add_tasks(db, project)
    db.commit()

    coordinator = db.scalar(select(User).where(User.email == "coordinator@gaint.com")) if include_demo_users else None
    admin = db.scalar(select(User).where(User.email == "admin@gaint.com"))
    if coordinator and not db.scalar(select(MouAccess).where(MouAccess.coordinator_id == coordinator.id)):
        project_ids = list(db.scalars(select(Project.id).where(Project.status == "PUBLISHED")).all())
        db.add(MouAccess(
            coordinator_id=coordinator.id, college_name=coordinator.college_name,
            mou_number="GAINT-DEMO-MOU-001", student_limit=500,
            allowed_project_ids=project_ids, starts_on=date.today(), ends_on=date.today() + timedelta(days=365),
            active=True, created_by_id=admin.id if admin else None,
        ))
        db.commit()

    if coordinator and not db.scalar(select(User).where(User.email == "student@gaint.com")):
        mentor = db.scalar(select(User).where(User.email == "mentor@gaint.com"))
        db.add(User(
            name="Demo College Student", email="student@gaint.com",
            password_hash=hash_password("Student@123"), role="student",
            enrollment_type="COLLEGE", college_name="GAINT Demo College",
            coordinator_id=coordinator.id, mentor_id=mentor.id if mentor else None,
            college_seat_active=True, must_change_password=False,
            email_verified=True, mobile_verified=True,
        ))
        db.commit()
