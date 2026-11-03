# OmniSearch

> **Academic Project Title:** Multifile Search Index Searcher  
> **Tagline:** One search. Your entire digital world.

OmniSearch is a professional, local-first, AI-powered multifile search and personal knowledge discovery desktop application engineered for Windows. It provides fast, privacy-preserving search across heterogeneous file formats (documents, spreadsheets, presentations, and text notes) using both exact keyword matching and natural-language queries—all without sending user files to the cloud.

---

## 1. Technology Stack

### Backend
- **Python 3.11+**
- **FastAPI** — High-performance ASGI web framework
- **Pydantic & Pydantic Settings** — Strongly-typed validation and centralized environment configuration
- **Uvicorn** — Production ASGI server

### Frontend
- **Next.js 15 (App Router)** — Modern React application framework
- **React 19 & TypeScript** — Type-safe, component-driven user interface
- **Tailwind CSS** — Restrained dark navy design system with subtle cyan accents
- **Lucide React** — Minimalist UI iconography

### Architecture Roadmap (Future Phases)
- **Desktop Shell:** Electron
- **Lexical Search & Storage:** SQLite with FTS5 extension (BM25 ranking)
- **Dense Vector Search:** ChromaDB
- **Embedding Model:** Google EmbeddingGemma 2

---

## 2. Project Structure

```text
OmniSearch/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── endpoints/
│   │   │       │   ├── __init__.py
│   │   │       │   └── health.py       # Health check route handler
│   │   │       ├── __init__.py
│   │   │       └── router.py           # V1 API router aggregator
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py               # Pydantic Settings configuration
│   │   │   └── logging.py              # Centralized logging setup
│   │   ├── models/                     # Domain & persistence models
│   │   ├── schemas/                    # Pydantic API schemas
│   │   │   ├── __init__.py
│   │   │   └── health.py               # HealthResponse schema
│   │   ├── services/                   # Business logic services
│   │   ├── utils/                      # Reusable utilities
│   │   ├── __init__.py
│   │   └── main.py                     # FastAPI application entry point
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py                 # Pytest test fixtures
│   │   └── test_health.py              # Health endpoint automated tests
│   ├── pyproject.toml                  # Backend project & dependency metadata
│   └── .env.example                    # Environment variable template
│
├── frontend/
│   ├── app/
│   │   ├── globals.css                 # Dark navy theme styling
│   │   ├── layout.tsx                  # Root HTML layout with metadata
│   │   └── page.tsx                    # Minimalist foundation homepage
│   ├── components/                     # Reusable UI components
│   ├── lib/                            # Frontend utility functions
│   ├── public/                         # Static assets
│   ├── package.json                    # Frontend dependencies and scripts
│   ├── tsconfig.json                   # TypeScript configuration
│   ├── tailwind.config.ts              # Tailwind CSS design system config
│   ├── postcss.config.mjs              # PostCSS plugins
│   ├── eslint.config.mjs               # ESLint configuration
│   └── next.config.mjs                 # Next.js configuration
│
├── docs/
│   ├── ARCHITECTURE.md                 # System architecture & component responsibilities
│   └── DEVELOPMENT.md                  # Development environment and testing guide
│
├── scripts/                            # Operational and automation scripts
├── .gitignore                          # Git exclusions for Python, Node, OS, & secrets
├── README.md                           # Project overview and quickstart
└── LICENSE                             # MIT License
```

---

## 3. Prerequisites

- **Python:** 3.11 or later
- **Node.js:** 20 or later
- **npm:** 10 or later
- **Git:** 2.x or later

---

## 4. Quickstart Guide

### 4.1 Backend Setup & Execution

1. **Navigate to the backend directory and activate your virtual environment:**
   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. **Install dependencies:**
   ```powershell
   python -m pip install -e ".[dev]"
   ```

3. **Set up local environment configuration:**
   ```powershell
   copy .env.example .env
   ```

4. **Start the FastAPI server:**
   ```powershell
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

5. **Verify operation:**
   - Health check: `http://127.0.0.1:8000/api/v1/health`
   - API Docs: `http://127.0.0.1:8000/docs`

### 4.2 Frontend Setup & Execution

1. **Navigate to the frontend directory:**
   ```powershell
   cd frontend
   npm install
   ```

2. **Start the Next.js development server:**
   ```powershell
   npm run dev
   ```

3. **Open the interface in your browser:**
   - URL: `http://localhost:3000`

---

## 5. Running Automated Tests

Run the backend test suite using `pytest`:

```powershell
.\backend\.venv\Scripts\pytest backend\tests -v
```

All tests verify that the health endpoint returns structured, type-safe data matching the `HealthResponse` schema.

---

## 6. Architecture & Engineering Rules

- **Strict Local-First:** Original files never leave the host system.
- **Loopback Binding:** Backend binds to `127.0.0.1` by default, never `0.0.0.0`.
- **Clean Separation:** Presentation (Next.js) is strictly decoupled from the core engine (FastAPI).
- **No Mock Functionality:** No fake search results or mock progress bars are introduced. Features are built iteratively according to project phase scope.

For deeper architectural details, refer to [ARCHITECTURE.md](docs/ARCHITECTURE.md). For development guidelines, see [DEVELOPMENT.md](docs/DEVELOPMENT.md).

---

## 7. License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

