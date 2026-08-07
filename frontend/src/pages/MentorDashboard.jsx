import {
  Building2,
  CheckCircle2,
  Code2,
  FileCheck2,
  Timer,
  Users,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import Layout from "../components/Layout";
import Notice from "../components/Notice";

const labels = {
  FASTTRACK: "FastTrack",
  "45_DAYS": "45 Days",
  SEMESTER: "Semester",
};

export default function MentorDashboard() {
  const [data, setData] = useState(null);
  const [notice, setNotice] = useState({});
  const load = useCallback(
    () =>
      api("/mentor/dashboard")
        .then(setData)
        .catch((error) => setNotice({ type: "error", message: error.message })),
    [],
  );
  useEffect(() => {
    load();
  }, [load]);

  if (!data)
    return (
      <div className="app-loader">
        <span className="spinner" />
        Loading Mentor analytics…
      </div>
    );
  return (
    <Layout
      title="Mentor Analytics"
      subtitle="Company-wide visibility across college and individual internships. No review, viva, pass or unlock actions."
    >
      <Notice {...notice} onClose={() => setNotice({})} />
      <div className="metric-grid">
        <article>
          <Building2 />
          <div>
            <strong>{data.summary.colleges}</strong>
            <small>Colleges with students</small>
          </div>
        </article>
        <article>
          <FileCheck2 />
          <div>
            <strong>{data.summary.active_mous}</strong>
            <small>Active MOUs</small>
          </div>
        </article>
        <article>
          <Users />
          <div>
            <strong>{data.summary.students}</strong>
            <small>Active students</small>
          </div>
        </article>
        <article>
          <CheckCircle2 />
          <div>
            <strong>{data.summary.completed}</strong>
            <small>Completed projects</small>
          </div>
        </article>
      </div>

      <div className="admin-columns">
        <section className="panel">
          <p className="eyebrow">TECHNOLOGY USE</p>
          <h2>Selected stacks</h2>
          <div className="summary-list">
            {Object.entries(data.summary.technologies).map(([name, count]) => (
              <p key={name}>
                <span>
                  <Code2 size={15} /> {name}
                </span>
                <strong>{count}</strong>
              </p>
            ))}
            {!Object.keys(data.summary.technologies).length && (
              <p>No projects selected yet.</p>
            )}
          </div>
        </section>
        <section className="panel">
          <p className="eyebrow">INTERNSHIP PERIODS</p>
          <h2>Program distribution</h2>
          <div className="summary-list">
            {Object.entries(data.summary.periods).map(([name, count]) => (
              <p key={name}>
                <span>
                  <Timer size={15} /> {labels[name] || name}
                </span>
                <strong>{count}</strong>
              </p>
            ))}
            {!Object.keys(data.summary.periods).length && (
              <p>No active programs yet.</p>
            )}
          </div>
        </section>
      </div>

      <section className="panel mentor-scope-card">
        <div>
          <p className="eyebrow">PROGRAM ACTIVITY</p>
          <h2>Aggregate internship progress</h2>
          <p>
            Mentors see company-wide counts only. Student review, viva, pass,
            certificate and task-unlock controls are not available.
          </p>
        </div>
        <div className="summary-list">
          <p>
            <span>College students</span>
            <strong>{data.summary.college_students}</strong>
          </p>
          <p>
            <span>Individual students</span>
            <strong>{data.summary.individual_students}</strong>
          </p>
          <p>
            <span>Started projects</span>
            <strong>{data.summary.started_projects}</strong>
          </p>
          <p>
            <span>In progress</span>
            <strong>{data.summary.in_progress}</strong>
          </p>
        </div>
      </section>
    </Layout>
  );
}
