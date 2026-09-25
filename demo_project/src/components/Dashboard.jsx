import { useState, useEffect } from "react";

/**
 * Dashboard — main view of the demo application.
 * Displays a list of tasks fetched from a local mock source.
 */
const MOCK_TASKS = [
  { id: 1, title: "Implement authentication flow", status: "in-progress" },
  { id: 2, title: "Write unit tests for API layer", status: "pending" },
  { id: 3, title: "Refactor Dashboard component", status: "pending" },
  { id: 4, title: "Set up CI/CD pipeline", status: "done" },
  { id: 5, title: "Deploy to staging environment", status: "done" },
];

const STATUS_COLORS = {
  done: "#a6e3a1",
  "in-progress": "#fab387",
  pending: "#6c7086",
};

export default function Dashboard() {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Simulate async data fetch
    const timer = setTimeout(() => {
      setTasks(MOCK_TASKS);
      setLoading(false);
    }, 400);
    return () => clearTimeout(timer);
  }, []);

  return (
    <main style={styles.main}>
      <header style={styles.header}>
        <h1 style={styles.title}>Dashboard</h1>
        <p style={styles.subtitle}>Your current tasks and project status.</p>
      </header>

      {loading ? (
        <p style={styles.loading}>Loading tasks…</p>
      ) : (
        <ul style={styles.list}>
          {tasks.map((task) => (
            <li key={task.id} style={styles.item}>
              <span style={styles.taskTitle}>{task.title}</span>
              <span
                style={{
                  ...styles.badge,
                  color: STATUS_COLORS[task.status],
                  borderColor: STATUS_COLORS[task.status],
                }}
              >
                {task.status}
              </span>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

const styles = {
  main: {
    padding: "40px 48px",
    minHeight: "calc(100vh - 56px)",
    background: "#181825",
    color: "#cdd6f4",
  },
  header: { marginBottom: "32px" },
  title: { margin: 0, fontSize: "24px", fontWeight: "600" },
  subtitle: { margin: "8px 0 0", color: "#a6adc8", fontSize: "14px" },
  loading: { color: "#a6adc8", fontSize: "14px" },
  list: { listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: "12px" },
  item: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "16px 20px",
    background: "#1e1e2e",
    borderRadius: "8px",
    border: "1px solid #313244",
  },
  taskTitle: { fontSize: "14px" },
  badge: {
    fontSize: "11px",
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: "0.5px",
    padding: "3px 8px",
    borderRadius: "4px",
    border: "1px solid",
  },
};
