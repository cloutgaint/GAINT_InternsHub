from __future__ import annotations

import json
import stat
import zipfile
from io import BytesIO
from pathlib import PurePosixPath


EXCLUDED = {
    "node_modules", ".venv", "venv", ".git", "__pycache__", ".pytest_cache",
    "dist", "build", ".next", "target", ".idea",
}
FORBIDDEN_SECRET_NAMES = {
    ".env", "id_rsa", "id_ed25519", "credentials.json", "service-account.json",
}
MAX_SOURCE_FILES = 5_000
MAX_UNCOMPRESSED_BYTES = 250 * 1024 * 1024


class ProjectZipError(ValueError):
    pass


def analyse_project_zip(content: bytes) -> dict:
    try:
        archive = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ProjectZipError("Upload a valid ZIP project") from exc

    names: list[str] = []
    uncompressed = 0
    for item in archive.infolist():
        if item.is_dir():
            continue
        if item.flag_bits & 0x1:
            raise ProjectZipError("Encrypted ZIP entries are not supported")
        unix_mode = (item.external_attr >> 16) & 0xFFFF
        if unix_mode and stat.S_ISLNK(unix_mode):
            raise ProjectZipError("The ZIP contains a symbolic link")
        if (
            item.file_size > 10 * 1024 * 1024
            and item.compress_size > 0
            and item.file_size / item.compress_size > 200
        ):
            raise ProjectZipError("The ZIP contains a suspiciously compressed file")
        path = PurePosixPath(item.filename.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts:
            raise ProjectZipError("The ZIP contains an unsafe file path")
        lowered_parts = [part.lower() for part in path.parts]
        filename = path.name.lower()
        if any(part in EXCLUDED for part in lowered_parts):
            continue
        if (
            filename in FORBIDDEN_SECRET_NAMES
            or (filename.startswith(".env.") and filename != ".env.example")
            or filename.endswith((".pem", ".key", ".p12", ".pfx"))
        ):
            raise ProjectZipError(
                f"Remove secret or credential file from the project ZIP: {path.name}"
            )
        names.append(str(path))
        uncompressed += item.file_size
    if not names:
        raise ProjectZipError("The ZIP contains no project source files")
    if len(names) > MAX_SOURCE_FILES:
        raise ProjectZipError(
            f"The source ZIP contains {len(names)} files after dependency folders were ignored; "
            f"the limit is {MAX_SOURCE_FILES}"
        )
    if uncompressed > MAX_UNCOMPRESSED_BYTES:
        raise ProjectZipError("The extracted source project is larger than 250 MB")

    first_parts = {PurePosixPath(name).parts[0] for name in names}
    strip_root = len(first_parts) == 1 and all(len(PurePosixPath(name).parts) > 1 for name in names)
    relative_names = [
        str(PurePosixPath(*PurePosixPath(name).parts[1:])) if strip_root else name
        for name in names
    ]
    lower_names = {name.lower() for name in relative_names}
    basenames = {PurePosixPath(name).name.lower() for name in names}
    technology = "Python"
    if "pom.xml" in basenames:
        technology = "Java"
    elif "manage.py" in basenames:
        technology = "Django"
    elif "package.json" in basenames:
        package_name = next(name for name in names if PurePosixPath(name).name.lower() == "package.json")
        try:
            package = json.loads(archive.read(package_name))
        except (json.JSONDecodeError, KeyError):
            package = {}
        dependencies = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
        technology = "Next.js" if "next" in dependencies else "Node.js"

    def roots_containing(parts_to_find: set[str]) -> list[str]:
        roots: list[str] = []
        for name in relative_names:
            parts = PurePosixPath(name).parts
            lowered = [part.lower() for part in parts]
            for index, part in enumerate(lowered[:-1]):
                if part in parts_to_find:
                    roots.append(str(PurePosixPath(*parts[:index + 1])))
                    break
        return list(dict.fromkeys(roots))

    frontend_roots = roots_containing({"frontend", "client"})
    backend_roots = roots_containing({"backend", "server", "api"})
    database_roots = roots_containing({"database", "db", "migrations"})
    if not frontend_roots and any("/src/pages/" in f"/{name}" or "/src/components/" in f"/{name}" for name in lower_names):
        frontend_roots = ["src"]
    if not backend_roots and any("/controllers/" in f"/{name}" or "/routes/" in f"/{name}" for name in lower_names):
        backend_roots = ["src"]
    if not database_roots:
        database_roots = [
            name for name in relative_names
            if PurePosixPath(name).name.lower() in {"schema.sql", "seed.sql", "alembic.ini"}
        ]

    tracks: list[str] = []
    if frontend_roots:
        tracks.append("FRONTEND")
    if backend_roots:
        tracks.append("BACKEND")
    if database_roots:
        tracks.append("DATABASE")
    if "FRONTEND" in tracks and "BACKEND" in tracks:
        tracks.insert(0, "FULL_STACK")
    if not tracks:
        tracks = ["FULL_STACK"]

    track_required_paths = {
        "FRONTEND": frontend_roots,
        "BACKEND": backend_roots,
        "DATABASE": database_roots,
    }
    full_stack_paths = list(dict.fromkeys(frontend_roots + backend_roots + database_roots))
    if full_stack_paths:
        track_required_paths["FULL_STACK"] = full_stack_paths

    def files_under(roots: list[str]) -> list[str]:
        return [
            name for name in relative_names
            if any(name == root or name.startswith(root + "/") for root in roots)
        ]

    backend_files = files_under(backend_roots)
    backend_basenames = {PurePosixPath(name).name.lower() for name in backend_files}
    if "pom.xml" in backend_basenames or any(name.lower().endswith(".java") for name in backend_files):
        backend_language = "java"
    elif (
        "requirements.txt" in backend_basenames
        or "manage.py" in backend_basenames
        or any(name.lower().endswith(".py") for name in backend_files)
    ):
        backend_language = "python"
    else:
        backend_language = "javascript"
    track_languages = {
        "FRONTEND": "javascript",
        "BACKEND": backend_language,
        "DATABASE": "python",
        "FULL_STACK": backend_language,
    }

    frontend_command = (
        f"cd {frontend_roots[0]} && npm run build"
        if frontend_roots and "package.json" in {
            PurePosixPath(name).name.lower()
            for name in relative_names
            if name.startswith(frontend_roots[0] + "/")
        } else None
    )
    if backend_language == "python":
        backend_command = f"cd {backend_roots[0]} && python -m pytest -q" if backend_roots else "python -m pytest -q"
    elif backend_language == "java":
        backend_command = f"cd {backend_roots[0]} && mvn test -q" if backend_roots else "mvn test -q"
    else:
        backend_command = f"cd {backend_roots[0]} && npm test" if backend_roots else "npm test"
    track_local_checks = {
        "FRONTEND": [frontend_command] if frontend_command else [],
        "BACKEND": [backend_command] if backend_roots else [],
        "DATABASE": [],
    }
    track_local_checks["FULL_STACK"] = list(dict.fromkeys(
        track_local_checks["BACKEND"] + track_local_checks["FRONTEND"]
    ))
    source_extensions = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".html", ".css", ".sql"}
    source_code_files = [
        name for name in relative_names
        if PurePosixPath(name).suffix.lower() in source_extensions
    ]
    validation_issues: list[str] = []
    if not source_code_files:
        validation_issues.append("No supported project source-code files were detected")
    if "FULL_STACK" in tracks and not full_stack_paths:
        validation_issues.append(
            "Full-stack source folders could not be identified; use frontend/backend/database folders"
        )

    return {
        "technology": technology,
        "available_tracks": list(dict.fromkeys(tracks)),
        "track_required_paths": track_required_paths,
        "track_local_checks": track_local_checks,
        "track_languages": track_languages,
        "source_file_count": len(names),
        "uncompressed_bytes": uncompressed,
        "has_readme": "readme.md" in basenames,
        "has_schema": "schema.sql" in basenames,
        "has_seed": "seed.sql" in basenames,
        "has_windows_start": any(name.lower().endswith((".bat", ".cmd")) for name in names),
        "source_code_file_count": len(source_code_files),
        "validation_issues": validation_issues,
        "publish_ready": not validation_issues,
        "sample_paths": relative_names[:30],
    }
