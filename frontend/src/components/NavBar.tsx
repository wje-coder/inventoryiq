import { useState } from "react";
import { NavLink } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

export function NavBar() {
  const { user, logout } = useAuth();
  const [loggingOut, setLoggingOut] = useState(false);

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await logout();
    } finally {
      setLoggingOut(false);
    }
  }

  return (
    <nav aria-label="Main navigation" className="nav-bar">
      <span className="nav-brand">InventoryIQ</span>
      <NavLink to="/" end className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
        Dashboard
      </NavLink>
      <NavLink
        to="/datasets"
        className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
      >
        Datasets
      </NavLink>
      <NavLink
        to="/analytics"
        className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
      >
        Analytics
      </NavLink>
      <span className="nav-spacer" />
      {user && <span className="nav-user">{user.email}</span>}
      <button type="button" onClick={handleLogout} disabled={loggingOut}>
        {loggingOut ? "Logging out…" : "Log out"}
      </button>
    </nav>
  );
}
