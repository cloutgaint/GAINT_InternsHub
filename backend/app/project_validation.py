from __future__ import annotations

import ast
import hashlib
import json
import re
import zipfile
from io import BytesIO
from pathlib import PurePosixPath


TEXT_SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".java",
    ".html", ".css", ".scss", ".json", ".sql", ".md", ".xml", ".yml", ".yaml",
}
FORBIDDEN_PARTS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    "dist", "build", ".next", "target", ".idea", "gaint_checkpoints",
}
FORBIDDEN_FILENAMES = {
    ".env", "id_rsa", "id_ed25519", "credentials.json", "service-account.json",
}
MAX_EVIDENCE_FILES = 180
MAX_EVIDENCE_FILE_BYTES = 256 * 1024
MAX_EVIDENCE_TOTAL_BYTES = 3 * 1024 * 1024


class ProjectValidationError(ValueError):
    pass


def normalise_source_path(value: str) -> str:
    raw = str(value).replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    path = PurePosixPath(raw)
    filename = path.name.lower()
    if (
        not path.parts
        or path.is_absolute()
        or ".." in path.parts
        or any(part.lower() in FORBIDDEN_PARTS for part in path.parts)
        or filename in FORBIDDEN_FILENAMES
        or (filename.startswith(".env.") and filename != ".env.example")
        or filename.endswith((".pem", ".key", ".p12", ".pfx"))
    ):
        raise ProjectValidationError(f"Unsafe or unsupported project source path: {value}")
    if path.suffix.lower() not in TEXT_SOURCE_EXTENSIONS:
        raise ProjectValidationError(f"Only text project source files may be submitted: {value}")
    return str(path)


def snapshot_hashes_from_zip(content: bytes) -> dict[str, str]:
    """Build the trusted starter baseline stored by the backend."""
    try:
        archive = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ProjectValidationError("The generated starter ZIP is invalid") from exc
    names = [
        item.filename.replace("\\", "/")
        for item in archive.infolist()
        if not item.is_dir()
    ]
    if not names:
        return {}
    first_parts = {PurePosixPath(name).parts[0] for name in names}
    strip_root = len(first_parts) == 1
    result: dict[str, str] = {}
    for item in archive.infolist():
        if item.is_dir():
            continue
        parts = PurePosixPath(item.filename.replace("\\", "/")).parts
        if strip_root:
            parts = parts[1:]
        if not parts:
            continue
        relative = str(PurePosixPath(*parts))
        try:
            safe = normalise_source_path(relative)
        except ProjectValidationError:
            continue
        data = archive.read(item)
        if len(data) <= MAX_EVIDENCE_FILE_BYTES:
            result[safe] = hashlib.sha256(data).hexdigest()
    return result


def _non_comment_lines(content: str, suffix: str) -> list[str]:
    comment_prefixes = ("#",) if suffix == ".py" else ("//", "/*", "*", "*/")
    return [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.strip().startswith(comment_prefixes)
    ]


def _validate_syntax(path: str, content: str) -> None:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == ".py":
        try:
            ast.parse(content, filename=path)
        except SyntaxError as exc:
            raise ProjectValidationError(
                f"Python syntax error in {path} at line {exc.lineno}: {exc.msg}"
            ) from exc
    elif suffix == ".json":
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProjectValidationError(
                f"Invalid JSON in {path} at line {exc.lineno}: {exc.msg}"
            ) from exc
    elif suffix in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}:
        # Catches the common and serious mistake of pasting Python into a JS task.
        python_patterns = (
            r"(?m)^\s*import\s+sys\s*$",
            r"(?m)^\s*for\s+\w+\s+in\s+.+:\s*$",
            r"(?m)^\s*except(?:\s+.+)?:\s*$",
            r"(?m)^\s*print\s*\(",
            r"(?m)^\s*raise\s+SystemExit",
        )
        if any(re.search(pattern, content) for pattern in python_patterns):
            raise ProjectValidationError(
                f"{path} contains Python syntax but this project file requires JavaScript/TypeScript"
            )
    elif suffix == ".java":
        if re.search(r"(?m)^\s*(import\s+sys|def\s+\w+\(|print\s*\()", content):
            raise ProjectValidationError(f"{path} contains non-Java syntax")


def validate_source_snapshot(
    *,
    contents: dict[str, str],
    declared_hashes: dict[str, str],
    required_paths: list[str],
    baseline_hashes: dict[str, str] | None = None,
    previous_hashes: dict[str, str] | None = None,
    require_change: bool = True,
) -> tuple[dict[str, str], dict]:
    if not contents:
        raise ProjectValidationError(
            "No actual project source was submitted. Update the required project modules before submitting."
        )
    if len(contents) > MAX_EVIDENCE_FILES:
        raise ProjectValidationError(
            f"Too many project source files ({len(contents)}); the limit is {MAX_EVIDENCE_FILES}"
        )

    normalised_required = []
    for value in required_paths:
        raw = str(value).replace("\\", "/")
        while raw.startswith("./"):
            raw = raw[2:]
        path = PurePosixPath(raw)
        if not path.parts or path.is_absolute() or ".." in path.parts:
            raise ProjectValidationError(f"Unsafe required project path: {value}")
        normalised_required.append(str(path).rstrip("/"))
    normalised: dict[str, str] = {}
    hashes: dict[str, str] = {}
    total_bytes = 0
    meaningful_files = 0
    for raw_path, content in contents.items():
        path = normalise_source_path(raw_path)
        if not isinstance(content, str):
            raise ProjectValidationError(f"Project evidence must be UTF-8 text: {path}")
        data = content.encode("utf-8")
        total_bytes += len(data)
        if len(data) > MAX_EVIDENCE_FILE_BYTES:
            raise ProjectValidationError(f"Project evidence file is larger than 256 KB: {path}")
        if total_bytes > MAX_EVIDENCE_TOTAL_BYTES:
            raise ProjectValidationError("Project evidence is larger than 3 MB")
        if normalised_required and not any(
            path == required or path.startswith(required + "/")
            for required in normalised_required
        ):
            raise ProjectValidationError(f"Unexpected project evidence path: {path}")
        digest = hashlib.sha256(data).hexdigest()
        if declared_hashes.get(path, "").lower() != digest:
            raise ProjectValidationError(f"Project source hash does not match its content: {path}")
        _validate_syntax(path, content)
        lines = _non_comment_lines(content, PurePosixPath(path).suffix.lower())
        lowered = content.lower()
        placeholder = any(
            marker in lowered
            for marker in (
                "todo: implement", "notimplementederror", "replace this with your code",
                "your code here", "throw new error(\"todo", "throw new error('todo",
            )
        )
        if lines and not placeholder:
            meaningful_files += 1
        normalised[path] = content
        hashes[path] = digest

    missing_roots = [
        required
        for required in normalised_required
        if not any(path == required or path.startswith(required + "/") for path in hashes)
    ]
    if missing_roots:
        raise ProjectValidationError(
            "Required project source is missing: " + ", ".join(missing_roots)
        )
    if meaningful_files == 0:
        raise ProjectValidationError("Required project files contain only placeholders or comments")

    comparison = previous_hashes or baseline_hashes or {}
    changed = sorted(
        path for path, digest in hashes.items()
        if comparison.get(path) != digest
    )
    if require_change and comparison and not changed:
        raise ProjectValidationError(
            "The required project modules have not changed since the previous validated stage"
        )

    return hashes, {
        "files_checked": len(hashes),
        "bytes_checked": total_bytes,
        "changed_files": changed,
        "syntax_checked": True,
        "placeholder_check": True,
    }


def source_snapshot_zip(contents: dict[str, str]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in sorted(contents.items()):
            archive.writestr(normalise_source_path(path), content)
    return buffer.getvalue()
