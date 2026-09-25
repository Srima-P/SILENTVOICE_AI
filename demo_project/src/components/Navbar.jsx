import { Link } from "react-router-dom";

/**
 * Navbar — top-level navigation for the demo application.
 */
export default function Navbar() {
  return (
    <nav style={styles.nav}>
      <span style={styles.brand}>DemoApp</span>
      <div style={styles.links}>
        <Link to="/" style={styles.link}>Dashboard</Link>
        <Link to="/login" style={styles.link}>Login</Link>
      </div>
    </nav>
  );
}

const styles = {
  nav: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "0 24px",
    height: "56px",
    background: "#1e1e2e",
    color: "#cdd6f4",
  },
  brand: {
    fontWeight: "700",
    fontSize: "18px",
    letterSpacing: "0.5px",
  },
  links: {
    display: "flex",
    gap: "24px",
  },
  link: {
    color: "#89b4fa",
    textDecoration: "none",
    fontSize: "14px",
  },
};
