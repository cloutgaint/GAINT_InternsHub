from __future__ import annotations

import json
import re
import sqlite3
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path, PurePosixPath

from .config import BASE_DIR, settings


EXCLUDED_PARTS = {
    "node_modules", ".venv", "venv", ".git", "__pycache__", ".pytest_cache",
    "dist", "build", ".next", "target", ".idea",
}
FORBIDDEN_SECRET_NAMES = {
    ".env", "id_rsa", "id_ed25519", "credentials.json", "service-account.json",
}

GAINT_EXTENSION_ID = "gaint-clout.gaint-interns-hub"
GAINT_EXTENSION_VERSION = "4.1.0"
GAINT_EXTENSION_VSIX = f"GAINT-Interns-Hub-{GAINT_EXTENSION_VERSION}.vsix"


def _safe_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")[:80] or "GAINT_Project"


def _normalised_archive_name(name: str) -> str | None:
    candidate = PurePosixPath(name.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    if not candidate.parts or any(part.lower() in EXCLUDED_PARTS for part in candidate.parts):
        return None
    filename = candidate.name.lower()
    if (
        filename in FORBIDDEN_SECRET_NAMES
        or (filename.startswith(".env.") and filename != ".env.example")
        or filename.endswith((".pem", ".key", ".p12", ".pfx"))
    ):
        return None
    return str(candidate)


def _master_project_files(filename: str | None) -> dict[str, bytes]:
    if not filename:
        return {}
    source = settings.upload_dir / filename
    if not source.exists():
        return {}
    with zipfile.ZipFile(source) as archive:
        safe_names = [
            value for item in archive.infolist()
            if not item.is_dir() and (value := _normalised_archive_name(item.filename))
        ]
        if not safe_names:
            return {}
        first_parts = {PurePosixPath(name).parts[0] for name in safe_names}
        strip_root = len(first_parts) == 1 and all(len(PurePosixPath(name).parts) > 1 for name in safe_names)
        result: dict[str, bytes] = {}
        for name in safe_names[:5000]:
            parts = PurePosixPath(name).parts[1:] if strip_root else PurePosixPath(name).parts
            relative = str(PurePosixPath(*parts))
            if relative:
                result[relative] = archive.read(name)
        return result


def team_completed_project_zip(
    project,
    team_name: str,
    artifact_archives: list[tuple[str, bytes]],
) -> tuple[bytes, str]:
    """Merge validated, role-specific team snapshots into one clean project."""
    files: dict[str, bytes | str] = _master_project_files(project.master_zip_filename)
    if not files:
        files.update(_technology_files(project.technology, project.title))
    owners: dict[str, str] = {}
    for owner, archive_bytes in artifact_archives:
        with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
            for item in archive.infolist():
                if item.is_dir():
                    continue
                relative = _normalised_archive_name(item.filename)
                if not relative:
                    continue
                content = archive.read(item)
                previous_owner = owners.get(relative)
                if (
                    previous_owner
                    and previous_owner != owner
                    and files.get(relative) != content
                ):
                    raise ValueError(
                        f"Team source conflict in {relative}: {previous_owner} and {owner}"
                    )
                files[relative] = content
                owners[relative] = owner
    files.update(_setup_files(project.technology))
    files["TEAM_PROJECT_README.md"] = (
        f"# {team_name}\n\n"
        "This clean project combines the validated role-specific work of all "
        "college team members. Use `START_PROJECT.bat` for the local presentation.\n"
    )
    excluded_roots = {"gaint_checkpoints", "gaint-extension", ".vscode"}
    buffer = BytesIO()
    root = _safe_slug(team_name)
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative, content in sorted(files.items()):
            safe = _normalised_archive_name(relative)
            if not safe or PurePosixPath(safe).parts[0] in excluded_roots:
                continue
            if PurePosixPath(safe).name in {
                "gaint-project.json", "CURRENT_TASK.md", "TASKS.md",
                "OPEN_IN_VSCODE.bat", "STUDENT_PROJECT_GUIDE.md",
            }:
                continue
            archive.writestr(f"{root}/{safe}", content)
    return buffer.getvalue(), f"GAINT_{root}_Completed.zip"


def _local_database_bytes(title: str, assignment_reference: str) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp:
        path = Path(temp.name)
    try:
        connection = sqlite3.connect(path)
        connection.executescript(
            """
            CREATE TABLE project_meta (
                id INTEGER PRIMARY KEY,
                project_title TEXT NOT NULL,
                assignment_reference TEXT NOT NULL
            );
            CREATE TABLE demo_records (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE'
            );
            """
        )
        connection.execute(
            "INSERT INTO project_meta(project_title, assignment_reference) VALUES (?, ?)",
            (title, assignment_reference),
        )
        connection.executemany(
            "INSERT INTO demo_records(name, category, status) VALUES (?, ?, ?)",
            [
                ("Sample Alpha", "General", "ACTIVE"),
                ("Sample Beta", "General", "PENDING"),
                ("Sample Gamma", "General", "CLOSED"),
            ],
        )
        connection.commit()
        connection.close()
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


def _setup_files(technology: str) -> dict[str, str]:
    if technology == "Python":
        windows = r"""@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python src\main.py
pause
"""
        linux = """#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python src/main.py
"""
    elif technology == "Django":
        windows = r"""@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
"""
        linux = """#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
"""
    elif technology in {"Node.js", "Next.js"}:
        command = "npm run dev" if technology == "Next.js" else "npm start"
        windows = f"""@echo off
cd /d "%~dp0"
call npm install
call {command}
"""
        linux = f"""#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
npm install
{command}
"""
    else:
        windows = r"""@echo off
cd /d "%~dp0"
call mvn -q test
call mvn -q package
java -cp target\classes com.gaint.internship.Application
pause
"""
        linux = """#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
mvn -q test
mvn -q package
java -cp target/classes com.gaint.internship.Application
"""
    return {
        "START_PROJECT.bat": windows,
        "start-project.sh": linux,
        "STOP_PROJECT.bat": "@echo off\necho Close the project terminal to stop the local application.\npause\n",
        "OPEN_IN_VSCODE.bat": (
            '@echo off\n'
            'setlocal\n'
            'cd /d "%~dp0"\n'
            'title GAINT Project Setup\n'
            'echo Preparing your GAINT project...\n'
            'where code >nul 2>&1\n'
            'if errorlevel 1 (\n'
            '  echo.\n'
            '  echo ERROR: Visual Studio Code was not found.\n'
            '  echo Install VS Code once from https://code.visualstudio.com/download\n'
            '  echo During installation, select "Add to PATH".\n'
            '  pause\n'
            '  exit /b 1\n'
            ')\n'
            f'set "VSIX=%~dp0{GAINT_EXTENSION_VSIX}"\n'
            'if not exist "%VSIX%" (\n'
            '  echo.\n'
            '  echo ERROR: The included GAINT extension installer is missing.\n'
            '  echo Download the project again from the Student Dashboard.\n'
            '  pause\n'
            '  exit /b 1\n'
            ')\n'
            'echo Installing the included GAINT extension...\n'
            'code --install-extension "%VSIX%" --force >nul\n'
            'if errorlevel 1 (\n'
            '  echo.\n'
            '  echo ERROR: VS Code could not install the GAINT extension.\n'
            '  echo Close all VS Code windows and run this file again.\n'
            '  pause\n'
            '  exit /b 1\n'
            ')\n'
            f'code --list-extensions --show-versions | findstr /I /C:"{GAINT_EXTENSION_ID}@{GAINT_EXTENSION_VERSION}" >nul\n'
            'if errorlevel 1 (\n'
            '  echo.\n'
            '  echo ERROR: GAINT extension installation could not be verified.\n'
            '  echo Close all VS Code windows and run this file again.\n'
            '  pause\n'
            '  exit /b 1\n'
            ')\n'
            'echo GAINT extension is ready.\n'
            'echo Opening the correct project folder in VS Code...\n'
            'code -n "%~dp0"\n'
            'if errorlevel 1 (\n'
            '  echo.\n'
            '  echo ERROR: VS Code could not open the project folder.\n'
            '  pause\n'
            '  exit /b 1\n'
            ')\n'
            'endlocal\n'
        ),
    }


def _student_guide(assignment, project, tasks) -> str:
    return f"""# Student Project Guide

## Your project

- Project: {assignment.variant_title}
- Technology: {project.technology}
- Track: {assignment.selected_track.replace("_", " ").title()}
- Internship: {project.internship_type.replace("_", " ").title()}
- Assignment reference: {assignment.variant_seed}

## Start in six simple steps

1. Install Visual Studio Code once from `https://code.visualstudio.com/download`.
2. Download the project ZIP, right-click it and choose **Extract All**. Do not
   work inside the ZIP.
3. Open the extracted folder and double-click `OPEN_IN_VSCODE.bat`. It installs
   the included GAINT extension automatically and opens the correct folder.
4. Read `CURRENT_TASK.md`, then write your solution in the required
   `gaint_checkpoints/task_N` file and update the listed real project modules.
5. Test the code in the VS Code terminal.
6. Press `Ctrl+Shift+P` and run `GAINT: Submit Current Task`.

The workspace connects automatically. Do not copy a token, enter a Task ID, use
Git, or upload the complete project.

## Evaluation

The extension validates required project files, runs the configured local
checks, and sends the checkpoint plus the required text-source snapshot to GAINT. Judge0
runs one visible check and hidden edge cases. A failed task stays open for
correction; the next task unlocks only after every required check passes.

## Completion

After all {len(tasks)} task(s) pass, the extension creates a clean runnable ZIP
beside this folder. The portal enables the verified certificate and evaluation
report automatically. The clean ZIP excludes dependencies, secrets, hidden
tests and GAINT checkpoint files.

If the extension connection is ever removed, run
`GAINT: Repair Project Connection`; the same starter reconnects automatically
without copying a token.

## Local presentation

Use `START_PROJECT.bat` to run the completed application. This project includes
an embedded local database in `database/local.db`; no GAINT production database
credentials are included.
"""


def starter_project_zip(user, project, assignment, tasks, bootstrap_token: str) -> tuple[bytes, str]:
    technology = project.technology
    files: dict[str, bytes | str] = _master_project_files(project.master_zip_filename)
    if not files:
        files.update(_technology_files(technology, assignment.variant_title))

    files.update(_setup_files(technology))
    files["STUDENT_PROJECT_GUIDE.md"] = _student_guide(assignment, project, tasks)
    files["PRESENTATION_GUIDE.md"] = (
        "# Local College Presentation\n\n"
        "1. Explain the problem and architecture.\n"
        "2. Run `START_PROJECT.bat`.\n"
        "3. Demonstrate the main workflow and validation.\n"
        "4. Show the local database and test evidence.\n"
        "5. Present your certificate QR verification.\n"
    )
    files["README_SETUP.md"] = (
        f"# {assignment.variant_title} — Local Setup\n\n"
        "Install the technology runtime once, then use `START_PROJECT.bat`. "
        "The script installs project dependencies and starts the application.\n"
    )
    files.setdefault(
        "README.md",
        (
            f"# {assignment.variant_title}\n\n"
            f"Technology: {technology}\n\n"
            "Use `START_PROJECT.bat` for the local project presentation. "
            "Read `STUDENT_PROJECT_GUIDE.md` before Task 1.\n"
        ),
    )
    files["database/schema.sql"] = (
        "CREATE TABLE demo_records (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "category TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ACTIVE');\n"
    )
    files["database/seed.sql"] = (
        "INSERT INTO demo_records(name, category, status) VALUES "
        "('Sample Alpha','General','ACTIVE'),('Sample Beta','General','PENDING');\n"
    )
    files["database/postgresql/schema.sql"] = (
        "CREATE TABLE IF NOT EXISTS demo_records ("
        "id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, "
        "status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','PENDING','CLOSED'))"
        ");\n"
    )
    files["database/postgresql/seed.sql"] = (
        "INSERT INTO demo_records(name, category, status) VALUES "
        "('Sample Alpha','General','ACTIVE'),('Sample Beta','General','PENDING');\n"
    )
    files["database/postgresql/README.md"] = (
        "# Optional PostgreSQL setup\n\n"
        "The student presentation uses `database/local.db` and needs no Docker. "
        "These PostgreSQL scripts are included for deployment or advanced demonstrations.\n"
    )
    files["database/local.db"] = _local_database_bytes(assignment.variant_title, assignment.variant_seed)
    files[".vscode/extensions.json"] = json.dumps(
        {"recommendations": ["gaint-clout.gaint-interns-hub"]}, indent=2
    )
    files["gaint-project.json"] = json.dumps({
        "format_version": 8,
        "api_url": settings.public_api_url,
        "workspace_bootstrap": bootstrap_token,
        "student_id": user.id,
        "assignment_id": assignment.id,
        "assignment_reference": assignment.variant_seed,
        "project": assignment.variant_title,
        "technology": technology,
        "track": assignment.selected_track,
        "internship_type": project.internship_type,
        "enrollment_type": user.enrollment_type,
        "task_count": len(tasks),
    }, indent=2)

    task_lines = [
        "# Project Milestones\n",
        "Only the current unlocked question is shown in the portal and extension.\n",
    ]
    base_language = {
        "Python": "python", "Django": "python", "Java": "java",
        "Node.js": "javascript", "Next.js": "javascript",
    }[technology]
    checkpoint_language = (project.stack_metadata or {}).get("track_languages", {}).get(
        assignment.selected_track,
        base_language,
    )
    checkpoint_extension = {"python": "py", "javascript": "js", "java": "java"}[checkpoint_language]
    comment = "#" if checkpoint_language == "python" else "//"
    for task in tasks:
        task_lines.append(f"## Task {task.order_no}: {task.title}\n\n{task.description}\n")
        checkpoint_file = f"gaint_checkpoints/task_{task.order_no}.{checkpoint_extension}"
        files[checkpoint_file] = (
            f"{comment} GAINT Task {task.order_no}: {task.title}\n"
            f"{comment} Open the portal or CURRENT_TASK.md for the current question.\n"
            f"{comment} Write the checkpoint solution below, save, and submit from GAINT.\n"
        )
    first = tasks[0]
    files["CURRENT_TASK.md"] = (
        f"# Task 1: {first.title}\n\n{first.description}\n\n"
        "Open the GAINT Student Dashboard for the visible example and complete instructions.\n"
    )
    files["TASKS.md"] = "\n".join(task_lines)

    extension_dir = BASE_DIR.parent / "vscode-extension"
    extension_vsix = extension_dir / GAINT_EXTENSION_VSIX
    if not extension_vsix.exists():
        raise RuntimeError(
            f"Bundled GAINT extension is missing: {extension_vsix}. "
            "Package the VS Code extension before starting the backend."
        )
    files[GAINT_EXTENSION_VSIX] = extension_vsix.read_bytes()

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        root = _safe_slug(assignment.variant_title)
        for item_path, content in files.items():
            safe_path = _normalised_archive_name(item_path)
            if safe_path:
                archive.writestr(f"{root}/{safe_path}", content)
    return buffer.getvalue(), f"GAINT_{user.id}_{_safe_slug(project.title)}_Starter.zip"


def _technology_files(technology: str, title: str) -> dict[str, str]:
    if technology == "Python":
        return {
            "requirements.txt": "pytest>=8,<9\n",
            "src/main.py": (
                "from pathlib import Path\nimport sqlite3\n\n"
                "def main():\n"
                "    db = Path(__file__).parents[1] / 'database' / 'local.db'\n"
                "    with sqlite3.connect(db) as connection:\n"
                "        count = connection.execute('SELECT COUNT(*) FROM demo_records').fetchone()[0]\n"
                f"    print('{title}')\n    print(f'Local database ready: {{count}} demo records')\n\n"
                "if __name__ == '__main__':\n    main()\n"
            ),
            "tests/test_smoke.py": "from src.main import main\n\ndef test_main_exists():\n    assert callable(main)\n",
        }
    if technology == "Node.js":
        return {
            "package.json": json.dumps({
                "name": _safe_slug(title).lower(), "version": "1.0.0", "type": "module",
                "scripts": {"start": "node src/index.js", "test": "node --test"},
            }, indent=2),
            "src/index.js": "export const health = () => ({ status: 'ready' });\nconsole.log('GAINT Node.js project ready');\n",
            "tests/health.test.js": (
                "import test from 'node:test';\nimport assert from 'node:assert';\n"
                "import { health } from '../src/index.js';\n"
                "test('health', () => assert.equal(health().status, 'ready'));\n"
            ),
        }
    if technology == "Next.js":
        return {
            "package.json": json.dumps({
                "name": _safe_slug(title).lower(), "version": "1.0.0", "private": True,
                "scripts": {"dev": "next dev", "build": "next build", "start": "next start"},
                "dependencies": {"next": "^15.5.0", "react": "^19.1.0", "react-dom": "^19.1.0"},
            }, indent=2),
            "app/layout.js": (
                "export const metadata = { title: 'GAINT Internship Project' };\n"
                "export default function Layout({ children }) { return <html lang=\"en\"><body>{children}</body></html>; }\n"
            ),
            "app/page.js": "export default function Home() { return <main><h1>GAINT Project</h1><p>Local presentation ready.</p></main>; }\n",
        }
    if technology == "Django":
        return {
            "requirements.txt": "Django>=5.1,<6\n",
            "manage.py": (
                "#!/usr/bin/env python\nimport os, sys\n"
                "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')\n"
                "from django.core.management import execute_from_command_line\nexecute_from_command_line(sys.argv)\n"
            ),
            "config/__init__.py": "",
            "config/settings.py": (
                "SECRET_KEY='local-presentation-only'\nDEBUG=True\nROOT_URLCONF='config.urls'\n"
                "ALLOWED_HOSTS=['127.0.0.1','localhost']\nINSTALLED_APPS=[]\nMIDDLEWARE=[]\n"
                "DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':'database/local.db'}}\n"
            ),
            "config/urls.py": (
                "from django.urls import path\nfrom django.http import JsonResponse\n"
                "urlpatterns=[path('', lambda request: JsonResponse({'status':'ready'}))]\n"
            ),
        }
    return {
        "pom.xml": (
            '<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>'
            "<groupId>com.gaint</groupId><artifactId>internship-project</artifactId><version>1.0.0</version>"
            "<properties><maven.compiler.source>21</maven.compiler.source>"
            "<maven.compiler.target>21</maven.compiler.target></properties></project>"
        ),
        "src/main/java/com/gaint/internship/Application.java": (
            'package com.gaint.internship;\npublic class Application { public static void main(String[] args) '
            '{ System.out.println("GAINT Java project ready"); } }\n'
        ),
    }
