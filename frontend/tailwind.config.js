/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          '"Segoe UI"',
          "system-ui",
          "sans-serif",
        ],
        mono: [
          '"JetBrains Mono"',
          '"Fira Code"',
          '"Cascadia Code"',
          "Consolas",
          "monospace",
        ],
      },
      colors: {
        surface: {
          DEFAULT: "#0d0d14",
          1: "#111118",
          2: "#16161f",
          3: "#1c1c28",
          4: "#252535",
        },
        border: {
          DEFAULT: "#2a2a3d",
          focus: "#5b8af8",
        },
        text: {
          primary: "#e2e4ef",
          secondary: "#9199b8",
          muted: "#5c6382",
          accent: "#5b8af8",
        },
        status: {
          ok: "#4ade80",
          warn: "#facc15",
          error: "#f87171",
          info: "#60a5fa",
        },
      },
    },
  },
  plugins: [],
};
