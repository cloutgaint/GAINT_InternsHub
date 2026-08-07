import {
  BookOpenCheck,
  Building2,
  CalendarCheck2,
  Clock3,
  Download,
  ShieldCheck,
  Users,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, downloadFile } from "../api";
import Layout from "../components/Layout";
import Notice from "../components/Notice";

const localDate = () =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());

export default function CoordinatorDashboard() {
  const [data, setData] = useState(null);
  const [teams, setTeams] = useState([]);
  const [notice, setNotice] = useState({});
  const load = useCallback(
    () =>
      Promise.all([api("/coordinator/dashboard"), api("/coordinator/teams")])
        .then(([dashboard, teamRows]) => {
          setData(dashboard);
          setTeams(teamRows);
        })
        .catch((error) => setNotice({ type: "error", message: error.message })),
    [],
  );
  useEffect(() => {
    load();
  }, [load]);

  const markAttendance = async (event, studentId) => {
    event.preventDefault();
    try {
      await api(`/coordinator/students/${studentId}/attendance`, {
        method: "PUT",
        body: JSON.stringify(
          Object.fromEntries(new FormData(event.currentTarget)),
        ),
      });
      setNotice({ type: "success", message: "Student attendance updated." });
      await load();
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    }
  };

  if (!data)
    return (
      <div className="app-loader">
        <span className="spinner" />
        Loading College Coordinator dashboard…
      </div>
    );
  return (
    <Layout
      title="College Coordinator"
      subtitle={`Monitor attendance and internship work for ${data.coordinator.college_name || "your college"}.`}
    >
      <Notice {...notice} onClose={() => setNotice({})} />
      <div className="metric-grid">
        <article>
          <Users />
          <div>
            <strong>{data.summary.students}</strong>
            <small>Assigned students</small>
          </div>
        </article>
        <article>
          <CalendarCheck2 />
          <div>
            <strong>{data.summary.present_today}</strong>
            <small>Present today</small>
          </div>
        </article>
        <article>
          <Clock3 />
          <div>
            <strong>{data.summary.absent_or_pending}</strong>
            <small>Absent or pending</small>
          </div>
        </article>
      </div>
      {data.mou_access && (
        <section className="panel coordinator-mou compact-mou">
          <div>
            <p className="eyebrow">ADMIN-APPROVED MOU ACCESS</p>
            <h2>{data.mou_access.mou_number}</h2>
            <p>
              {data.mou_access.starts_on} to {data.mou_access.ends_on} ·{" "}
              {data.mou_access.currently_valid ? "Active" : "Inactive"}
            </p>
          </div>
          <div className="seat-meter">
            <span>
              <strong>{data.mou_access.used_seats}</strong> used
            </span>
            <span>
              <strong>{data.mou_access.available_seats}</strong> available
            </span>
            <span>
              <strong>{data.mou_access.student_limit}</strong> limit
            </span>
          </div>
          <div className="approved-project-summary">
            <strong>{data.allowed_projects.length} approved project(s)</strong>
            <p>
              {data.allowed_projects
                .slice(0, 4)
                .map((project) => `${project.technology} – ${project.title}`)
                .join(" · ") || "No project access"}
            </p>
            {data.allowed_projects.length > 4 && (
              <small>
                + {data.allowed_projects.length - 4} more projects approved by
                Admin
              </small>
            )}
          </div>
          <button
            className="secondary-button"
            onClick={() =>
              downloadFile(
                "/coordinator/progress-report",
                "GAINT-College-Progress.csv",
              )
            }
          >
            <Download size={16} /> Progress CSV
          </button>
          <ShieldCheck />
        </section>
      )}
      {teams.length > 0 && (
        <section className="panel table-panel">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">COLLEGE TEAM PROJECTS</p>
              <h2>Frontend and Backend track progress</h2>
            </div>
            <Users />
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Team</th>
                  <th>Project</th>
                  <th>Track ownership</th>
                  <th>Status</th>
                  <th>Package</th>
                </tr>
              </thead>
              <tbody>
                {teams.map((team) => (
                  <tr key={team.id}>
                    <td>
                      <strong>{team.name}</strong>
                    </td>
                    <td>{team.project.title}</td>
                    <td>
                      {team.members
                        .map(
                          (member) =>
                            `${member.student.name}: ${member.track} ${member.progress}%`,
                        )
                        .join(" · ")}
                    </td>
                    <td>{team.status}</td>
                    <td>
                      <button
                        className="secondary-button"
                        disabled={
                          !team.members.every((member) => member.completed)
                        }
                        onClick={() =>
                          downloadFile(
                            `/teams/${team.id}/completed-project`,
                            `${team.name}-Completed.zip`,
                          )
                        }
                      >
                        <Download size={15} /> Combined ZIP
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <section className="panel coordinator-panel">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">COLLEGE MONITORING</p>
            <h2>Students, attendance and project progress</h2>
          </div>
          <Building2 />
        </div>
        {data.students.length === 0 ? (
          <div className="empty-state">
            <Users />
            <h3>No students assigned</h3>
            <p>GAINT Admin must assign students to this Coordinator account.</p>
          </div>
        ) : (
          <div className="coordinator-grid">
            {data.students.map((row) => (
              <article className="coordinator-student" key={row.student.id}>
                <header>
                  <div className="avatar">{row.student.name.charAt(0)}</div>
                  <div>
                    <h3>{row.student.name}</h3>
                    <p>
                      {row.student.email}
                      <br />
                      {row.student.pursuing_year}
                    </p>
                  </div>
                  <span className="attendance-score">
                    {row.attendance.percentage}% attendance
                  </span>
                </header>
                <div className="coordinator-progress">
                  <span>
                    <BookOpenCheck size={17} />{" "}
                    {row.assignment?.variant_title || "Project not selected"}
                  </span>
                  <strong>{row.progress}%</strong>
                </div>
                <div className="progress-track">
                  <span style={{ width: `${row.progress}%` }} />
                </div>
                <div className="today-attendance">
                  <strong>Today</strong>
                  <span
                    className={`status-badge ${(row.attendance.today?.status || "not_started").toLowerCase()}`}
                  >
                    {row.attendance.today?.status?.replaceAll("_", " ") ||
                      "NOT MARKED"}
                  </span>
                  <small>
                    {row.attendance.today?.work_minutes
                      ? `${row.attendance.today.work_minutes} working minutes`
                      : "No completed work session"}
                  </small>
                </div>
                <form
                  className="attendance-form"
                  onSubmit={(event) => markAttendance(event, row.student.id)}
                >
                  <input
                    name="attendance_date"
                    type="date"
                    max={localDate()}
                    defaultValue={localDate()}
                    required
                  />
                  <select name="status" defaultValue="PRESENT">
                    <option>PRESENT</option>
                    <option>HALF_DAY</option>
                    <option>ABSENT</option>
                    <option>LEAVE</option>
                  </select>
                  <input
                    name="notes"
                    placeholder="Coordinator note (optional)"
                  />
                  <button className="secondary-button">
                    Update attendance
                  </button>
                </form>
              </article>
            ))}
          </div>
        )}
      </section>
    </Layout>
  );
}
