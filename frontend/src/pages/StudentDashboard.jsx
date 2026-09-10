import {
  Activity,
  Award,
  BookOpen,
  Check,
  ChevronDown,
  Clock3,
  Code2,
  Download,
  FileText,
  FolderOpen,
  LockKeyhole,
  Target,
  Users,
  Verified,
  WalletCards,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, downloadCertificate, downloadFile } from "../api";
import { useAuth } from "../auth";
import Layout from "../components/Layout";
import Notice from "../components/Notice";
import SupportBot from "../components/SupportBot";

const typeLabel = {
  FASTTRACK: "FastTrack",
  "45_DAYS": "45 Days",
  SEMESTER: "Semester",
};
const selectableProjectTracks = (project) => project.available_tracks || [];
const studentStartSteps = [
  [
    "Install VS Code once",
    "If VS Code is not installed, download it from code.visualstudio.com/download and complete the normal installation.",
  ],
  [
    "Download and extract the project",
    "Click Download project, open Downloads, right-click the ZIP and select Extract All. Do not work inside the ZIP.",
  ],
  [
    "Open the correct folder",
    "Inside the extracted folder, double-click OPEN_IN_VSCODE.bat. It installs the included GAINT extension automatically and opens the project.",
  ],
  [
    "Read before coding",
    "Open CURRENT_TASK.md, read the red Current Task Question in this dashboard, and edit the required file inside gaint_checkpoints.",
  ],
  [
    "Run and submit",
    "Test your code in the VS Code terminal. Press Ctrl+Shift+P, select GAINT: Submit Current Task, and wait for all 3 checks.",
  ],
  [
    "Continue or correct",
    "If it passes, the next task unlocks automatically. If it fails, correct the same task and submit it again.",
  ],
];

let razorpayScriptPromise;
function loadRazorpayCheckout() {
  if (window.Razorpay) return Promise.resolve();
  if (!razorpayScriptPromise) {
    razorpayScriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://checkout.razorpay.com/v1/checkout.js";
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () =>
        reject(
          new Error(
            "Razorpay Checkout could not load. Check your internet connection.",
          ),
        );
      document.head.appendChild(script);
    });
  }
  return razorpayScriptPromise;
}

export default function StudentDashboard() {
  const { user, refreshUser } = useAuth();
  const [dashboard, setDashboard] = useState(null);
  const [projects, setProjects] = useState([]);
  const [openTask, setOpenTask] = useState(null);
  const [notice, setNotice] = useState({});
  const [busy, setBusy] = useState(false);
  const [acceptedPaymentPolicy, setAcceptedPaymentPolicy] = useState(false);
  const [aiHelpByTask, setAiHelpByTask] = useState({});
  const [aiHelpLoading, setAiHelpLoading] = useState(null);
  const [aiHelpErrors, setAiHelpErrors] = useState({});

  const load = useCallback(async () => {
    try {
      const data = await api("/student/dashboard");
      setDashboard(data);
      const collegeReady =
        data.user.enrollment_type !== "COLLEGE" || data.college_access?.allowed;
      if (
        data.user.preferred_language &&
        data.user.internship_type &&
        !data.assignment &&
        collegeReady
      ) {
        setProjects(await api("/student/projects"));
      } else setProjects([]);
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const changePassword = async (event) => {
    event.preventDefault();
    setBusy(true);
    setNotice({});
    const values = Object.fromEntries(new FormData(event.currentTarget));
    if (values.new_password !== values.confirm_password) {
      setNotice({
        type: "error",
        message: "New password and confirmation must match.",
      });
      setBusy(false);
      return;
    }
    delete values.confirm_password;
    try {
      await api("/auth/change-password", {
        method: "POST",
        body: JSON.stringify(values),
      });
      await refreshUser();
      await load();
      setNotice({
        type: "success",
        message: "Password changed. Continue with your internship setup.",
      });
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    } finally {
      setBusy(false);
    }
  };

  const savePreferences = async (event) => {
    event.preventDefault();
    setBusy(true);
    setNotice({});
    try {
      const values = Object.fromEntries(new FormData(event.currentTarget));
      values.area_interest = values.area_interest.trim();
      if (values.area_interest.length < 2) {
        throw new Error("Area of interest must contain at least 2 characters.");
      }
      await api("/student/preferences", {
        method: "PUT",
        body: JSON.stringify(values),
      });
      await refreshUser();
      await load();
      setNotice({
        type: "success",
        message: dashboard.assignment
          ? "Technology updated. Your unpaid project selection was cleared; select a matching project."
          : "Internship and technology saved. Select your project.",
      });
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    } finally {
      setBusy(false);
    }
  };

  const chooseProject = async (project) => {
    setBusy(true);
    try {
      const availableTracks = selectableProjectTracks(project);
      const selectedTrack = availableTracks[0];
      if (!selectedTrack) {
        throw new Error("This project has no selectable track. Ask Admin to add a track.");
      }
      const result = await api(`/student/projects/${project.id}/select`, {
        method: "POST",
        body: JSON.stringify({ selected_track: selectedTrack }),
      });
      await load();
      setNotice({ type: "success", message: result.message });
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    } finally {
      setBusy(false);
    }
  };

  const confirmDemoPayment = async (paymentId) => {
    setBusy(true);
    try {
      const payment = await api(`/student/payments/${paymentId}/demo-confirm`, {
        method: "POST",
        body: JSON.stringify({ terms_accepted: acceptedPaymentPolicy }),
      });
      await load();
      setNotice({
        type: "success",
        message: `Demo payment verified. Receipt ${payment.receipt_number}. Project access is active.`,
      });
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    } finally {
      setBusy(false);
    }
  };

  const payWithRazorpay = async (payment) => {
    if (!acceptedPaymentPolicy) {
      setNotice({
        type: "error",
        message:
          "Accept the payment and certification policy before continuing.",
      });
      return;
    }
    setBusy(true);
    setNotice({});
    try {
      const order = await api(
        `/student/payments/${payment.id}/razorpay/order`,
        {
          method: "POST",
          body: JSON.stringify({ terms_accepted: true }),
        },
      );
      await loadRazorpayCheckout();
      const checkout = new window.Razorpay({
        key: order.key_id,
        order_id: order.order_id,
        amount: order.amount,
        currency: order.currency,
        name: order.business_name,
        description: order.description,
        prefill: order.prefill,
        theme: { color: "#3d5ce7" },
        modal: {
          ondismiss: () =>
            setNotice({
              type: "info",
              message:
                "Payment window closed. Your project remains safely pending.",
            }),
        },
        handler: async (response) => {
          setBusy(true);
          try {
            const verified = await api(
              `/student/payments/${payment.id}/razorpay/verify`,
              {
                method: "POST",
                body: JSON.stringify(response),
              },
            );
            await load();
            setNotice({
              type: "success",
              message: `Payment verified. Receipt ${verified.receipt_number}. Project access is active.`,
            });
          } catch (error) {
            setNotice({ type: "error", message: error.message });
          } finally {
            setBusy(false);
          }
        },
      });
      checkout.on("payment.failed", (response) => {
        const description =
          response?.error?.description || "The payment was not completed.";
        setNotice({
          type: "error",
          message: `${description} You can safely try again.`,
        });
      });
      checkout.open();
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    } finally {
      setBusy(false);
    }
  };

  const attendanceAction = async (action) => {
    setBusy(true);
    try {
      await api(`/student/attendance/${action}`, { method: "POST" });
      await load();
      setNotice({ type: "success", message: `Attendance ${action} recorded.` });
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    } finally {
      setBusy(false);
    }
  };

  const download = async (path, fallback, message) => {
    try {
      await downloadFile(path, fallback);
      setNotice({ type: "success", message });
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    }
  };

  const acknowledgeGuide = async () => {
    try {
      await api("/student/guide/acknowledge", { method: "POST" });
      await load();
      setNotice({
        type: "success",
        message:
          "Guide acknowledged. Download and open your automatically connected VS Code project.",
      });
    } catch (error) {
      setNotice({ type: "error", message: error.message });
    }
  };

  const requestAiHelp = async (taskId, action) => {
    setAiHelpLoading(`${taskId}:${action}`);
    setAiHelpErrors((current) => ({ ...current, [taskId]: "" }));
    try {
      const result = await api("/student/ai/current-task", {
        method: "POST",
        body: JSON.stringify({ task_id: taskId, action, error_message: "" }),
      });
      setAiHelpByTask((current) => ({ ...current, [taskId]: result.response }));
    } catch (error) {
      setAiHelpErrors((current) => ({ ...current, [taskId]: error.message }));
    } finally {
      setAiHelpLoading(null);
    }
  };

  if (!dashboard)
    return (
      <div className="app-loader">
        <span className="spinner" />
        Preparing your internship workspace…
      </div>
    );

  if (dashboard.user.must_change_password)
    return (
      <Layout
        title="Change your temporary password"
        subtitle="College credentials must be secured before internship setup."
      >
        <Notice {...notice} onClose={() => setNotice({})} />
        <section className="panel setup-panel">
          <div>
            <p className="eyebrow">FIRST LOGIN</p>
            <h2>Create your private password</h2>
            <p>Your temporary password will stop working after this change.</p>
          </div>
          <form className="mini-form" onSubmit={changePassword}>
            <input
              name="current_password"
              type="password"
              minLength="8"
              required
              placeholder="Temporary password"
            />
            <input
              name="new_password"
              type="password"
              minLength="8"
              required
              placeholder="New password"
            />
            <input
              name="confirm_password"
              type="password"
              minLength="8"
              required
              placeholder="Confirm new password"
            />
            <button className="primary-button" disabled={busy}>
              Change password
            </button>
          </form>
        </section>
      </Layout>
    );

  const assignment = dashboard.assignment;
  const isCollege = dashboard.user.enrollment_type === "COLLEGE";
  const setupMissing =
    !dashboard.user.preferred_language || !dashboard.user.internship_type;
  const canEditPreferences =
    !assignment ||
    (!isCollege &&
      !assignment.access_enabled &&
      assignment.payment?.status === "PENDING");
  const currentTask = assignment?.tasks?.find(
    (task) => task.unlocked && task.status !== "PASSED",
  );
  return (
    <Layout
      title={`Welcome, ${user.name.split(" ")[0]}`}
      subtitle={
        isCollege
          ? "College internship: attendance and progress are visible to your College Coordinator."
          : "Individual internship: one project payment, no attendance, and no College Coordinator."
      }
    >
      <Notice {...notice} onClose={() => setNotice({})} />
      <div className={`student-stats ${isCollege ? "four" : "three"}`}>
        <article>
          <span className="stat-icon blue">
            <Target />
          </span>
          <div>
            <small>Internship</small>
            <strong>
              {typeLabel[dashboard.user.internship_type] || "Not selected"}
            </strong>
          </div>
        </article>
        <article>
          <span className="stat-icon violet">
            <BookOpen />
          </span>
          <div>
            <small>Technology</small>
            <strong>
              {dashboard.user.preferred_language || "Not selected"}
            </strong>
          </div>
        </article>
        <article>
          <span className="stat-icon green">
            <Check />
          </span>
          <div>
            <small>Project progress</small>
            <strong>{dashboard.progress}%</strong>
          </div>
        </article>
        {isCollege && (
          <article>
            <span className="stat-icon amber">
              <Activity />
            </span>
            <div>
              <small>Attendance</small>
              <strong>{dashboard.attendance?.percentage || 0}%</strong>
            </div>
          </article>
        )}
      </div>

      {assignment?.team && (
        <section className="panel">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">COLLEGE TEAM PROJECT</p>
              <h2>{assignment.team.name}</h2>
              <p>
                Your owned work:{" "}
                <strong>
                  {assignment.team.member_track.replaceAll("_", " ")}
                </strong>
                . Complete only your track; GAINT combines the validated tracks
                after every member finishes.
              </p>
            </div>
            <Users />
          </div>
          <div className="assignment-meta">
            {assignment.team.members.map((member) => (
              <span key={member.assignment_id}>
                {member.student.name}: {member.track.replaceAll("_", " ")}{" "}
                {member.completed ? "✓" : ""}
              </span>
            ))}
          </div>
          {assignment.team.members.every((member) => member.completed) && (
            <button
              className="secondary-button"
              onClick={() =>
                download(
                  `/teams/${assignment.team.id}/completed-project`,
                  `${assignment.team.name}-Completed.zip`,
                  "Combined team project downloaded.",
                )
              }
            >
              <Download size={16} /> Download combined team project
            </button>
          )}
        </section>
      )}

      {isCollege && (
        <section className="attendance-strip panel">
          <div>
            <p className="eyebrow">COLLEGE ATTENDANCE</p>
            <h2>
              {dashboard.attendance?.today?.status?.replaceAll("_", " ") ||
                "Not checked in today"}
            </h2>
            <p>Check in when you begin working on the local project.</p>
          </div>
          <div className="attendance-actions">
            <button
              className="primary-button"
              disabled={busy || dashboard.attendance?.today?.check_in_at}
              onClick={() => attendanceAction("check-in")}
            >
              <Clock3 size={17} /> Check in
            </button>
            <button
              className="secondary-button"
              disabled={
                busy ||
                !dashboard.attendance?.today?.check_in_at ||
                dashboard.attendance?.today?.check_out_at
              }
              onClick={() => attendanceAction("check-out")}
            >
              <Check size={17} /> Check out
            </button>
          </div>
        </section>
      )}

      {canEditPreferences && (
        <section className="panel setup-panel">
          <div>
            <p className="eyebrow">
              {setupMissing ? "STEP 1" : "YOUR TECH STACK"}
            </p>
            <h2>
              {setupMissing
                ? "Select internship and technology"
                : "Edit internship and technology"}
            </h2>
            <p>
              {assignment
                ? "You can change these before payment. Changing either one clears the unpaid project selection so you can choose a matching project."
                : "This filters the project library and sets the number of sequential milestones."}
            </p>
          </div>
          <form onSubmit={savePreferences} className="inline-form">
            <label>
              Internship
              <select
                name="internship_type"
                required
                defaultValue={dashboard.user.internship_type || ""}
              >
                <option value="" disabled>
                  Select internship
                </option>
                <option value="FASTTRACK">FastTrack</option>
                <option value="45_DAYS">45 Days</option>
                <option value="SEMESTER">Semester</option>
              </select>
            </label>
            <label>
              Technology
              <select
                name="preferred_language"
                required
                defaultValue={dashboard.user.preferred_language || ""}
              >
                <option value="" disabled>
                  Select technology
                </option>
                {["Java", "Python", "Node.js", "Next.js", "Django"].map(
                  (item) => (
                    <option key={item}>{item}</option>
                  ),
                )}
              </select>
            </label>
            <label>
              Area of interest
              <input
                name="area_interest"
                required
                minLength="2"
                maxLength="250"
                defaultValue={dashboard.user.area_interest || ""}
                placeholder="Education, healthcare, AI…"
              />
            </label>
            <button className="primary-button" disabled={busy}>
              {assignment ? "Save changes" : "Save and continue"}
            </button>
          </form>
        </section>
      )}

      {!setupMissing &&
        !assignment &&
        isCollege &&
        !dashboard.college_access?.allowed && (
          <section className="panel access-pending">
            <p className="eyebrow">COLLEGE ACCESS</p>
            <h2>Project selection is waiting for Admin access</h2>
            <p>{dashboard.college_access?.reason}</p>
          </section>
        )}

      {!setupMissing &&
        !assignment &&
        (!isCollege || dashboard.college_access?.allowed) && (
          <section>
            <div className="section-heading">
              <div>
                <p className="eyebrow">STEP 2</p>
                <h2>Select one project and track</h2>
                <p>
                  {isCollege
                    ? "Only projects approved under your college MOU are shown. There is no payment."
                    : "Choose one project. Its one-time internship fee is shown before access."}
                </p>
              </div>
            </div>
            {projects.length === 0 ? (
              <div className="empty-state panel">
                <BookOpen />
                <h3>No matching project</h3>
                <p>Ask Admin to publish a matching project.</p>
              </div>
            ) : (
              <div className="project-grid">
                {projects.map((project) => {
                  const availableTracks = selectableProjectTracks(project);
                  return (
                  <article className="project-card" key={project.id}>
                    <div className="project-pills">
                      <span className="language-pill">
                        {project.technology}
                      </span>
                      <span className="type-pill">
                        {project.task_count} task(s)
                      </span>
                    </div>
                    <h3>{project.title}</h3>
                    <p>{project.description}</p>
                    {!isCollege && <h3>₹{project.individual_fee_rupees}</h3>}
                    <ul className="feature-list">
                      {project.features.slice(0, 4).map((feature) => (
                        <li key={feature}>{feature}</li>
                      ))}
                    </ul>
                    <button
                      className="primary-button"
                      onClick={() => chooseProject(project)}
                      disabled={busy || availableTracks.length === 0}
                    >
                      {availableTracks.length === 0
                        ? "No track available"
                        : "Select project"}
                    </button>
                  </article>
                  );
                })}
              </div>
            )}
          </section>
        )}

      {assignment && !assignment.access_enabled && assignment.payment && (
        <section className="panel payment-panel">
          <div>
            <p className="eyebrow">ONE-TIME PROJECT PAYMENT</p>
            <h2>
              <WalletCards size={22} /> ₹{assignment.payment.amount_rupees}{" "}
              {assignment.payment.currency}
            </h2>
            <p>
              Payment gives project access and reattempts during the
              internship/grace period. It does not guarantee a pass or
              certificate.
            </p>
            <p>
              <strong>Status:</strong> {assignment.payment.status}
            </p>
            <label className="policy-check">
              <input
                type="checkbox"
                checked={acceptedPaymentPolicy}
                onChange={(event) =>
                  setAcceptedPaymentPolicy(event.target.checked)
                }
              />{" "}
              I understand that every task must pass to receive the certificate
              and completed-project ZIP.
            </label>
          </div>
          <button
            className="primary-button"
            disabled={busy || !acceptedPaymentPolicy}
            onClick={() =>
              assignment.payment.provider === "razorpay"
                ? payWithRazorpay(assignment.payment)
                : confirmDemoPayment(assignment.payment.id)
            }
          >
            {assignment.payment.provider === "razorpay"
              ? `Pay ₹${assignment.payment.amount_rupees} securely`
              : "Complete demo payment"}
          </button>
          <small>
            {assignment.payment.provider === "razorpay"
              ? "Secure Razorpay Checkout opens in a payment window. Project access activates only after server verification."
              : "Demo mode is for local testing only. No real money is collected."}
          </small>
        </section>
      )}

      {assignment && assignment.access_enabled && (
        <>
          <section className="assignment-hero panel">
            <div className="assignment-icon">
              <FolderOpen />
            </div>
            <div>
              <p className="eyebrow">YOUR LOCAL PROJECT</p>
              <h2>{assignment.variant_title}</h2>
              <p>{assignment.variant_brief}</p>
              <div className="assignment-meta">
                <span>{assignment.project.technology}</span>
                <span>{assignment.selected_track.replaceAll("_", " ")}</span>
                <span>{assignment.tasks.length} tasks</span>
              </div>
            </div>
            <div className="hero-actions-stack">
              <button
                className="primary-button"
                disabled={!assignment.student_guide_acknowledged}
                title={
                  !assignment.student_guide_acknowledged
                    ? "Read and confirm the guide below first"
                    : "Download your connected project"
                }
                onClick={() =>
                  download(
                    "/student/starter-project",
                    "GAINT-Starter-Project.zip",
                    "Project downloaded. Extract it and double-click OPEN_IN_VSCODE.bat. It installs the GAINT extension and opens the correct folder automatically.",
                  )
                }
              >
                <Download size={18} /> Download project
              </button>
            </div>
          </section>

          <section
            className={`panel student-guide ${assignment.student_guide_acknowledged ? "acknowledged" : ""}`}
          >
            <div className="student-guide-heading">
              <div>
                <p className="eyebrow">READ BEFORE STARTING TASK 1</p>
                <h2>How to install, open VS Code and submit your work</h2>
                <p>
                  Follow these steps in the same order. You do not need a token,
                  Task ID, Git, project upload, Mentor approval or viva.
                </p>
              </div>
              {assignment.student_guide_acknowledged && (
                <span className="guide-read-badge">
                  <Check size={16} /> Guide completed
                </span>
              )}
            </div>
            <div className="student-guide-steps">
              {studentStartSteps.map(([title, description], index) => (
                <article key={title}>
                  <span>{index + 1}</span>
                  <div>
                    <strong>{title}</strong>
                    <p>{description}</p>
                  </div>
                </article>
              ))}
            </div>
            {!assignment.student_guide_acknowledged && (
              <button className="primary-button" onClick={acknowledgeGuide}>
                <Check size={17} /> I have read these steps — enable project
                download
              </button>
            )}
          </section>

          <section className="progress-panel panel">
            <div className="section-heading compact">
              <div>
                <p className="eyebrow">PROJECT PROGRESS</p>
                <h2>Tasks passed through VS Code and Judge0</h2>
              </div>
              <strong>
                {assignment.passed_tasks}/{assignment.tasks.length}
              </strong>
            </div>
            <div className="progress-track">
              <span style={{ width: `${dashboard.progress}%` }} />
            </div>
          </section>

          <section>
            <div className="section-heading">
              <div>
                <p className="eyebrow">SEQUENTIAL PROJECT TASKS</p>
                <h2>The extension finds your current task automatically</h2>
                <p>
                  No Task ID, Git, commit ID, browser code form, or
                  complete-project upload is used.
                </p>
              </div>
            </div>
            <div className="task-list">
              {assignment.tasks.map((task) => (
                <article
                  key={task.id}
                  className={`task-card ${task.status.toLowerCase()} ${!task.unlocked ? "locked" : ""}`}
                >
                  <button
                    className="task-summary"
                    onClick={() =>
                      task.unlocked &&
                      setOpenTask(openTask === task.id ? null : task.id)
                    }
                  >
                    <span className="task-number">
                      {task.status === "PASSED" ? (
                        <Check size={18} />
                      ) : task.unlocked ? (
                        task.order_no
                      ) : (
                        <LockKeyhole size={17} />
                      )}
                    </span>
                    <div>
                      <small>TASK {task.order_no}</small>
                      <strong>{task.title}</strong>
                    </div>
                    <span
                      className={`status-badge ${task.status.toLowerCase()}`}
                    >
                      {task.status.replaceAll("_", " ")}
                    </span>
                    {task.unlocked && (
                      <ChevronDown
                        className={openTask === task.id ? "rotate" : ""}
                      />
                    )}
                  </button>
                  {openTask === task.id && (
                    <div className="task-workspace">
                      <div>
                        <h4>Project instructions</h4>
                        <p>{task.description}</p>
                        <h4>Deliverables</h4>
                        <ul>
                          {task.deliverables.map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                        {task.status !== "PASSED" && (
                          <div className="ai-help-actions">
                            <button
                              type="button"
                              className="secondary-button"
                              disabled={Boolean(aiHelpLoading)}
                              onClick={() => requestAiHelp(task.id, "EXPLAIN")}
                            >
                              {aiHelpLoading === `${task.id}:EXPLAIN`
                                ? "Explaining…"
                                : "Explain task"}
                            </button>
                            <button
                              type="button"
                              className="secondary-button"
                              disabled={Boolean(aiHelpLoading)}
                              onClick={() => requestAiHelp(task.id, "HINT")}
                            >
                              {aiHelpLoading === `${task.id}:HINT`
                                ? "Preparing hint…"
                                : "Give a hint"}
                            </button>
                          </div>
                        )}
                        {aiHelpErrors[task.id] && (
                          <p className="ai-help-result error" role="alert">
                            <strong>Help could not load.</strong>{" "}
                            {aiHelpErrors[task.id]}
                          </p>
                        )}
                        {aiHelpByTask[task.id] && (
                          <p className="ai-help-result" aria-live="polite">
                            {aiHelpByTask[task.id]}
                          </p>
                        )}
                      </div>
                      <div className="vscode-only-box">
                        <Code2 />
                        <h4>Submit from local VS Code</h4>
                        <div className="checkpoint-question">
                          <strong>CURRENT TASK QUESTION</strong>
                          <p>{task.challenge_prompt}</p>
                        </div>
                        <ol>
                          <li>Implement the real project milestone.</li>
                          <li>
                            Open the required checkpoint and write the solution.
                          </li>
                          <li>
                            Run <strong>GAINT: Submit Current Task</strong>.
                          </li>
                          <li>
                            Required project files, local checks, and all 3
                            Judge0 checks must pass.
                          </li>
                        </ol>
                        {task.judge0 && (
                          <div
                            className={`judge-result ${task.judge0.status.toLowerCase()}`}
                          >
                            <strong>{task.judge0.status}</strong>
                            <span>
                              {task.judge0.passed_cases}/
                              {task.judge0.total_cases} automated checks passed
                            </span>
                            <small>
                              File: {task.judge0.file_names.join(", ")}
                            </small>
                            <small>SHA-256: {task.judge0.source_hash}</small>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </article>
              ))}
            </div>
          </section>

          <section
            className={`certificate-card ${assignment.certificate_ready ? "ready" : ""}`}
          >
            <span>
              {assignment.certificate_ready ? <Verified /> : <Award />}
            </span>
            <div>
              <p className="eyebrow">FINAL COMPLETION</p>
              <h2>
                {assignment.certificate_ready
                  ? "Certificate enabled and completed project ZIP created locally."
                  : "Pass every required project and Judge0 check."}
              </h2>
              <p>
                {assignment.certificate_ready
                  ? `Your clean runnable ZIP is created beside the project folder by VS Code${assignment.completion_package_name ? `: ${assignment.completion_package_name}` : ""}.`
                  : "A failed task can be corrected and resubmitted during your access/grace period. Payment does not guarantee a certificate."}
              </p>
              <p>
                {isCollege
                  ? "Present the runnable project locally and submit it directly to your college."
                  : "No attendance or College Coordinator is used for this individual internship."}
              </p>
            </div>
            <div className="download-actions">
              <button
                className="primary-button"
                disabled={!assignment.certificate_ready}
                onClick={downloadCertificate}
              >
                <Award size={17} /> Certificate
              </button>
              <button
                className="secondary-button"
                disabled={!assignment.certificate_ready}
                onClick={() =>
                  download(
                    "/student/evaluation-report",
                    "GAINT-Evaluation-Report.pdf",
                    "Evaluation report downloaded.",
                  )
                }
              >
                <FileText size={17} /> Evaluation report
              </button>
            </div>
          </section>
        </>
      )}
      {assignment?.access_enabled && currentTask && (
        <SupportBot
          taskTitle={`Task ${currentTask.order_no}: ${currentTask.title}`}
        />
      )}
    </Layout>
  );
}
