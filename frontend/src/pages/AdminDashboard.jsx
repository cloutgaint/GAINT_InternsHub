import {
  Activity,
  Award,
  BarChart3,
  Bot,
  Building2,
  CheckCircle2,
  Code2,
  FolderKanban,
  Plus,
  Send,
  ShieldCheck,
  UserRoundPlus,
  Users,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import Layout from "../components/Layout";
import Notice from "../components/Notice";

const tabs = [
  "Overview",
  "Students",
  "Projects",
  "College Teams",
  "MOU Access",
  "Reports",
];
const technologies = ["Java", "Python", "Node.js", "Next.js", "Django"];
const dateInput = (date) =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
const startDate = dateInput(new Date());
const end = new Date();
end.setFullYear(end.getFullYear() + 1);
const endDate = dateInput(end);

export default function AdminDashboard() {
  const [tab, setTab] = useState("Overview");
  const [stats, setStats] = useState(null);
  const [students, setStudents] = useState([]);
  const [coordinators, setCoordinators] = useState([]);
  const [projects, setProjects] = useState([]);
  const [accessList, setAccessList] = useState([]);
  const [reports, setReports] = useState([]);
  const [payments, setPayments] = useState([]);
  const [teams, setTeams] = useState([]);
  const [credentialSheet, setCredentialSheet] = useState([]);
  const [notice, setNotice] = useState({});

  const load = useCallback(async () => {
    try {
      const result = await Promise.all([
        api("/admin/dashboard"),
        api("/admin/users?role=student"),
        api("/admin/users?role=coordinator"),
        api("/admin/projects"),
        api("/admin/coordinators/access"),
        api("/admin/reports"),
        api("/admin/payments"),
        api("/admin/teams"),
      ]);
      setStats(result[0]);
      setStudents(result[1]);
      setCoordinators(result[2]);
      setProjects(result[3]);
      setAccessList(result[4]);
      setReports(result[5]);
      setPayments(result[6]);
      setTeams(result[7]);
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const submitForm = async (
    event,
    path,
    success,
    transform = (value) => value,
  ) => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      await api(path, {
        method: "POST",
        body: JSON.stringify(transform(Object.fromEntries(new FormData(form)))),
      });
      form.reset();
      setNotice({ type: "success", message: success });
      await load();
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    }
  };

  const mouPayload = (form, includeActive) => {
    const data = new FormData(form);
    const payload = Object.fromEntries(data);
    payload.student_limit = Number(payload.student_limit);
    payload.allowed_project_ids = data
      .getAll("allowed_project_ids")
      .map(Number);
    if (includeActive) payload.active = payload.active === "true";
    return payload;
  };

  const createCoordinator = async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      const result = await api("/admin/coordinators", {
        method: "POST",
        body: JSON.stringify(mouPayload(form, false)),
      });
      setCredentialSheet(result.student_credentials || []);
      form.reset();
      setNotice({
        type: "success",
        message: `Coordinator, MOU and ${result.student_credentials?.length || 0} student credentials created.`,
      });
      await load();
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    }
  };

  const updateMou = async (event, coordinatorId) => {
    event.preventDefault();
    try {
      const result = await api(`/admin/coordinators/${coordinatorId}/mou`, {
        method: "PUT",
        body: JSON.stringify(mouPayload(event.currentTarget, true)),
      });
      setCredentialSheet(result.student_credentials || []);
      setNotice({
        type: "success",
        message: `MOU updated. ${result.student_credentials?.length || 0} new credential(s) created.`,
      });
      await load();
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    }
  };

  const assignCoordinator = async (studentId, value) => {
    try {
      await api(`/admin/students/${studentId}/coordinator`, {
        method: "PUT",
        body: JSON.stringify({ coordinator_id: Number(value) }),
      });
      setNotice({ type: "success", message: "Coordinator assigned." });
      await load();
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    }
  };

  const publish = async (projectId) => {
    try {
      await api(`/admin/projects/${projectId}/publish`, { method: "POST" });
      setNotice({ type: "success", message: "Project published." });
      await load();
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    }
  };

  const createTeam = async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    try {
      await api("/admin/teams", {
        method: "POST",
        body: JSON.stringify({
          name: values.name,
          coordinator_id: Number(values.coordinator_id),
          project_id: Number(values.project_id),
          members: [
            {
              student_id: Number(values.frontend_student_id),
              track: "FRONTEND",
            },
            { student_id: Number(values.backend_student_id), track: "BACKEND" },
          ],
        }),
      });
      form.reset();
      setNotice({
        type: "success",
        message:
          "College team created with separate Frontend and Backend work.",
      });
      await load();
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    }
  };

  const uploadCompleteProject = async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      const result = await api("/admin/projects/upload-complete", {
        method: "POST",
        body: new FormData(form),
      });
      form.reset();
      setNotice({
        type: "success",
        message: `${result.project.title} analysed: ${result.analysis.source_file_count} source files, ${result.analysis.available_tracks.join(", ")} track(s). Review and publish it.`,
      });
      await load();
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    }
  };

  const downloadCredentials = () => {
    const rows = [
      ["Student ID", "Name", "Login email", "Temporary password"],
      ...credentialSheet.map((item) => [
        item.student_id,
        item.name,
        item.email,
        item.temporary_password,
      ]),
    ];
    const csv = rows
      .map((row) =>
        row
          .map((value) => `"${String(value).replaceAll('"', '""')}"`)
          .join(","),
      )
      .join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "GAINT-College-Student-Credentials.csv";
    link.click();
    URL.revokeObjectURL(url);
  };

  if (!stats)
    return (
      <div className="app-loader">
        <span className="spinner" />
        Loading Admin dashboard…
      </div>
    );
  const publishedProjects = projects.filter(
    (project) => project.status === "PUBLISHED" && project.active,
  );
  return (
    <Layout
      title="Admin Dashboard"
      subtitle="Control college MOU access, seats, projects, Mentors and internship reports."
      actions={
        <nav className="top-tabs">
          {tabs.map((item) => (
            <button
              className={tab === item ? "active" : ""}
              onClick={() => setTab(item)}
              key={item}
            >
              {item}
            </button>
          ))}
        </nav>
      }
    >
      <Notice {...notice} onClose={() => setNotice({})} />

      {tab === "Overview" && (
        <>
          <div className="metric-grid admin-metrics six">
            <article>
              <Users />
              <div>
                <strong>{stats.student}</strong>
                <small>All students</small>
              </div>
            </article>
            <article>
              <Building2 />
              <div>
                <strong>{stats.college_students}</strong>
                <small>College students</small>
              </div>
            </article>
            <article>
              <UserRoundPlus />
              <div>
                <strong>{stats.individual_students}</strong>
                <small>Individual students</small>
              </div>
            </article>
            <article>
              <FolderKanban />
              <div>
                <strong>{stats.projects}</strong>
                <small>Projects</small>
              </div>
            </article>
            <article>
              <Code2 />
              <div>
                <strong>{stats.judge_runs}</strong>
                <small>Judge0 runs</small>
              </div>
            </article>
            <article>
              <Award />
              <div>
                <strong>{stats.certificates}</strong>
                <small>Certificates</small>
              </div>
            </article>
          </div>
          <div className="admin-columns">
            <section className="panel">
              <p className="eyebrow">MOU AND PAYMENTS</p>
              <h2>{stats.mou_seats} approved college seats</h2>
              <div className="summary-list">
                <p>
                  <span>Active Coordinators</span>
                  <strong>
                    {
                      accessList.filter(
                        (item) => item.mou_access?.currently_valid,
                      ).length
                    }
                  </strong>
                </p>
                <p>
                  <span>College seats activated</span>
                  <strong>
                    {accessList.reduce(
                      (sum, item) => sum + (item.mou_access?.used_seats || 0),
                      0,
                    )}
                  </strong>
                </p>
                <p>
                  <span>Individual projects paid</span>
                  <strong>{stats.paid_projects}</strong>
                </p>
              </div>
            </section>
            <section className="panel">
              <p className="eyebrow">QUALITY CONTROLS</p>
              <h2>VS Code-only project flow</h2>
              <div className="quality-list">
                <span>
                  <CheckCircle2 /> No student project upload, Git or manual Task
                  ID
                </span>
                <span>
                  <CheckCircle2 /> Real project modules + local + hidden checks
                </span>
                <span>
                  <CheckCircle2 /> Only a complete PASS unlocks the next task
                </span>
                <span>
                  <CheckCircle2 /> All tasks automatically enable certificate +
                  local ZIP
                </span>
              </div>
            </section>
          </div>
        </>
      )}

      {tab === "Students" && (
        <section className="panel table-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">STUDENT MANAGEMENT</p>
              <h2>College and individual students</h2>
              <p>
                Mentors use aggregate analytics; they are not assigned to review
                individual work.
              </p>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Type</th>
                  <th>College</th>
                  <th>Technology</th>
                  <th>Coordinator</th>
                </tr>
              </thead>
              <tbody>
                {students.map((student) => (
                  <tr key={student.id}>
                    <td>
                      <strong>{student.name}</strong>
                      <small>{student.email}</small>
                    </td>
                    <td>{student.enrollment_type || "-"}</td>
                    <td>{student.college_name || "Not applicable"}</td>
                    <td>{student.preferred_language || "Not selected"}</td>
                    <td>
                      {student.enrollment_type === "COLLEGE" ? (
                        <select
                          value={student.coordinator_id || ""}
                          onChange={(event) =>
                            assignCoordinator(student.id, event.target.value)
                          }
                        >
                          <option value="" disabled>
                            Assign Coordinator
                          </option>
                          {coordinators.map((item) => (
                            <option value={item.id} key={item.id}>
                              {item.name} – {item.college_name}
                            </option>
                          ))}
                        </select>
                      ) : (
                        "Not applicable"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {tab === "Projects" && (
        <>
          <div className="admin-columns">
            <section className="panel generator-panel">
              <p className="eyebrow">YOUR PROJECT PROMPT</p>
              <h2>
                <Bot size={21} /> Generate from your brief
              </h2>
              <form
                className="mini-form"
                onSubmit={(event) =>
                  submitForm(
                    event,
                    "/admin/projects/generate-from-prompt",
                    "Project draft and sequential tasks generated.",
                  )
                }
              >
                <textarea
                  name="prompt"
                  required
                  minLength="20"
                  placeholder="Build an attendance portal with reports and role dashboards."
                />
                <div className="two-fields">
                  <select name="technology">
                    {technologies.map((item) => (
                      <option key={item}>{item}</option>
                    ))}
                  </select>
                  <select name="internship_type">
                    <option value="FASTTRACK">FastTrack</option>
                    <option value="45_DAYS">45 Days</option>
                    <option value="SEMESTER">Semester</option>
                  </select>
                </div>
                <div className="two-fields">
                  <input name="domain" defaultValue="General" />
                  <select name="difficulty" defaultValue="Intermediate">
                    <option>Beginner</option>
                    <option>Intermediate</option>
                    <option>Advanced</option>
                  </select>
                </div>
                <button className="primary-button">
                  <Bot size={17} /> Generate draft
                </button>
              </form>
            </section>
            <section className="panel generator-panel">
              <p className="eyebrow">TECHNOLOGY GENERATOR</p>
              <h2>Generate catalogue projects</h2>
              <form
                className="mini-form"
                onSubmit={(event) =>
                  submitForm(
                    event,
                    "/admin/projects/generate",
                    "Catalogue drafts generated.",
                    (values) => ({ ...values, count: Number(values.count) }),
                  )
                }
              >
                <div className="two-fields">
                  <select name="technology">
                    {technologies.map((item) => (
                      <option key={item}>{item}</option>
                    ))}
                  </select>
                  <select name="internship_type">
                    <option value="FASTTRACK">FastTrack</option>
                    <option value="45_DAYS">45 Days</option>
                    <option value="SEMESTER">Semester</option>
                  </select>
                </div>
                <input
                  name="domain"
                  required
                  placeholder="Education, healthcare, retail…"
                />
                <div className="two-fields">
                  <select name="difficulty" defaultValue="Intermediate">
                    <option>Beginner</option>
                    <option>Intermediate</option>
                    <option>Advanced</option>
                  </select>
                  <input
                    name="count"
                    type="number"
                    min="1"
                    max="5"
                    defaultValue="3"
                  />
                </div>
                <button className="primary-button">
                  <Bot size={17} /> Generate projects
                </button>
              </form>
            </section>
          </div>
          <section className="panel complete-project-panel">
            <p className="eyebrow">COMPLETE PREDEFINED PROJECT</p>
            <h2>Upload, analyse and prepare a runnable project</h2>
            <p>
              Upload source only. Dependency folders such as node_modules,
              .venv, build, target and .git are ignored. GAINT adds local
              database/setup files, project-related milestones and hidden tests.
            </p>
            <form
              className="form-grid compact-grid"
              onSubmit={uploadCompleteProject}
            >
              <label>
                Title
                <input name="title" required />
              </label>
              <label>
                Technology
                <select name="technology" defaultValue="AUTO">
                  <option value="AUTO">Auto detect</option>
                  {technologies.map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </select>
              </label>
              <label>
                Internship
                <select name="internship_type">
                  <option value="FASTTRACK">FastTrack</option>
                  <option value="45_DAYS">45 Days</option>
                  <option value="SEMESTER">Semester</option>
                </select>
              </label>
              <label>
                Domain
                <input name="domain" defaultValue="General" />
              </label>
              <label>
                Difficulty
                <select name="difficulty" defaultValue="Intermediate">
                  <option>Beginner</option>
                  <option>Intermediate</option>
                  <option>Advanced</option>
                </select>
              </label>
              <label>
                Individual fee (₹)
                <input
                  name="individual_fee_rupees"
                  type="number"
                  min="1"
                  defaultValue="999"
                  required
                />
              </label>
              <label className="full">
                Description
                <textarea
                  name="description"
                  required
                  minLength="10"
                  placeholder="Explain the project, main modules and expected local presentation."
                />
              </label>
              <label className="full">
                Complete runnable source ZIP
                <input
                  name="project_zip"
                  type="file"
                  accept=".zip,application/zip"
                  required
                />
              </label>
              <button className="primary-button full">
                <FolderKanban size={17} /> Analyse and create project tasks
              </button>
            </form>
          </section>

          <section className="panel custom-project-panel">
            <p className="eyebrow">PREDEFINED PROJECT WITHOUT MASTER ZIP</p>
            <h2>Create a starter project from details</h2>
            <form
              className="form-grid compact-grid"
              onSubmit={(event) =>
                submitForm(
                  event,
                  "/admin/projects",
                  "Project and project-related tasks created.",
                  (values) => ({
                    ...values,
                    individual_fee_rupees: Number(values.individual_fee_rupees),
                    features: values.features
                      .split(",")
                      .map((item) => item.trim())
                      .filter(Boolean),
                    available_tracks: values.available_tracks
                      .split(",")
                      .map((item) => item.trim().toUpperCase()),
                    auto_generate_tasks: true,
                  }),
                )
              }
            >
              <label>
                Title
                <input name="title" required />
              </label>
              <label>
                Technology
                <select name="technology">
                  {technologies.map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </select>
              </label>
              <label>
                Internship
                <select name="internship_type">
                  <option value="FASTTRACK">FastTrack</option>
                  <option value="45_DAYS">45 Days</option>
                  <option value="SEMESTER">Semester</option>
                </select>
              </label>
              <label>
                Domain
                <input name="domain" defaultValue="General" />
              </label>
              <label>
                Difficulty
                <select name="difficulty" defaultValue="Intermediate">
                  <option>Beginner</option>
                  <option>Intermediate</option>
                  <option>Advanced</option>
                </select>
              </label>
              <label>
                Individual fee (₹)
                <input
                  name="individual_fee_rupees"
                  type="number"
                  min="1"
                  defaultValue="999"
                  required
                />
              </label>
              <label>
                Features
                <input
                  name="features"
                  required
                  placeholder="Login, dashboard, reports"
                />
              </label>
              <label>
                Tracks
                <input
                  name="available_tracks"
                  required
                  defaultValue="FULL_STACK"
                  placeholder="FRONTEND,BACKEND,FULL_STACK"
                />
              </label>
              <label className="full">
                Description
                <textarea name="description" required minLength="10" />
              </label>
              <button className="primary-button full">
                <Plus size={17} /> Create project and tasks
              </button>
            </form>
          </section>
          <section className="panel project-library-panel">
            <div className="section-heading compact">
              <div>
                <p className="eyebrow">PROJECT LIBRARY</p>
                <h2>Predefined and generated projects</h2>
              </div>
              <strong>{projects.length}</strong>
            </div>
            <div className="project-admin-grid">
              {projects.map((project) => (
                <article key={project.id}>
                  <div>
                    <span className="language-pill">{project.technology}</span>
                    <span
                      className={`draft-pill ${project.status.toLowerCase()}`}
                    >
                      {project.status}
                    </span>
                  </div>
                  <h3>{project.title}</h3>
                  <p>
                    {project.internship_type.replaceAll("_", " ")} ·{" "}
                    {project.task_count} task(s)
                  </p>
                  {project.status === "DRAFT" && (
                    <button
                      className="approve-button"
                      onClick={() => publish(project.id)}
                    >
                      <Send size={15} /> Publish
                    </button>
                  )}
                </article>
              ))}
            </div>
          </section>
        </>
      )}

      {tab === "College Teams" && (
        <>
          <section className="panel">
            <p className="eyebrow">COLLEGE-ONLY TEAM PROJECT</p>
            <h2>Split one full-stack project safely</h2>
            <p>
              Admin assigns one student to Frontend and one to Backend. Each
              student receives only that track’s tasks. Individual internships
              remain single-student projects.
            </p>
            <form className="form-grid compact-grid" onSubmit={createTeam}>
              <label>
                Team name
                <input
                  name="name"
                  required
                  placeholder="Campus Builders Team"
                />
              </label>
              <label>
                College Coordinator
                <select name="coordinator_id" required defaultValue="">
                  <option value="" disabled>
                    Select Coordinator
                  </option>
                  {coordinators.map((item) => (
                    <option value={item.id} key={item.id}>
                      {item.college_name} — {item.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Full-stack project
                <select name="project_id" required defaultValue="">
                  <option value="" disabled>
                    Select project
                  </option>
                  {publishedProjects
                    .filter(
                      (item) =>
                        item.available_tracks?.includes("FRONTEND") &&
                        item.available_tracks?.includes("BACKEND"),
                    )
                    .map((item) => (
                      <option value={item.id} key={item.id}>
                        {item.title} (
                        {item.internship_type.replaceAll("_", " ")})
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Frontend student
                <select name="frontend_student_id" required defaultValue="">
                  <option value="" disabled>
                    Select student
                  </option>
                  {students
                    .filter(
                      (item) =>
                        item.enrollment_type === "COLLEGE" && !item.project_id,
                    )
                    .map((item) => (
                      <option value={item.id} key={item.id}>
                        {item.name} — {item.college_name}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Backend student
                <select name="backend_student_id" required defaultValue="">
                  <option value="" disabled>
                    Select student
                  </option>
                  {students
                    .filter(
                      (item) =>
                        item.enrollment_type === "COLLEGE" && !item.project_id,
                    )
                    .map((item) => (
                      <option value={item.id} key={item.id}>
                        {item.name} — {item.college_name}
                      </option>
                    ))}
                </select>
              </label>
              <button className="primary-button">
                <Users size={17} /> Create project team
              </button>
            </form>
          </section>
          <section className="panel table-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">TEAM PROGRESS</p>
                <h2>{teams.length} college team(s)</h2>
              </div>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Team</th>
                    <th>College</th>
                    <th>Project</th>
                    <th>Members and tracks</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {teams.map((team) => (
                    <tr key={team.id}>
                      <td>
                        <strong>{team.name}</strong>
                      </td>
                      <td>{team.college_name}</td>
                      <td>{team.project.title}</td>
                      <td>
                        {team.members
                          .map(
                            (member) =>
                              `${member.student.name}: ${member.track} (${member.progress}%)`,
                          )
                          .join(" · ")}
                      </td>
                      <td>{team.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      {tab === "MOU Access" && (
        <>
          <div className="admin-columns">
            <section className="panel">
              <p className="eyebrow">CREATE MENTOR</p>
              <h2>Add Mentor account</h2>
              <form
                className="mini-form"
                onSubmit={(event) =>
                  submitForm(event, "/admin/mentors", "Mentor created.")
                }
              >
                <input name="name" required placeholder="Mentor name" />
                <input name="email" type="email" required placeholder="Email" />
                <input
                  name="password"
                  type="password"
                  minLength="8"
                  required
                  placeholder="Temporary password"
                />
                <button className="primary-button">
                  <Plus size={17} /> Create Mentor
                </button>
              </form>
            </section>
            <section className="panel">
              <p className="eyebrow">CREATE COLLEGE COORDINATOR</p>
              <h2>Add account, MOU and student logins</h2>
              <form className="mini-form" onSubmit={createCoordinator}>
                <input name="name" required placeholder="Coordinator name" />
                <input
                  name="college_name"
                  required
                  placeholder="Exact college name"
                />
                <input name="email" type="email" required placeholder="Email" />
                <input
                  name="password"
                  type="password"
                  minLength="8"
                  required
                  placeholder="Temporary password"
                />
                <input name="mou_number" required placeholder="MOU number" />
                <label>
                  Student limit / credentials (1–500)
                  <input
                    name="student_limit"
                    type="number"
                    min="1"
                    max="500"
                    defaultValue="10"
                    required
                  />
                </label>
                <div className="two-fields">
                  <label>
                    Starts
                    <input
                      name="starts_on"
                      type="date"
                      defaultValue={startDate}
                      required
                    />
                  </label>
                  <label>
                    Expires
                    <input
                      name="ends_on"
                      type="date"
                      defaultValue={endDate}
                      required
                    />
                  </label>
                </div>
                <label>
                  Allowed projects
                  <select
                    className="multi-select"
                    name="allowed_project_ids"
                    multiple
                    size="7"
                    required
                  >
                    {publishedProjects.map((project) => (
                      <option value={project.id} key={project.id}>
                        {project.technology} — {project.title} (
                        {project.internship_type.replaceAll("_", " ")})
                      </option>
                    ))}
                  </select>
                  <small>Use Ctrl-click to select multiple projects.</small>
                </label>
                <button className="primary-button">
                  <Building2 size={17} /> Create Coordinator, MOU and logins
                </button>
              </form>
            </section>
          </div>
          {credentialSheet.length > 0 && (
            <section className="panel">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">
                    NEW STUDENT CREDENTIALS — SHOWN ONCE
                  </p>
                  <h2>{credentialSheet.length} college login(s) created</h2>
                  <p>
                    Download and distribute privately. Every student must change
                    the temporary password after first login.
                  </p>
                </div>
                <button
                  className="primary-button"
                  onClick={downloadCredentials}
                >
                  Download credentials CSV
                </button>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Login email</th>
                      <th>Temporary password</th>
                    </tr>
                  </thead>
                  <tbody>
                    {credentialSheet.slice(0, 10).map((item) => (
                      <tr key={item.student_id}>
                        <td>{item.name}</td>
                        <td>{item.email}</td>
                        <td>{item.temporary_password}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {credentialSheet.length > 10 && (
                <p>
                  Download the CSV to see all {credentialSheet.length}{" "}
                  credentials.
                </p>
              )}
            </section>
          )}
          <section className="panel mou-access-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">ADMIN-ONLY COLLEGE ACCESS</p>
                <h2>MOU validity, seats and projects</h2>
              </div>
              <ShieldCheck />
            </div>
            <div className="mou-grid">
              {accessList.map(
                ({
                  coordinator,
                  mou_access: mou,
                  allowed_projects: allowed,
                }) => (
                  <article className="mou-card" key={coordinator.id}>
                    <header>
                      <div>
                        <h3>{coordinator.college_name}</h3>
                        <p>
                          {coordinator.name} · {coordinator.email}
                        </p>
                      </div>
                      <span
                        className={`status-badge ${mou?.currently_valid ? "approved" : "not_started"}`}
                      >
                        {mou?.currently_valid ? "ACTIVE" : "INACTIVE"}
                      </span>
                    </header>
                    {mou ? (
                      <>
                        <div className="seat-meter">
                          <span>
                            <strong>{mou.used_seats}</strong> used
                          </span>
                          <span>
                            <strong>{mou.available_seats}</strong> available
                          </span>
                          <span>
                            <strong>{mou.student_limit}</strong> limit
                          </span>
                        </div>
                        <p className="mou-projects">
                          <strong>Allowed:</strong>{" "}
                          {allowed
                            .map((item) => `${item.technology} – ${item.title}`)
                            .join(", ") || "None"}
                        </p>
                        <form
                          className="mini-form mou-edit-form"
                          onSubmit={(event) => updateMou(event, coordinator.id)}
                        >
                          <div className="two-fields">
                            <label>
                              MOU/access code
                              <input
                                name="mou_number"
                                defaultValue={mou.mou_number}
                                required
                              />
                            </label>
                            <label>
                              Student limit
                              <input
                                name="student_limit"
                                type="number"
                                min="1"
                                max="500"
                                defaultValue={mou.student_limit}
                                required
                              />
                            </label>
                          </div>
                          <div className="two-fields">
                            <label>
                              Starts
                              <input
                                name="starts_on"
                                type="date"
                                defaultValue={mou.starts_on}
                                required
                              />
                            </label>
                            <label>
                              Expires
                              <input
                                name="ends_on"
                                type="date"
                                defaultValue={mou.ends_on}
                                required
                              />
                            </label>
                          </div>
                          <label>
                            Access
                            <select
                              name="active"
                              defaultValue={String(mou.active)}
                            >
                              <option value="true">Active</option>
                              <option value="false">Deactivated</option>
                            </select>
                          </label>
                          <label>
                            Allowed projects
                            <select
                              className="multi-select"
                              name="allowed_project_ids"
                              multiple
                              size="6"
                              defaultValue={mou.allowed_project_ids.map(String)}
                              required
                            >
                              {publishedProjects.map((project) => (
                                <option value={project.id} key={project.id}>
                                  {project.technology} — {project.title} (
                                  {project.internship_type.replaceAll("_", " ")}
                                  )
                                </option>
                              ))}
                            </select>
                          </label>
                          <button className="secondary-button">
                            Update MOU access
                          </button>
                        </form>
                      </>
                    ) : (
                      <p>MOU access is not configured.</p>
                    )}
                  </article>
                ),
              )}
            </div>
          </section>
        </>
      )}

      {tab === "Reports" && (
        <>
          <section className="panel table-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">INTERNSHIP REPORTS</p>
                <h2>College and individual project progress</h2>
              </div>
              <BarChart3 />
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Student</th>
                    <th>Type</th>
                    <th>Project</th>
                    <th>Technology</th>
                    <th>Progress</th>
                    <th>Attendance</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {reports.map((report) => (
                    <tr key={report.student_id}>
                      <td>
                        <strong>{report.name}</strong>
                        <small>{report.college || "Individual"}</small>
                      </td>
                      <td>{report.enrollment_type}</td>
                      <td>{report.project || "Not assigned"}</td>
                      <td>{report.technology || "-"}</td>
                      <td>{report.progress}%</td>
                      <td>
                        {report.attendance === null ? (
                          "Not used"
                        ) : (
                          <span className="attendance-cell">
                            <Activity size={14} /> {report.attendance}%
                          </span>
                        )}
                      </td>
                      <td>
                        <span
                          className={`status-badge ${report.status === "COMPLETED" ? "approved" : "not_started"}`}
                        >
                          {report.status.replaceAll("_", " ")}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="panel">
            <p className="eyebrow">INDIVIDUAL PAYMENTS</p>
            <h2>{payments.length} payment record(s)</h2>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Student</th>
                    <th>Project</th>
                    <th>Amount</th>
                    <th>Status</th>
                    <th>Receipt</th>
                  </tr>
                </thead>
                <tbody>
                  {payments.map((payment) => (
                    <tr key={payment.id}>
                      <td>{payment.student.name}</td>
                      <td>{payment.project.title}</td>
                      <td>₹{payment.amount_rupees}</td>
                      <td>{payment.status}</td>
                      <td>{payment.receipt_number || "Pending"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </Layout>
  );
}
