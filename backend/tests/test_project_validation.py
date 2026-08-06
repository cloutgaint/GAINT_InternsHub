import hashlib
import zipfile
from io import BytesIO

import pytest

from app.project_upload import ProjectZipError, analyse_project_zip
from app.project_validation import (
    ProjectValidationError,
    normalise_source_path,
    validate_source_snapshot,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def test_real_source_snapshot_accepts_changed_valid_code():
    content = "def create_student(name):\n    return {'name': name}\n"
    hashes, details = validate_source_snapshot(
        contents={"backend/app/students.py": content},
        declared_hashes={"backend/app/students.py": digest(content)},
        required_paths=["backend/app"],
        baseline_hashes={"backend/app/students.py": digest("pass\n")},
    )
    assert hashes["backend/app/students.py"] == digest(content)
    assert details["changed_files"] == ["backend/app/students.py"]


def test_python_pasted_into_javascript_is_rejected():
    content = "import sys\nfor line in sys.stdin:\n    print(line)\n"
    with pytest.raises(ProjectValidationError, match="Python syntax"):
        validate_source_snapshot(
            contents={"frontend/src/App.js": content},
            declared_hashes={"frontend/src/App.js": digest(content)},
            required_paths=["frontend/src"],
        )


def test_unchanged_starter_source_cannot_unlock_a_task():
    content = "def ready():\n    return True\n"
    with pytest.raises(ProjectValidationError, match="have not changed"):
        validate_source_snapshot(
            contents={"backend/app/main.py": content},
            declared_hashes={"backend/app/main.py": digest(content)},
            required_paths=["backend/app"],
            baseline_hashes={"backend/app/main.py": digest(content)},
        )


def test_unchanged_project_evidence_is_allowed_for_checkpoint_only_submission():
    """Regression: editing README must not be needed to submit task_N.py."""
    content = "def ready():\n    return True\n"
    hashes, details = validate_source_snapshot(
        contents={"backend/app/main.py": content},
        declared_hashes={"backend/app/main.py": digest(content)},
        required_paths=["backend/app"],
        baseline_hashes={"backend/app/main.py": digest(content)},
        require_change=False,
    )
    assert hashes["backend/app/main.py"] == digest(content)
    assert details["changed_files"] == []


def test_project_evidence_rejects_path_traversal_and_private_keys():
    with pytest.raises(ProjectValidationError, match="Unsafe"):
        normalise_source_path("../../backend/app/main.py")
    with pytest.raises(ProjectValidationError, match="Unsafe"):
        normalise_source_path("backend/private-signing-key.pem")


def test_admin_project_zip_rejects_secret_files():
    content = BytesIO()
    with zipfile.ZipFile(content, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("CompleteApp/backend/app/main.py", "print('ready')\n")
        archive.writestr("CompleteApp/backend/.env", "DATABASE_PASSWORD=secret\n")
    with pytest.raises(ProjectZipError, match="secret or credential"):
        analyse_project_zip(content.getvalue())
