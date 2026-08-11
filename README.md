# GAINT Interns Hub V8.1

## Checkpoint submission fix

A correct `gaint_checkpoints/task_N.*` submission no longer requires students
to edit `README.md` or another unrelated project file. Required project files
are still inspected, configured local checks still run, and every Judge0 case
must pass before the next task unlocks.

GAINT Interns Hub is a PostgreSQL-backed internship platform for college and
individual students. Students complete sequential, project-related work in
local VS Code. The next task opens only after required project evidence, local
checks and all Judge0 checks pass. Completing every task automatically enables
the certificate and creates a clean, runnable local-project ZIP.

## Final rules

- College students use Admin-generated credentials under an active MOU and do
  not pay.
- Individual students self-register and make one project-access payment.
- Payment gives access and evaluation attempts; it never guarantees a pass,
  certificate or completed-project package.
- Individual students who fail can correct and retry until the project access
  and grace period ends. No second payment is charged for retries.
- Only the current task is visible. Future questions and hidden tests stay on
  the backend.
- Task completion requires the correct checkpoint file, a validated snapshot of
  required real project modules, passing local commands, and every Judge0 case.
- The certificate is blocked until the final whole-project source snapshot and
  build/test commands pass.
- No Git, commit ID, manual Task ID, browser code form, full student-project
  upload, or copied VS Code token is used.
- Mentor access is aggregate analytics only. Mentors do not review, conduct a
  viva, pass a task, unlock work, or issue a certificate.
- College Coordinators can see only their own college students.
- The platform uses PostgreSQL. Downloaded student projects use an included
  SQLite database for simple offline/local presentation and need no Docker.

## Internship sizes

| Program | Sequential tasks | Grace after access |
| --- | ---: | ---: |
| FastTrack | 1 | 7 days |
| 45 Days | 3 | 15 days |
| Semester | 8 | 30 days |

The program controls project depth, not an artificial waiting timer.

## Project tracks

An uploaded complete project is analysed for available tracks. A student can
choose one allowed track before assignment:

- Frontend
- Backend
- Full Stack
- Database
- AI/ML
- Mobile

Admin-uploaded projects should contain source only. `node_modules`, `.venv`,
`.git`, caches, compiled builds and other dependency folders are ignored.
GAINT adds the local database, setup scripts, student guide, project milestones,
checkpoint files, and hidden evaluation configuration.

## Run the platform on Windows

Requirements:

- Docker Desktop
- Python 3.11 or newer
- Node.js 20 or newer
- VS Code for the student workflow

1. Start Docker Desktop and wait until the engine is running.
2. Extract this ZIP.
3. Open PowerShell in the extracted `gaint-interns-hub` folder.
4. Run:

```powershell
.\start-windows.bat
```

The script starts an isolated V8.1 PostgreSQL Compose project, creates
`backend\.venv`, installs backend/frontend dependencies, and opens the two
development servers.

- App: `http://localhost:5173`
- API documentation: `http://127.0.0.1:8000/docs`
- API health: `http://127.0.0.1:8000/api/health`

Use `.\stop-windows.bat` when finished. PostgreSQL data remains in the
`gaint_v8_1_postgres_data` Docker volume.

If PowerShell says a `.bat` command is not recognized, include the `.\` prefix.
If an old V6/V7/V8 container exists, it does not conflict because V8.1 uses its own
Compose project and does not set a fixed container name.

## Demo accounts

| Role | Email | Password |
| --- | --- | --- |
| Admin | `admin@gaint.com` | `Admin@123` |
| Mentor | `mentor@gaint.com` | `Mentor@123` |
| Demo Coordinator | `coordinator@gaint.com` | `Coordinator@123` |
| Demo College Student | `student@gaint.com` | `Student@123` |

The demo verification code is `123456`. Change all demo passwords, the
`SECRET_KEY`, payment mode, verification mode and Judge0 configuration before
production.

## Individual payments

College students never see a payment step. Individual students receive one
payment record after selecting a project. A successful payment is saved in
PostgreSQL and is not requested again for task retries.

For simple local flow testing, keep this in `backend/.env`:

```env
PAYMENT_PROVIDER=demo
```

For Razorpay Test Mode, generate a fresh test key in the Razorpay Dashboard and
configure only the private backend file:

```env
PAYMENT_PROVIDER=razorpay
RAZORPAY_KEY_ID=your_test_key_id
RAZORPAY_KEY_SECRET=your_test_key_secret
RAZORPAY_WEBHOOK_SECRET=your_separate_webhook_secret
```

Restart the backend after changing these values. The student button becomes
**Pay securely**, the backend creates the Razorpay order, Checkout opens, and
the backend verifies the signature, order, amount, currency and captured status
before activating project access. The Key Secret is never sent to React.

Test Mode uses simulated transactions. Regenerate any key that has been shared
in chat, screenshots, source control or documentation. A production webhook
needs a public HTTPS endpoint; `localhost` cannot directly receive Razorpay
webhooks.

## Student: simple local workflow

1. Select the program, technology, project and available track.
2. College: continue free under MOU. Individual: accept the payment policy and
   complete the one-time project payment.
3. Read and acknowledge the Student Project Guide.
4. Install VS Code once from `https://code.visualstudio.com/download`.
5. Download the starter ZIP, right-click it and select **Extract All**.
6. Double-click `OPEN_IN_VSCODE.bat`. It installs the included GAINT VSIX,
   verifies that VS Code registered version 4.1.0, and opens the correct project
   folder automatically. Students do not use a separate extension installer.
7. Read `CURRENT_TASK.md` and the red Current Task Question, implement the real project milestone, and complete
   `gaint_checkpoints/task_N.*`.
8. Test the code in the VS Code terminal, press `Ctrl+Shift+P`, and run
   `GAINT: Submit Current Task`.
9. Fix any failed project/local/Judge0 check and submit again.
10. After the final task and final whole-project validation pass, the formal
    signed certificate with its unique ID and verification QR appears, and the extension creates
    `GAINT_Completed_<project>.zip` beside the project folder.
11. Double-click `START_PROJECT.bat` to run the clean completed project locally
    for the college presentation.

The included extension connects from the private bootstrap inside
`gaint-project.json`. It remains repairable throughout the internship and grace
period. If VS Code storage is cleared, run **GAINT: Repair Project
Connection**—no copied token is needed. After connecting, the installed
VS Code connection has no time-based expiry (`VSCODE_TOKEN_DAYS=0`). Admin
revocation, inactive project access, an expired college MOU, a disabled account,
or a database reset can still stop access. The student never copies a token.

## Admin project workflow

1. Open **Projects**.
2. Upload a complete runnable source ZIP, generate a catalogue project, generate
   from a brief, or create a predefined project from details.
3. Set technology, FastTrack/45 Days/Semester, fee and allowed tracks.
4. Review detected stack, source-file count, generated milestones, required
   paths, local checks and hidden cases.
5. Publish the project.
6. Add it to the required college MOU or leave it available to individual
   students.

## College MOU workflow

1. Admin creates the Coordinator, college name, MOU number, start/end dates,
   active status, 1–500 limit and allowed projects.
2. The backend automatically generates student credentials up to the limit.
3. Admin downloads the one-time credential CSV and distributes it privately.
4. A student changes the temporary password on first login; the seat activates
   only when a valid seat is available.
5. Coordinator monitors only that college's attendance, selected projects,
   progress and Judge0 status, and can download its progress CSV.
6. Only Admin can alter MOU dates, status, seats or project access.

## Optional college team workflow

1. Admin opens **College Teams** and chooses an MOU-approved uploaded full-stack
   project.
2. Admin assigns one unused college student to Frontend and another to Backend.
3. Each student works only in the required folders for that track.
4. Both students pass checkpoint, real-source and final-project validation.
5. Coordinator monitors both streams but cannot pass or unlock work.
6. GAINT merges the validated work, rejects conflicting files, and enables one
   combined runnable team ZIP after every member finishes.

## Role boundary

| Role | Access |
| --- | --- |
| Student | Own onboarding, project, current task, results, certificate and local package |
| Mentor | Aggregate MOUs, students, stacks, programs, started/in-progress/completed counts |
| Coordinator | Assigned-college students, attendance, project progress and report |
| Admin | All students/reports, MOU access, credentials, projects, tasks, payments, certificates and audit history |

## AI support

The student dashboard includes the **GAINT Learning Assistant**, a complete
current-task chat panel with:

- saved conversation history for the current task;
- quick actions for task explanation, a progressive hint and VS Code submission;
- project, installation, local-run, error and Judge0 guidance;
- a configurable 30-message rolling daily limit;
- a safe local assistant that works without an API key; and
- optional live OpenAI Responses API support.

The assistant receives only the current unlocked task. It never provides a
ready-to-submit answer, complete source code, hidden test, pass result, task
unlock or certificate. Judge0 and required local project checks remain the only
pass/fail authority.

For a completely local presentation, keep:

```env
AI_PROVIDER=safe-local
```

For live conversational AI, edit `backend/.env`, set `AI_PROVIDER=openai`,
add a server-side `OPENAI_API_KEY`, and restart the backend. Never place the API
key in React, the browser or the student project ZIP.

## Judge0

`backend/.env.example` points to the public Judge0 endpoint for local testing:

```env
JUDGE0_URL=https://ce.judge0.com
JUDGE0_PYTHON_ID=109
JUDGE0_JAVASCRIPT_ID=63
JUDGE0_JAVA_ID=62
```

A Judge0 outage returns a retryable error and never counts as a failed or passed
task. For reliable production use, deploy a private Judge0 instance and update
the URL/language IDs.

## PostgreSQL

The platform starts PostgreSQL 16 on host port `55432`:

```env
DATABASE_URL=postgresql+psycopg://gaint:gaint_local_password@localhost:55432/gaint_interns
```

Use a strong database password, Alembic migrations, backups, HTTPS, signed
payment webhooks, email/SMS verification, object storage and rate limiting
before public deployment.

## Validation

The delivery was checked with:

```text
Backend: 10 API and validation tests passed
Frontend: Vite production build passed
Extension: Node syntax validation passed
Python: full app compile passed
```

The tests cover individual demo and Razorpay payment activation, payment policy,
retry access, no individual attendance, built-in workspace bootstrap, guarded
chatbot replies and history, local project evidence, automatic certificate,
college credentials/MOU isolation, sequential unlocking, aggregate mentor
permissions, college Frontend/Backend teams, project generation, secret/path
protection, and removal of Git/manual Task ID inputs.

*BE commands*

cd backend
python3 -m venv venv
source venv/bin/activate   // .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload