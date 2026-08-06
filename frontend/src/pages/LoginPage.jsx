import { ArrowRight, BookOpen, Building2, CheckCircle2, GraduationCap, ShieldCheck, Users } from "lucide-react";
import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import Notice from "../components/Notice";

const roles = [
  { value: "student", label: "Student", icon: GraduationCap },
  { value: "mentor", label: "Mentor", icon: Users },
  { value: "coordinator", label: "Coordinator", icon: Building2 },
  { value: "admin", label: "Admin", icon: ShieldCheck },
];

export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [role, setRole] = useState("student");
  const [form, setForm] = useState({ email: "student@gaint.com", password: "Student@123" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to={`/${user.role}`} replace />;

  const selectRole = (value) => {
    setRole(value);
    setError("");
    if (value === "admin") setForm({ email: "admin@gaint.com", password: "Admin@123" });
    else if (value === "mentor") setForm({ email: "mentor@gaint.com", password: "Mentor@123" });
    else if (value === "coordinator") setForm({ email: "coordinator@gaint.com", password: "Coordinator@123" });
    else setForm({ email: "student@gaint.com", password: "Student@123" });
  };
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const loggedIn = await login({ ...form, role });
      navigate(`/${loggedIn.role}`);
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  };

  return <div className="auth-page">
    <section className="auth-hero">
      <div className="brand large"><span className="brand-mark"><BookOpen /></span><span><strong>GAINT</strong><small>Interns Hub</small></span></div>
      <div className="hero-copy"><span className="free-pill">FREE FOR COLLEGE STUDENTS · ONE PAYMENT FOR INDIVIDUALS</span><h1>Learn. Build.<br /><em>Get Certified.</em></h1><p>A guided internship platform with local VS Code projects, sequential evaluation and Mentor verification.</p>
        <ul><li><CheckCircle2 /> Role-based guided learning</li><li><CheckCircle2 /> Real coding tasks and evaluation</li><li><CheckCircle2 /> Mentor feedback and free certificate</li></ul>
      </div>
    </section>
    <section className="auth-form-wrap"><div className="auth-card"><p className="eyebrow">WELCOME BACK</p><h2>Sign in to your account</h2><p>Choose your role and continue your internship journey.</p>
      <div className="role-tabs">{roles.map(({ value, label, icon: Icon }) => <button key={value} className={role === value ? "active" : ""} onClick={() => selectRole(value)}><Icon size={18} />{label}</button>)}</div>
      <Notice type="error" message={error} />
      <form onSubmit={submit} className="form-stack"><label>Email address<input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="you@college.edu" /></label><label>Password<input type="password" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="Enter your password" /></label><button className="primary-button" disabled={busy}>{busy ? "Signing in…" : <>Sign in <ArrowRight size={18} /></>}</button></form>
      {role === "student" && <><p className="auth-switch">Individual student? <Link to="/register">Create an account</Link></p><p className="demo-note">College students log in with Admin-provided credentials. Demo student credentials are filled automatically.</p></>}
      {role !== "student" && <p className="demo-note">Demo credentials are filled automatically.</p>}
    </div></section>
  </div>;
}
