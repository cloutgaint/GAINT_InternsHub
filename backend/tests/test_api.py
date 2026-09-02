import os
import hashlib
import json
import tempfile
import uuid
import zipfile
from dataclasses import replace
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path


TEST_DB = Path(tempfile.gettempdir()) / f"gaint_test_{uuid.uuid4().hex}.db"
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["PAYMENT_PROVIDER"] = "demo"
os.environ["AI_PROVIDER"] = "safe-local"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.config import clean_secret  # noqa: E402


def test_deployment_secrets_are_normalized():
    assert clean_secret("  rzp_live_example\n") == "rzp_live_example"
    assert clean_secret("'live-secret' ") == "live-secret"
    assert clean_secret('\"live-secret\"') == "live-secret"


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def vscode_auth(token: str) -> dict:
    return {**auth(token), "X-GAINT-Client": "vscode-extension"}


def login(client: TestClient, email: str, password: str, role: str) -> dict:
    response = client.post("/api/auth/login", json={"email": email, "password": password, "role": role})
    assert response.status_code == 200, response.text
    return response.json()


def register_individual(client: TestClient, email: str, internship_type: str = "FASTTRACK") -> dict:
    response = client.post("/api/auth/register", data={
        "name": "Individual Student", "email": email, "mobile": "9876543210",
        "password": "Student@123", "pursuing_year": "B.Tech 3rd Year",
        "internship_type": internship_type,
    })
    assert response.status_code == 201, response.text
    assert response.json()["user"]["enrollment_type"] == "INDIVIDUAL"
    verified = client.post("/api/auth/verify-contact", headers=auth(response.json()["token"]), json={"code": "123456"})
    assert verified.status_code == 200 and verified.json()["email_verified"] is True
    return response.json()


def mock_judge0(monkeypatch):
    import app.main as main_module
    monkeypatch.setattr(main_module, "submit_tests", lambda source, language, cases: [f"token-{index}" for index, _ in enumerate(cases)])
    monkeypatch.setattr(main_module, "fetch_results", lambda tokens: [
        {"token": token, "status_id": 3, "status": "Accepted", "time": "0.01", "memory": 2048,
         "stdout": "", "stderr": "", "compile_output": "", "message": ""} for token in tokens
    ])


def download_and_connect_vscode(client: TestClient, website_token: str) -> tuple[str, bytes]:
    headers = auth(website_token)
    acknowledged = client.post("/api/student/guide/acknowledge", headers=headers)
    assert acknowledged.status_code == 200, acknowledged.text
    starter = client.get("/api/student/starter-project", headers=headers)
    assert starter.status_code == 200, starter.text
    with zipfile.ZipFile(BytesIO(starter.content)) as archive:
        manifest_name = next(name for name in archive.namelist() if name.endswith("gaint-project.json"))
        manifest = __import__("json").loads(archive.read(manifest_name))
        assert manifest["format_version"] == 8
        assert manifest["workspace_bootstrap"].startswith("gaint_boot_")
    response = client.post("/api/vscode/bootstrap", json={"token": manifest["workspace_bootstrap"]})
    assert response.status_code == 201, response.text
    assert response.json()["token"].startswith("gaint_vsc_")
    assert response.json()["expires_at"].startswith("9999-12-31")
    return response.json()["token"], starter.content


def pass_task(client: TestClient, device_token: str, task: dict, language: str = "python") -> dict:
    project_file_contents = {}
    suffix = {"python": ".py", "javascript": ".js", "java": ".java"}[language]
    for required in task.get("required_paths", []):
        path = required if Path(required).suffix else f"{required.rstrip('/')}/student_work{suffix}"
        if path.endswith(".json"):
            content = json.dumps({"name": "student-work", "taskStage": task["order_no"]})
        elif language == "javascript":
            content = f"export const taskStage = {task['order_no']};\n"
        elif language == "java":
            content = f"class StudentWork {{ static int taskStage = {task['order_no']}; }}\n"
        else:
            content = (
                f'"""Validated real project work for task {task["order_no"]}."""\n'
                f'TASK_STAGE = {task["order_no"]}\n'
            )
        project_file_contents[path] = content
    required_file_hashes = {
        path: hashlib.sha256(content.encode()).hexdigest()
        for path, content in project_file_contents.items()
    }
    created = client.post(
        f"/api/vscode/tasks/{task['id']}/evaluate", headers=vscode_auth(device_token),
        json={
            "language": language, "source_code": "print('project checkpoint')",
            "file_name": task["checkpoint_file"],
            "explanation": "Implemented the selected project task and tested edge cases locally.",
            "required_file_hashes": required_file_hashes,
            "project_file_contents": project_file_contents,
            "local_check_results": [
                {"command": command, "passed": True, "output": "passed"}
                for command in task.get("local_checks", [])
            ],
        },
    )
    assert created.status_code == 201, created.text
    result = client.get(f"/api/vscode/evaluations/{created.json()['id']}", headers=auth(device_token))
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "PASSED"
    return {**result.json(), "project_file_contents": project_file_contents}


def test_individual_payment_vscode_and_automatic_certificate(monkeypatch):
    mock_judge0(monkeypatch)
    with TestClient(app) as client:
        registered = register_individual(client, "individual@example.com")
        website_token = registered["token"]
        headers = auth(website_token)
        assert client.put("/api/student/preferences", headers=headers, json={
            "preferred_language": "Python", "area_interest": "AI services", "internship_type": "FASTTRACK",
        }).status_code == 200
        projects = client.get("/api/student/projects", headers=headers).json()
        assert projects and all(item["individual_fee_rupees"] >= 0 for item in projects)
        assert client.post(f"/api/student/projects/{projects[0]['id']}/select", headers=headers).status_code == 200

        dashboard = client.get("/api/student/dashboard", headers=headers).json()
        assert dashboard["attendance"] is None
        assert dashboard["assignment"]["payment"]["status"] == "PENDING"
        assert not dashboard["assignment"]["access_enabled"]
        assert client.get("/api/student/starter-project", headers=headers).status_code == 402
        assert client.post("/api/student/attendance/check-in", headers=headers).status_code == 403

        payment_id = dashboard["assignment"]["payment"]["id"]
        rejected = client.post(
            f"/api/student/payments/{payment_id}/demo-confirm",
            headers=headers,
            json={"terms_accepted": False},
        )
        assert rejected.status_code == 400
        paid = client.post(
            f"/api/student/payments/{payment_id}/demo-confirm",
            headers=headers,
            json={"terms_accepted": True},
        )
        assert paid.status_code == 200 and paid.json()["receipt_number"].startswith("GAINT-RCPT-")
        assert client.get("/api/student/starter-project", headers=headers).status_code == 409

        device_token, starter_content = download_and_connect_vscode(client, website_token)
        with zipfile.ZipFile(BytesIO(starter_content)) as archive:
            assert any(name.endswith("gaint-project.json") for name in archive.namelist())
            tasks_text = next(archive.read(name).decode() for name in archive.namelist() if name.endswith("TASKS.md"))
            assert "Project Milestones" in tasks_text
            assert any(name.endswith("database/local.db") for name in archive.namelist())
            assert any(name.endswith("STUDENT_PROJECT_GUIDE.md") for name in archive.namelist())
            assert any(name.endswith("GAINT-Interns-Hub-4.1.0.vsix") for name in archive.namelist())
            assert not any(name.endswith("INSTALL_GAINT_EXTENSION.bat") for name in archive.namelist())
            open_script = next(
                archive.read(name).decode()
                for name in archive.namelist()
                if name.endswith("OPEN_IN_VSCODE.bat")
            )
            assert 'code --install-extension "%VSIX%" --force' in open_script
            assert "code --list-extensions --show-versions" in open_script
            assert 'code -n "%~dp0"' in open_script

        assignment = client.get("/api/vscode/assignment", headers=auth(device_token)).json()
        task = assignment["tasks"][0]
        assert "intake validator" in task["challenge_prompt"].lower()
        assert "3 checks" in task["challenge_prompt"].lower()

        explained = client.post(
            "/api/student/ai/current-task",
            headers=headers,
            json={"task_id": task["id"], "action": "EXPLAIN"},
        )
        assert explained.status_code == 200, explained.text
        assert explained.json()["task_id"] == task["id"]
        assert "milestone" in explained.json()["response"].lower()
        hinted = client.post(
            "/api/student/ai/current-task",
            headers=headers,
            json={"task_id": task["id"], "action": "HINT"},
        )
        assert hinted.status_code == 200, hinted.text
        assert "hint only" in hinted.json()["response"].lower()

        chat = client.post(
            "/api/student/ai/chat",
            headers=headers,
            json={"message": "Explain my current task in simple steps."},
        )
        assert chat.status_code == 200, chat.text
        assert chat.json()["provider"] == "safe-local"
        assert chat.json()["remaining_messages"] == 29
        refused = client.post(
            "/api/student/ai/chat",
            headers=headers,
            json={"message": "Give me full code and the complete answer."},
        )
        assert refused.status_code == 200
        assert "cannot provide the complete answer" in refused.json()["message"]["text"].lower()
        history = client.get("/api/student/ai/chat/history", headers=headers)
        assert history.status_code == 200
        assert len(history.json()["messages"]) == 4
        assert history.json()["task_id"] == task["id"]
        assert client.delete("/api/student/ai/chat/history", headers=headers).status_code == 204
        cleared = client.get("/api/student/ai/chat/history", headers=headers).json()
        assert cleared["messages"] == []
        assert cleared["remaining_messages"] == 28

        passed = pass_task(client, device_token, task)
        assert client.get("/api/student/certificate", headers=headers).status_code == 403
        final_hashes = {
            path: hashlib.sha256(content.encode()).hexdigest()
            for path, content in passed["project_file_contents"].items()
        }
        packaged = client.post(
            "/api/vscode/final-package",
            headers=auth(device_token),
            json={
                "fingerprint": "b" * 64,
                "filename": "GAINT_Completed.zip",
                "required_file_hashes": final_hashes,
                "project_file_contents": passed["project_file_contents"],
                "local_check_results": [
                    {"command": command, "passed": True, "output": "passed"}
                    for command in assignment.get("final_local_checks", [])
                ],
            },
        )
        assert packaged.status_code == 200, packaged.text
        assert client.get("/api/student/certificate", headers=headers).content.startswith(b"%PDF")
        assert client.get("/api/student/evaluation-report", headers=headers).content.startswith(b"%PDF")

        mentor = login(client, "mentor@gaint.com", "Mentor@123", "mentor")
        mentor_headers = auth(mentor["token"])
        mentor_data = client.get("/api/mentor/dashboard", headers=mentor_headers).json()
        assert mentor_data["permissions"]["can_review_tasks"] is False
        assert mentor_data["permissions"]["can_unlock_tasks"] is False
        assert mentor_data["summary"]["individual_students"] >= 1
        assert "assignments" not in mentor_data


def test_razorpay_order_signature_and_access_activation(monkeypatch):
    import app.main as main_module
    import app.payment_gateway as gateway_module

    razorpay_settings = replace(
        main_module.settings,
        payment_provider="razorpay",
        razorpay_key_id="rzp_test_example",
        razorpay_key_secret="test-secret-not-for-production",
    )
    monkeypatch.setattr(main_module, "settings", razorpay_settings)
    monkeypatch.setattr(gateway_module, "settings", razorpay_settings)
    monkeypatch.setattr(
        main_module,
        "create_razorpay_order",
        lambda **_: {"id": "order_TestOrder123", "amount": 99900, "currency": "INR"},
    )
    monkeypatch.setattr(main_module, "verify_checkout_signature", lambda **_: True)
    monkeypatch.setattr(
        main_module,
        "fetch_razorpay_payment",
        lambda _: {
            "id": "pay_TestPayment123",
            "order_id": "order_TestOrder123",
            "amount": 99900,
            "currency": "INR",
            "status": "captured",
        },
    )

    with TestClient(app) as client:
        registered = register_individual(client, "razorpay-test@example.com")
        headers = auth(registered["token"])
        assert client.put(
            "/api/student/preferences",
            headers=headers,
            json={
                "preferred_language": "Python",
                "area_interest": "AI services",
                "internship_type": "FASTTRACK",
            },
        ).status_code == 200
        project = client.get("/api/student/projects", headers=headers).json()[0]
        assert client.post(f"/api/student/projects/{project['id']}/select", headers=headers).status_code == 200
        dashboard = client.get("/api/student/dashboard", headers=headers).json()
        payment = dashboard["assignment"]["payment"]
        assert payment["provider"] == "razorpay"

        order = client.post(
            f"/api/student/payments/{payment['id']}/razorpay/order",
            headers=headers,
            json={"terms_accepted": True},
        )
        assert order.status_code == 200, order.text
        assert order.json()["order_id"] == "order_TestOrder123"
        assert order.json()["key_id"] == "rzp_test_example"

        verified = client.post(
            f"/api/student/payments/{payment['id']}/razorpay/verify",
            headers=headers,
            json={
                "razorpay_order_id": "order_TestOrder123",
                "razorpay_payment_id": "pay_TestPayment123",
                "razorpay_signature": "a" * 64,
            },
        )
        assert verified.status_code == 200, verified.text
        assert verified.json()["status"] == "PAID"
        assert verified.json()["receipt_number"].startswith("GAINT-RCPT-")
        dashboard = client.get("/api/student/dashboard", headers=headers).json()
        assert dashboard["assignment"]["access_enabled"] is True


def test_admin_generates_college_credentials_and_coordinator_is_restricted():
    with TestClient(app) as client:
        admin = login(client, "admin@gaint.com", "Admin@123", "admin")
        admin_headers = auth(admin["token"])
        projects = client.get("/api/admin/projects", headers=admin_headers).json()
        allowed = next(item for item in projects if item["technology"] == "Java" and item["internship_type"] == "FASTTRACK")
        created = client.post("/api/admin/coordinators", headers=admin_headers, json={
            "name": "City Coordinator", "email": "city.coordinator@example.com", "password": "Coordinator@123",
            "college_name": "City College", "mou_number": "CITY-MOU-001", "student_limit": 2,
            "allowed_project_ids": [allowed["id"]], "starts_on": str(date.today()),
            "ends_on": str(date.today() + timedelta(days=30)),
        })
        assert created.status_code == 201, created.text
        credentials = created.json()["student_credentials"]
        assert len(credentials) == 2 and credentials[0]["temporary_password"]

        college_login = login(client, credentials[0]["email"], credentials[0]["temporary_password"], "student")
        college_headers = auth(college_login["token"])
        assert college_login["user"]["must_change_password"] is True
        changed = client.post("/api/auth/change-password", headers=college_headers, json={
            "current_password": credentials[0]["temporary_password"], "new_password": "Private@123",
        })
        assert changed.status_code == 200 and changed.json()["must_change_password"] is False
        assert client.put("/api/student/preferences", headers=college_headers, json={
            "preferred_language": "Java", "area_interest": "APIs", "internship_type": "FASTTRACK",
        }).status_code == 200
        suggestions = client.get("/api/student/projects", headers=college_headers).json()
        assert [item["id"] for item in suggestions] == [allowed["id"]]
        assert client.post(f"/api/student/projects/{allowed['id']}/select", headers=college_headers).status_code == 200
        dashboard = client.get("/api/student/dashboard", headers=college_headers).json()
        assert dashboard["assignment"]["payment"] is None and dashboard["assignment"]["access_enabled"]
        assert dashboard["attendance"] is not None

        coordinator = login(client, "city.coordinator@example.com", "Coordinator@123", "coordinator")
        coordinator_data = client.get("/api/coordinator/dashboard", headers=auth(coordinator["token"])).json()
        assert all(row["student"]["enrollment_type"] == "COLLEGE" for row in coordinator_data["students"])
        assert not any(row["student"]["email"] == "individual@example.com" for row in coordinator_data["students"])
        assert coordinator_data["mou_access"]["used_seats"] == 1


def test_45_day_tasks_unlock_immediately_and_sequentially(monkeypatch):
    mock_judge0(monkeypatch)
    with TestClient(app) as client:
        registered = register_individual(client, "learning@example.com", "45_DAYS")
        headers = auth(registered["token"])
        client.put("/api/student/preferences", headers=headers, json={
            "preferred_language": "Node.js", "area_interest": "Backend APIs", "internship_type": "45_DAYS",
        })
        project = client.get("/api/student/projects", headers=headers).json()[0]
        assert project["task_count"] == 3
        client.post(f"/api/student/projects/{project['id']}/select", headers=headers)
        payment = client.get("/api/student/dashboard", headers=headers).json()["assignment"]["payment"]
        client.post(
            f"/api/student/payments/{payment['id']}/demo-confirm",
            headers=headers,
            json={"terms_accepted": True},
        )
        device_token, _ = download_and_connect_vscode(client, registered["token"])
        assignment = client.get("/api/vscode/assignment", headers=auth(device_token)).json()
        assert assignment["tasks"][0]["unlocked"] and not assignment["tasks"][1]["unlocked"]
        pass_task(client, device_token, assignment["tasks"][0], "javascript")
        assignment = client.get("/api/vscode/assignment", headers=auth(device_token)).json()
        assert assignment["tasks"][1]["unlocked"] and assignment["passed_tasks"] == 1


def test_project_generators_and_removed_legacy_inputs():
    with TestClient(app) as client:
        admin = login(client, "admin@gaint.com", "Admin@123", "admin")
        headers = auth(admin["token"])
        generated = client.post("/api/admin/projects/generate", headers=headers, json={
            "technology": "Next.js", "internship_type": "SEMESTER", "domain": "Education", "difficulty": "Intermediate", "count": 2,
        })
        assert generated.status_code == 201 and all(item["task_count"] == 8 for item in generated.json())

        source = BytesIO()
        with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("CompleteApp/frontend/package.json", '{"scripts":{"build":"vite build"},"dependencies":{"react":"18"}}')
            archive.writestr("CompleteApp/frontend/src/App.jsx", "export default function App(){return <main>Ready</main>}")
            archive.writestr("CompleteApp/backend/requirements.txt", "fastapi\npytest\n")
            archive.writestr("CompleteApp/backend/app/main.py", "from fastapi import FastAPI\napp=FastAPI()\n")
            archive.writestr("CompleteApp/backend/tests/test_smoke.py", "def test_ready(): assert True\n")
            archive.writestr("CompleteApp/database/schema.sql", "CREATE TABLE records(id INTEGER PRIMARY KEY);\n")
            archive.writestr("CompleteApp/README.md", "# Complete app\n")
        uploaded = client.post(
            "/api/admin/projects/upload-complete",
            headers=headers,
            data={
                "title": "Verified Full Stack Campus System",
                "technology": "AUTO",
                "internship_type": "45_DAYS",
                "domain": "Education",
                "difficulty": "Intermediate",
                "description": "A complete React and FastAPI campus project for local presentation.",
                "individual_fee_rupees": "1499",
            },
            files={"project_zip": ("complete-app.zip", source.getvalue(), "application/zip")},
        )
        assert uploaded.status_code == 201, uploaded.text
        analysis = uploaded.json()["analysis"]
        assert analysis["available_tracks"][:3] == ["FULL_STACK", "FRONTEND", "BACKEND"]
        assert analysis["track_languages"]["FRONTEND"] == "javascript"
        assert analysis["track_languages"]["BACKEND"] == "python"
        assert analysis["track_required_paths"]["FULL_STACK"] == ["frontend", "backend", "database"]
        uploaded_id = uploaded.json()["project"]["id"]
        assert client.post(f"/api/admin/projects/{uploaded_id}/publish", headers=headers).status_code == 200

        coordinator_created = client.post("/api/admin/coordinators", headers=headers, json={
            "name": "Team Coordinator",
            "email": "team.coordinator@example.com",
            "password": "Coordinator@123",
            "college_name": "Team Engineering College",
            "mou_number": "TEAM-MOU-001",
            "student_limit": 2,
            "allowed_project_ids": [uploaded_id],
            "starts_on": str(date.today()),
            "ends_on": str(date.today() + timedelta(days=30)),
        })
        assert coordinator_created.status_code == 201, coordinator_created.text
        coordinator_payload = coordinator_created.json()
        team_credentials = coordinator_payload["student_credentials"]
        assert len(team_credentials) == 2
        member_tokens = [
            login(
                client,
                credential["email"],
                credential["temporary_password"],
                "student",
            )["token"]
            for credential in team_credentials
        ]
        team = client.post("/api/admin/teams", headers=headers, json={
            "name": "Campus Full Stack Team",
            "project_id": uploaded_id,
            "coordinator_id": coordinator_payload["coordinator"]["id"],
            "members": [
                {"student_id": team_credentials[0]["student_id"], "track": "FRONTEND"},
                {"student_id": team_credentials[1]["student_id"], "track": "BACKEND"},
            ],
        })
        assert team.status_code == 201, team.text
        team_data = team.json()
        assert {member["track"] for member in team_data["members"]} == {"FRONTEND", "BACKEND"}
        assert team_data["combined_package_ready"] is False
        assert client.get(
            "/api/student/team", headers=auth(member_tokens[0])
        ).json()["id"] == team_data["id"]
        coordinator_token = login(
            client, "team.coordinator@example.com", "Coordinator@123", "coordinator"
        )["token"]
        coordinator_teams = client.get(
            "/api/coordinator/teams", headers=auth(coordinator_token)
        )
        assert coordinator_teams.status_code == 200
        assert coordinator_teams.json()[0]["id"] == team_data["id"]

        schema = str(client.get("/openapi.json").json()).lower()
        assert "commit_id" not in schema and "final-project" not in schema
        extension = (Path(__file__).parents[2] / "vscode-extension" / "extension.js").read_text()
        assert "enter the unlocked task id" not in extension.lower()
        assert "findprojectroot" in extension.lower()
        assert "workspace_bootstrap" in extension
        assert "packagecompletedproject" in extension.lower()
