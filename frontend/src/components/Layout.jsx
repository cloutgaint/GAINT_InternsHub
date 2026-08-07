import { LogOut, ShieldCheck } from "lucide-react";
import { useAuth } from "../auth";
import logo from "../images/logo.png";

export default function Layout({ title, subtitle, children, actions }) {
  const { user, logout } = useAuth();
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <img className="brand-logo" src={logo} alt="GAINT Interns Hub" />
        </div>
        <div className="profile-card">
          <div className="avatar">{user?.name?.charAt(0).toUpperCase()}</div>
          <div><strong>{user?.name}</strong><small>{user?.role}</small></div>
        </div>
        <div className="side-message">
          <ShieldCheck size={20} />
          <div><strong>College Program</strong><small>Free internship access</small></div>
        </div>
        <button className="logout-button" onClick={logout}><LogOut size={18} /> Logout</button>
      </aside>
      <main className="main-content">
        <header className="page-header">
          <div><p className="eyebrow">GAINT INTERNS HUB</p><h1>{title}</h1><p>{subtitle}</p></div>
          {actions && <div className="header-actions">{actions}</div>}
        </header>
        {children}
      </main>
    </div>
  );
}
