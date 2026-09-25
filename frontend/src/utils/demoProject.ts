/**
 * demoProject.ts — static demo project data for Phase 1.
 *
 * In Phase 2+ this is replaced by real project scanner results from the backend.
 * All component logic reads from ProjectMeta, so no component changes are
 * needed when the real scanner lands.
 */

import type { FileNode, ProjectMeta } from "@/types";

export const DEMO_FILE_CONTENTS: Record<string, string> = {
  "demo_project/src/App.jsx": `import { BrowserRouter, Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import Dashboard from "./components/Dashboard";
import Login from "./components/Login";

export default function App() {
  return (
    <BrowserRouter>
      <Navbar />
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/login" element={<Login />} />
      </Routes>
    </BrowserRouter>
  );
}`,

  "demo_project/src/main.jsx": `import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);`,

  "demo_project/src/components/Navbar.jsx": `import { Link } from "react-router-dom";

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
  brand: { fontWeight: "700", fontSize: "18px" },
  links: { display: "flex", gap: "24px" },
  link: { color: "#89b4fa", textDecoration: "none", fontSize: "14px" },
};`,

  "demo_project/src/components/Login.jsx": `import { useState } from "react";

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
    console.log("Login attempted with:", email);
  }

  return (
    <main>
      <h1>Sign in</h1>
      {error && <p>{error}</p>}
      <form onSubmit={handleSubmit}>
        <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="Email" />
        <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Password" />
        <button type="submit">Sign in</button>
      </form>
    </main>
  );
}`,

  "demo_project/src/components/Dashboard.jsx": `import { useState, useEffect } from "react";

const MOCK_TASKS = [
  { id: 1, title: "Implement authentication flow", status: "in-progress" },
  { id: 2, title: "Write unit tests for API layer", status: "pending" },
  { id: 3, title: "Refactor Dashboard component", status: "pending" },
  { id: 4, title: "Set up CI/CD pipeline", status: "done" },
];

export default function Dashboard() {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => {
      setTasks(MOCK_TASKS);
      setLoading(false);
    }, 400);
    return () => clearTimeout(timer);
  }, []);

  if (loading) return <p>Loading…</p>;

  return (
    <main>
      <h1>Dashboard</h1>
      <ul>
        {tasks.map(task => (
          <li key={task.id}>{task.title} — {task.status}</li>
        ))}
      </ul>
    </main>
  );
}`,

  "demo_project/package.json": `{
  "name": "demo-app",
  "version": "1.0.0",
  "type": "module",
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.23.1"
  }
}`,
};

const demoTree: FileNode[] = [
  {
    id: "src",
    name: "src",
    path: "demo_project/src",
    type: "directory",
    children: [
      {
        id: "components",
        name: "components",
        path: "demo_project/src/components",
        type: "directory",
        children: [
          {
            id: "Navbar.jsx",
            name: "Navbar.jsx",
            path: "demo_project/src/components/Navbar.jsx",
            type: "file",
            language: "jsx",
          },
          {
            id: "Login.jsx",
            name: "Login.jsx",
            path: "demo_project/src/components/Login.jsx",
            type: "file",
            language: "jsx",
          },
          {
            id: "Dashboard.jsx",
            name: "Dashboard.jsx",
            path: "demo_project/src/components/Dashboard.jsx",
            type: "file",
            language: "jsx",
          },
        ],
      },
      {
        id: "App.jsx",
        name: "App.jsx",
        path: "demo_project/src/App.jsx",
        type: "file",
        language: "jsx",
      },
      {
        id: "main.jsx",
        name: "main.jsx",
        path: "demo_project/src/main.jsx",
        type: "file",
        language: "jsx",
      },
    ],
  },
  {
    id: "package.json",
    name: "package.json",
    path: "demo_project/package.json",
    type: "file",
    language: "json",
  },
];

export const DEMO_PROJECT: ProjectMeta = {
  name: "demo-app",
  tree: demoTree,
};
