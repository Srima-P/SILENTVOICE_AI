# SilentVoice AI

> **Accessibility-first, voice-driven AI development workspace.**

SilentVoice AI is a developer tool that lets you interact with and understand software projects using natural language — voice or text — while keeping you in complete control of any AI-generated code changes.

---

## Table of Contents

1. [What is SilentVoice AI?](#what-is-silentvoice-ai)
2. [Problem Being Solved](#problem-being-solved)
3. [Architecture](#architecture)
4. [Technology Stack](#technology-stack)
5. [Folder Structure](#folder-structure)
6. [Prerequisites](#prerequisites)
7. [Installation](#installation)
8. [Environment Variables](#environment-variables)
9. [Starting the Backend](#starting-the-backend)
10. [Starting the Frontend](#starting-the-frontend)
11. [Frontend ↔ Backend Connection](#frontend--backend-connection)
12. [Phase 1 Capabilities](#phase-1-capabilities)
13. [Features Reserved for Later Phases](#features-reserved-for-later-phases)

---

## What is SilentVoice AI?

SilentVoice AI is a professional developer workspace that bridges the gap between natural language and code. You open a project, ask questions or issue commands in plain English (or via voice), and the AI explains, analyses, and carefully proposes changes — always waiting for your approval before modifying a single file.

---

## Problem Being Solved

Developers — especially those with accessibility needs — often struggle to navigate large codebases efficiently. Existing tools are mouse-heavy, visually dense, and provide no natural language interface. SilentVoice AI makes projects approachable for everyone by allowing voice and text commands to drive exploration and modification, with full human oversight.

---

## Architecture

```
Browser (React SPA)
        │
        │  HTTP via Vite dev-proxy  →  /api/*
        ▼
FastAPI Backend (Python)
        │
        │  [Phase 2+] Groq LLM API
        │  [Phase 2+] Project Scanner
        │  [Phase 2+] Sandbox
        ▼
   File System / AI Services
```

- The **frontend** is a single-page application served by Vite in development.  
- Vite proxies all `/api` requests to the FastAPI backend, avoiding CORS issues in development.  
- In production both are deployed behind a reverse proxy (e.g., nginx).

---

## Technology Stack

| Layer      | Technology                                      |
|------------|-------------------------------------------------|
| Frontend   | React 18, Vite, TypeScript, Tailwind CSS, Lucide React, React Router |
| Backend    | Python 3.11+, FastAPI, Uvicorn, Pydantic v2     |
| Config     | `.env` / `python-dotenv` / `pydantic-settings`  |

---

## Folder Structure

```
silentvoice-ai/
│
├── frontend/                     # React + Vite + TypeScript SPA
│   ├── src/
│   │   ├── components/           # Reusable UI components
│   │   ├── pages/                # Route-level page components
│   │   ├── layouts/              # Layout wrappers
│   │   ├── hooks/                # Custom React hooks
│   │   ├── services/             # Backend API service layer
│   │   ├── types/                # TypeScript type definitions
│   │   ├── utils/                # Utility functions & demo data
│   │   ├── contexts/             # React context + state management
│   │   ├── App.tsx               # Root component + router
│   │   ├── main.tsx              # Entry point
│   │   └── index.css             # Global styles + Tailwind
│   │
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── tsconfig.json
│
├── backend/                      # FastAPI Python backend
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes/           # Individual API route modules
│   │   │   │   └── health.py     # GET /api/health
│   │   │   └── router.py         # Centralised router mount
│   │   ├── services/             # Business logic (Phase 2+)
│   │   ├── models/               # SQLAlchemy / domain models (Phase 2+)
│   │   ├── schemas/              # Pydantic request/response schemas
│   │   ├── utils/
│   │   │   └── errors.py         # Global exception handling
│   │   ├── config.py             # Settings via pydantic-settings
│   │   └── main.py               # FastAPI app, middleware, startup
│   │
│   └── requirements.txt
│
├── demo_project/                 # Sample React app for Phase 2 scanning
│   ├── src/
│   │   ├── components/
│   │   │   ├── Navbar.jsx
│   │   │   ├── Login.jsx
│   │   │   └── Dashboard.jsx
│   │   ├── App.jsx
│   │   └── main.jsx
│   └── package.json
│
├── .env.example                  # Environment variable template
├── .gitignore
└── README.md
```

---

## Prerequisites

| Tool       | Version  | Notes                          |
|------------|----------|--------------------------------|
| Node.js    | 18+      | LTS recommended                |
| npm        | 9+       | Bundled with Node.js           |
| Python     | 3.11+    | Earlier 3.x may work           |
| pip        | latest   | `pip install --upgrade pip`    |

---

## Installation

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd silentvoice-ai
```

### 2. Set up environment variables

```bash
cp .env.example .env
# Edit .env if you need non-default ports
```

### 3. Install backend dependencies

```bash
cd backend
pip install -r requirements.txt
cd ..
```

### 4. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

---

## Environment Variables

| Variable          | Default                                     | Description                          |
|-------------------|---------------------------------------------|--------------------------------------|
| `BACKEND_HOST`    | `127.0.0.1`                                 | Host the FastAPI server binds to     |
| `BACKEND_PORT`    | `8000`                                      | Port the FastAPI server listens on   |
| `FRONTEND_PORT`   | `5173`                                      | Vite dev server port                 |
| `ALLOWED_ORIGINS` | `http://localhost:5173,...`                 | CORS allowed origins (comma-separated) |
| `APP_ENV`         | `development`                               | `development` or `production`        |
| `LOG_LEVEL`       | `info`                                      | Python logging level                 |
| `GROQ_API_KEY`    | *(empty)*                                   | Reserved for Phase 2 — leave blank   |

> **Security note:** Never commit your `.env` file. It is excluded by `.gitignore`.

---

## Starting the Backend

```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API will be available at `http://127.0.0.1:8000`.  
Interactive docs: `http://127.0.0.1:8000/docs` (development mode only).

---

## Starting the Frontend

In a separate terminal:

```bash
cd frontend
npm run dev
```

The application opens at `http://localhost:5173`.

---

## Frontend ↔ Backend Connection

Vite's dev server proxies all requests starting with `/api` to the backend:

```
Browser  →  http://localhost:5173/api/health
                   ↓  (Vite proxy)
Backend  →  http://127.0.0.1:8000/api/health
```

This means no absolute backend URL is needed in frontend code.  
The proxy configuration lives in [`frontend/vite.config.ts`](frontend/vite.config.ts).

The frontend polls `GET /api/health` every 30 seconds and displays the result in the top bar:

- 🟢 **Connected** — backend is running and healthy  
- 🔴 **Offline** — backend is unreachable  
- 🟡 **Checking…** — initial poll in progress

---

## Phase 1 Capabilities

- ✅ Professional developer workspace UI (IDE-style layout)
- ✅ Project explorer with folder/file tree (demo project)
- ✅ Code viewer with line numbers (read-only)
- ✅ AI assistant panel (UI shell — no AI yet)
- ✅ Workflow panel with Changes / Diff / Activity tabs
- ✅ Backend health-check endpoint (`GET /api/health`)
- ✅ Live backend connection status in top bar
- ✅ Accessibility mode toggle (larger text, strong focus)
- ✅ Settings page (backend status, accessibility preferences, app info)
- ✅ Keyboard navigation throughout
- ✅ ARIA labels and semantic HTML
- ✅ Environment variable configuration
- ✅ CORS-safe frontend/backend separation
- ✅ TypeScript throughout the frontend

---

## Features Reserved for Later Phases

| Feature                        | Phase |
|-------------------------------|-------|
| Groq LLM integration          | 2     |
| Intent classification          | 2     |
| Voice / speech recognition     | 2     |
| Text-to-speech responses       | 2     |
| Real project scanner           | 2     |
| File reading from disk         | 2     |
| Code explanation               | 2     |
| Dependency analysis            | 2     |
| Diff generation                | 3     |
| Human approval workflow        | 3     |
| Sandbox-based file modification| 3     |
| Automatic code modification    | 3     |

---

*SilentVoice AI — Phase 1 Foundation*
