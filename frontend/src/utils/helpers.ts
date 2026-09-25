/** Generates a short unique ID (not cryptographically strong). */
export function uid(): string {
  return Math.random().toString(36).slice(2, 10);
}

/** Formats a Date to a compact HH:MM string. */
export function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** Returns the file extension from a file path. */
export function getExtension(path: string): string {
  const parts = path.split(".");
  return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : "";
}

/** Maps a file extension to a simple language label. */
export function languageFromPath(path: string): string {
  const ext = getExtension(path);
  const map: Record<string, string> = {
    ts: "TypeScript",
    tsx: "TypeScript JSX",
    js: "JavaScript",
    jsx: "JavaScript JSX",
    json: "JSON",
    py: "Python",
    md: "Markdown",
    html: "HTML",
    css: "CSS",
    yaml: "YAML",
    yml: "YAML",
    txt: "Plain Text",
  };
  return map[ext] ?? ext.toUpperCase();
}
