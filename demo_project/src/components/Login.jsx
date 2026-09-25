import { useState } from "react";

/**
 * Login — simple credential form for the demo application.
 * This component demonstrates form state management.
 */
export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);

  function handleSubmit(e) {
    e.preventDefault();
    if (!email || !password) {
      setError("Please enter both email and password.");
      return;
    }
    setError(null);
    // NOTE: authentication logic goes here in a real application.
    console.log("Login attempted with:", email);
  }

  return (
    <main style={styles.main}>
      <div style={styles.card}>
        <h1 style={styles.heading}>Sign in</h1>
        {error && <p style={styles.error}>{error}</p>}
        <form onSubmit={handleSubmit} style={styles.form}>
          <label htmlFor="email" style={styles.label}>Email</label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={styles.input}
            placeholder="you@example.com"
            autoComplete="email"
          />
          <label htmlFor="password" style={styles.label}>Password</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={styles.input}
            placeholder="••••••••"
            autoComplete="current-password"
          />
          <button type="submit" style={styles.button}>Sign in</button>
        </form>
      </div>
    </main>
  );
}

const styles = {
  main: {
    display: "flex",
    justifyContent: "center",
    paddingTop: "80px",
    minHeight: "calc(100vh - 56px)",
    background: "#181825",
  },
  card: {
    background: "#1e1e2e",
    borderRadius: "8px",
    padding: "40px 48px",
    width: "360px",
    color: "#cdd6f4",
    boxShadow: "0 4px 24px rgba(0,0,0,0.4)",
  },
  heading: { margin: "0 0 24px", fontSize: "22px", fontWeight: "600" },
  error: { color: "#f38ba8", marginBottom: "16px", fontSize: "13px" },
  form: { display: "flex", flexDirection: "column", gap: "12px" },
  label: { fontSize: "13px", color: "#a6adc8" },
  input: {
    padding: "10px 12px",
    borderRadius: "6px",
    border: "1px solid #313244",
    background: "#181825",
    color: "#cdd6f4",
    fontSize: "14px",
    outline: "none",
  },
  button: {
    marginTop: "8px",
    padding: "11px",
    borderRadius: "6px",
    border: "none",
    background: "#89b4fa",
    color: "#1e1e2e",
    fontWeight: "600",
    fontSize: "14px",
    cursor: "pointer",
  },
};
