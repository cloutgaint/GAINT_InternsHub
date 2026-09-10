from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def clean_secret(value: str) -> str:
    """Normalize secrets copied from hosting dashboards.

    Unlike dotenv files, most deployment dashboards preserve surrounding
    whitespace and quote characters. Either makes HTTP Basic authentication
    fail even when the visible Razorpay credentials look correct.
    """
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("ENVIRONMENT", "development").lower()
    app_name: str = os.getenv("APP_NAME", "GAINT Interns Hub")
    secret_key: str = os.getenv("SECRET_KEY", "development-only-change-me")
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'gaint_interns_v8.db'}")
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    public_api_url: str = os.getenv("PUBLIC_API_URL", "http://localhost:8000/api").rstrip("/")
    token_expire_hours: int = int(os.getenv("TOKEN_EXPIRE_HOURS", "720"))
    # 0 means the installed VS Code connection has no time-based expiry.
    # Admin/project/MOU access controls can still revoke or block it.
    vscode_token_days: int = int(os.getenv("VSCODE_TOKEN_DAYS", "0"))
    # A student may download the starter at college and open it later at home.
    # Keep the first automatic connection usable for 30 days. After it is used,
    # the private VS Code device connection does not expire by default.
    workspace_bootstrap_minutes: int = int(os.getenv("WORKSPACE_BOOTSTRAP_MINUTES", "43200"))
    payment_provider: str = os.getenv("PAYMENT_PROVIDER", "demo").lower()
    razorpay_key_id: str = clean_secret(os.getenv("RAZORPAY_KEY_ID", ""))
    razorpay_key_secret: str = clean_secret(os.getenv("RAZORPAY_KEY_SECRET", ""))
    razorpay_webhook_secret: str = clean_secret(os.getenv("RAZORPAY_WEBHOOK_SECRET", ""))
    razorpay_api_url: str = os.getenv("RAZORPAY_API_URL", "https://api.razorpay.com/v1").rstrip("/")
    judge0_url: str = os.getenv("JUDGE0_URL", "https://ce.judge0.com").rstrip("/")
    judge0_auth_header: str = os.getenv("JUDGE0_AUTH_HEADER", "X-Auth-Token")
    judge0_auth_token: str = os.getenv("JUDGE0_AUTH_TOKEN", "")
    judge0_python_id: int = int(os.getenv("JUDGE0_PYTHON_ID", "109"))
    judge0_javascript_id: int = int(os.getenv("JUDGE0_JAVASCRIPT_ID", "63"))
    judge0_java_id: int = int(os.getenv("JUDGE0_JAVA_ID", "62"))
    certificate_verify_base_url: str = os.getenv("CERTIFICATE_VERIFY_BASE_URL", "http://localhost:8000/api/certificates/verify")
    ai_provider: str = os.getenv("AI_PROVIDER", "safe-local").lower()
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.6-terra")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    ai_chat_daily_limit: int = max(1, int(os.getenv("AI_CHAT_DAILY_LIMIT", "30")))
    ai_timeout_seconds: int = max(5, int(os.getenv("AI_TIMEOUT_SECONDS", "25")))
    project_validation_required: bool = os.getenv(
        # Checkpoint submissions must not require an unrelated README or
        # project-source edit. Judge0 and local checks determine task success.
        "PROJECT_VALIDATION_REQUIRED", "false"
    ).lower() in {"1", "true", "yes", "on"}
    project_evidence_max_mb: int = max(
        1, min(10, int(os.getenv("PROJECT_EVIDENCE_MAX_MB", "3")))
    )
    upload_dir: Path = BASE_DIR / "uploads"
    seed_demo_data: bool = os.getenv("SEED_DEMO_DATA", "true").lower() in {"1", "true", "yes", "on"}
    bootstrap_admin_email: str = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
    bootstrap_admin_password: str = clean_secret(os.getenv("BOOTSTRAP_ADMIN_PASSWORD", ""))

    @property
    def frontend_urls(self) -> list[str]:
        return [value.strip().rstrip("/") for value in self.frontend_url.split(",") if value.strip()]

    def validate_production(self) -> None:
        if self.environment != "production":
            return
        errors = []
        if len(self.secret_key) < 32 or "change-me" in self.secret_key.lower():
            errors.append("SECRET_KEY must be a random value of at least 32 characters")
        if not self.frontend_urls or any(not url.startswith("https://") for url in self.frontend_urls):
            errors.append("FRONTEND_URL must contain public HTTPS URL(s)")
        if not self.public_api_url.startswith("https://"):
            errors.append("PUBLIC_API_URL must be a public HTTPS URL")
        if not self.bootstrap_admin_email or len(self.bootstrap_admin_password) < 12:
            errors.append("set BOOTSTRAP_ADMIN_EMAIL and a BOOTSTRAP_ADMIN_PASSWORD of at least 12 characters")
        if self.payment_provider == "razorpay" and not all(
            (self.razorpay_key_id, self.razorpay_key_secret, self.razorpay_webhook_secret)
        ):
            errors.append("Razorpay mode requires key ID, key secret, and webhook secret")
        if errors:
            raise RuntimeError("Invalid production configuration: " + "; ".join(errors))


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
