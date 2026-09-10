import re
from datetime import date

from pydantic import BaseModel, EmailStr, Field, field_validator


TECHNOLOGIES = {"Java", "Python", "Node.js", "Next.js", "Django"}
INTERNSHIP_TYPES = {"FASTTRACK", "45_DAYS", "SEMESTER"}
PROJECT_TRACKS = {"FRONTEND", "BACKEND", "FULL_STACK", "DATABASE", "AI_ML", "MOBILE"}


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    role: str | None = None


class PreferencesRequest(BaseModel):
    preferred_language: str = Field(min_length=1, max_length=40)
    area_interest: str = Field(min_length=2, max_length=250)
    internship_type: str = Field(min_length=1, max_length=30)

    @field_validator("preferred_language")
    @classmethod
    def validate_technology(cls, value: str) -> str:
        value = value.strip()
        if value not in TECHNOLOGIES:
            raise ValueError("Select a supported technology")
        return value

    @field_validator("area_interest")
    @classmethod
    def validate_area_interest(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Area of interest must contain at least 2 characters")
        return value

    @field_validator("internship_type")
    @classmethod
    def validate_internship_type(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in INTERNSHIP_TYPES:
            raise ValueError("Select a supported internship type")
        return value


class ProjectSelectRequest(BaseModel):
    selected_track: str | None = None

    @field_validator("selected_track")
    @classmethod
    def validate_track(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper().strip()
        if value not in PROJECT_TRACKS:
            raise ValueError("Invalid project track")
        return value


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class MentorCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class CoordinatorCreateRequest(MentorCreateRequest):
    college_name: str = Field(min_length=2, max_length=200)
    mou_number: str = Field(min_length=3, max_length=100)
    student_limit: int = Field(ge=1, le=500)
    allowed_project_ids: list[int] = Field(min_length=1)
    starts_on: date
    ends_on: date

    @field_validator("ends_on")
    @classmethod
    def validate_ends_on(cls, value: date, info) -> date:
        starts_on = info.data.get("starts_on")
        if starts_on and value < starts_on:
            raise ValueError("MOU end date must be on or after start date")
        return value


class MouAccessRequest(BaseModel):
    mou_number: str = Field(min_length=3, max_length=100)
    student_limit: int = Field(ge=1, le=500)
    allowed_project_ids: list[int] = Field(min_length=1)
    starts_on: date
    ends_on: date
    active: bool = True

    @field_validator("ends_on")
    @classmethod
    def validate_mou_ends_on(cls, value: date, info) -> date:
        starts_on = info.data.get("starts_on")
        if starts_on and value < starts_on:
            raise ValueError("MOU end date must be on or after start date")
        return value


class CollegeStudentsGenerateRequest(BaseModel):
    count: int | None = Field(default=None, ge=1, le=500)
    email_prefix: str = Field(default="student", min_length=2, max_length=30, pattern=r"^[A-Za-z0-9._-]+$")


class AssignMentorRequest(BaseModel):
    mentor_id: int


class AssignCoordinatorRequest(BaseModel):
    coordinator_id: int


class AttendanceOverrideRequest(BaseModel):
    attendance_date: date
    status: str
    notes: str = Field(default="", max_length=500)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        value = value.upper()
        if value not in {"PRESENT", "HALF_DAY", "ABSENT", "LEAVE"}:
            raise ValueError("Invalid attendance status")
        return value


class JudgeSubmitRequest(BaseModel):
    language: str
    source_code: str = Field(min_length=3, max_length=100_000)
    file_name: str = Field(min_length=1, max_length=500)
    explanation: str = Field(default="Submitted from the GAINT VS Code extension", min_length=3, max_length=2_000)
    required_file_hashes: dict[str, str] = Field(default_factory=dict)
    project_file_contents: dict[str, str] = Field(default_factory=dict)
    local_check_results: list[dict] = Field(default_factory=list)

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in {"python", "javascript", "java"}:
            raise ValueError("Judge0 supports Python, JavaScript or Java checkpoints")
        return value

    @field_validator("project_file_contents")
    @classmethod
    def validate_project_file_contents(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 180:
            raise ValueError("Too many project source files")
        total = 0
        for path, content in value.items():
            if not path or len(path) > 500 or not isinstance(content, str):
                raise ValueError("Invalid project source evidence")
            total += len(content.encode("utf-8"))
            if len(content.encode("utf-8")) > 256 * 1024:
                raise ValueError(f"Project source file is too large: {path}")
        if total > 3 * 1024 * 1024:
            raise ValueError("Project source evidence is too large")
        return value

    @field_validator("required_file_hashes")
    @classmethod
    def validate_file_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 500:
            raise ValueError("Too many project evidence files")
        for path, digest in value.items():
            if not path or len(path) > 500 or not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
                raise ValueError("Invalid project evidence hash")
        return value


class ProjectFingerprintRequest(BaseModel):
    fingerprint: str = Field(pattern=r"^[a-fA-F0-9]{64}$")


class CompletionPackageRequest(ProjectFingerprintRequest):
    filename: str = Field(min_length=5, max_length=255, pattern=r"^[A-Za-z0-9._ -]+\.zip$")
    required_file_hashes: dict[str, str] = Field(default_factory=dict)
    project_file_contents: dict[str, str] = Field(default_factory=dict)
    local_check_results: list[dict] = Field(default_factory=list)

    @field_validator("project_file_contents")
    @classmethod
    def validate_final_project_contents(cls, value: dict[str, str]) -> dict[str, str]:
        return JudgeSubmitRequest.validate_project_file_contents(value)

    @field_validator("required_file_hashes")
    @classmethod
    def validate_final_file_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        return JudgeSubmitRequest.validate_file_hashes(value)


class TeamMemberInput(BaseModel):
    student_id: int
    track: str

    @field_validator("track")
    @classmethod
    def validate_team_track(cls, value: str) -> str:
        value = value.upper().strip()
        if value not in {"FRONTEND", "BACKEND", "DATABASE", "MOBILE", "AI_ML"}:
            raise ValueError("Team members require a role-specific project track")
        return value


class TeamCreateRequest(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    project_id: int
    coordinator_id: int
    members: list[TeamMemberInput] = Field(min_length=2, max_length=6)

    @field_validator("members")
    @classmethod
    def validate_team_members(cls, value: list[TeamMemberInput]) -> list[TeamMemberInput]:
        student_ids = [item.student_id for item in value]
        tracks = [item.track for item in value]
        if len(student_ids) != len(set(student_ids)):
            raise ValueError("A student can appear only once in a team")
        if len(tracks) != len(set(tracks)):
            raise ValueError("Assign only one student to each team track")
        if "FRONTEND" not in tracks or "BACKEND" not in tracks:
            raise ValueError("A college team project requires FRONTEND and BACKEND members")
        return value


class WorkspaceBootstrapRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200, pattern=r"^gaint_boot_")


class PaymentConfirmRequest(BaseModel):
    terms_accepted: bool


class RazorpayVerifyRequest(BaseModel):
    razorpay_order_id: str = Field(min_length=8, max_length=120, pattern=r"^order_[A-Za-z0-9]+$")
    razorpay_payment_id: str = Field(min_length=8, max_length=120, pattern=r"^pay_[A-Za-z0-9]+$")
    razorpay_signature: str = Field(min_length=64, max_length=64, pattern=r"^[a-fA-F0-9]{64}$")


class AiTaskRequest(BaseModel):
    action: str
    error_message: str = Field(default="", max_length=2_000)
    task_id: int | None = Field(default=None, ge=1)

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        value = value.upper().strip()
        if value not in {"EXPLAIN", "HINT", "ERROR"}:
            raise ValueError("AI action must be EXPLAIN, HINT or ERROR")
        return value


class AiChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=500)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = re.sub(r"\s+", " ", value).strip()
        if len(value) < 2:
            raise ValueError("Enter a question for the learning assistant")
        return value


class GenerateProjectsRequest(BaseModel):
    technology: str
    internship_type: str
    domain: str = Field(min_length=2, max_length=80)
    difficulty: str = Field(default="Intermediate", max_length=30)
    count: int = Field(default=3, ge=1, le=5)

    @field_validator("technology")
    @classmethod
    def validate_technology(cls, value: str) -> str:
        if value not in TECHNOLOGIES:
            raise ValueError("Unsupported technology")
        return value

    @field_validator("internship_type")
    @classmethod
    def validate_internship_type(cls, value: str) -> str:
        value = value.upper()
        if value not in INTERNSHIP_TYPES:
            raise ValueError("Invalid internship type")
        return value


class PromptProjectRequest(BaseModel):
    prompt: str = Field(min_length=20, max_length=8_000)
    technology: str
    internship_type: str
    domain: str = Field(default="General", min_length=2, max_length=80)
    difficulty: str = Field(default="Intermediate", max_length=30)

    @field_validator("technology")
    @classmethod
    def validate_prompt_technology(cls, value: str) -> str:
        if value not in TECHNOLOGIES:
            raise ValueError("Unsupported technology")
        return value

    @field_validator("internship_type")
    @classmethod
    def validate_prompt_internship_type(cls, value: str) -> str:
        value = value.upper()
        if value not in INTERNSHIP_TYPES:
            raise ValueError("Invalid internship type")
        return value

class ProjectCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    technology: str
    internship_type: str
    domain: str = Field(default="General", max_length=80)
    difficulty: str = Field(default="Intermediate", max_length=30)
    description: str = Field(min_length=10, max_length=4_000)
    features: list[str] = Field(default_factory=list)
    auto_generate_tasks: bool = True
    individual_fee_rupees: int = Field(default=999, ge=1, le=100_000)
    available_tracks: list[str] = Field(default_factory=lambda: ["FULL_STACK"])

    @field_validator("available_tracks")
    @classmethod
    def validate_tracks(cls, value: list[str]) -> list[str]:
        tracks = list(dict.fromkeys(item.upper().strip() for item in value))
        if not tracks or any(item not in PROJECT_TRACKS for item in tracks):
            raise ValueError("Select at least one valid project track")
        return tracks

    @field_validator("technology")
    @classmethod
    def validate_project_technology(cls, value: str) -> str:
        if value not in TECHNOLOGIES:
            raise ValueError("Unsupported technology")
        return value

    @field_validator("internship_type")
    @classmethod
    def validate_project_internship(cls, value: str) -> str:
        value = value.upper()
        if value not in INTERNSHIP_TYPES:
            raise ValueError("Invalid internship type")
        return value


class TaskCreateRequest(BaseModel):
    order_no: int = Field(ge=1, le=20)
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(min_length=10, max_length=6_000)
    deliverables: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    visible_tests: list[str] = Field(default_factory=list)
    hidden_checks: list[str] = Field(default_factory=list)
    checkpoint_file: str = Field(default="gaint_checkpoints/task_1.py", min_length=3, max_length=500)
    challenge_prompt: str = Field(default="Complete the Judge0 checkpoint described by the Mentor.", max_length=4_000)
    judge0_cases: list[dict] = Field(default_factory=list)
    required_paths: list[str] = Field(default_factory=list)
    local_checks: list[str] = Field(default_factory=list)
