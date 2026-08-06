import { ArrowLeft, ArrowRight, BookOpen } from "lucide-react";
import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import Notice from "../components/Notice";

export default function RegisterPage() {
  const { user, register } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to={`/${user.role}`} replace />;
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    if (data.get("password") !== data.get("confirm_password")) {
      setError("Password and confirm password must match"); setBusy(false); return;
    }
    data.delete("confirm_password");
    try { await register(data); navigate("/student"); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };
  return <div className="register-page"><header className="register-header"><div className="brand"><span className="brand-mark"><BookOpen /></span><span><strong>GAINT</strong><small>Interns Hub</small></span></div><Link to="/login"><ArrowLeft size={17} /> Back to login</Link></header>
    <main className="register-card"><p className="eyebrow">INDIVIDUAL STUDENT REGISTRATION</p><h1>Start your internship journey</h1><p>Individual students register here and pay once after selecting a project. College students must use the login credentials supplied by their college Coordinator or GAINT Admin.</p><Notice type="error" message={error} />
      <form onSubmit={submit} className="form-grid">
        <label>Full name<input name="name" required minLength="2" placeholder="Your full name" /></label>
        <label>Email<input name="email" type="email" required placeholder="you@example.com" /></label>
        <label>Mobile number<input name="mobile" required pattern="[0-9]{10}" placeholder="10-digit mobile number" /></label>
        <label>Pursuing year <small>(optional)</small><select name="pursuing_year" defaultValue=""><option value="">Select year</option><option>B.Tech 1st Year</option><option>B.Tech 2nd Year</option><option>B.Tech 3rd Year</option><option>B.Tech 4th Year</option><option>B.Sc 1st Year</option><option>B.Sc 2nd Year</option><option>B.Sc 3rd Year</option><option>B.Sc 4th Year</option></select></label>
        <label>Internship type<select name="internship_type" required defaultValue="FASTTRACK"><option value="FASTTRACK">FastTrack – 1 Month</option><option value="45_DAYS">45 Days</option><option value="SEMESTER">Semester – 4 Months</option></select></label>
        <label>Password<input name="password" type="password" required minLength="8" placeholder="Minimum 8 characters" /></label>
        <label>Confirm password<input name="confirm_password" type="password" required minLength="8" placeholder="Repeat password" /></label>
        <button className="primary-button full" disabled={busy}>{busy ? "Creating account…" : <>Create individual account <ArrowRight size={18} /></>}</button>
      </form><p className="auth-switch">Already registered? <Link to="/login">Sign in</Link></p>
    </main>
  </div>;
}
