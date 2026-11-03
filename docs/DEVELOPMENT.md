# OmniSearch Development Guide

This guide describes how to configure your local development environment, install dependencies, run the backend and frontend development servers, and run automated verification tests.

---

## 1. Prerequisites

Ensure the following tools are installed on your Windows development workstation:

- **Python:** 3.11 or later (`python --version`)
- **Node.js:** 20 or later (`node --version`)
- **npm:** 10 or later (`cmd /c npm --version`)
- **Git:** 2.x or later (`git --version`)

---

## 2. Environment Setup

### 2.1 Backend Setup

1. **Navigate to the backend directory:**
   ```powershell
   cd backend
   ```

2. **Create and activate the virtual environment:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   *(If PowerShell script execution is restricted on your machine, you can run commands directly using `.\.venv\Scripts\python.exe` or `.\.venv\Scripts\uvicorn.exe`)*

3. **Install dependencies in editable mode with development packages:**
   ```powershell
   python -m pip install -e ".[dev]"
   ```

4. **Configure environment variables:**
   ```powershell
   copy .env.example .env
   ```
   Review `.env` to verify configuration defaults (host `127.0.0.1`, port `8000`, log level `INFO`).

### 2.2 Frontend Setup

1. **Navigate to the frontend directory:**
   ```powershell
   cd frontend
   ```

2. **Install Node.js packages:**
   ```powershell
   npm install
   ```

---

## 3. Running Development Servers

### 3.1 Start the FastAPI Backend

Run from the root or `backend/` directory:

```powershell
# From backend directory with activated virtual environment
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Or directly from root without activating virtual environment
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

Once running, verify backend operation:
- **Health Check Endpoint:** `http://127.0.0.1:8000/api/v1/health`
- **Interactive Swagger Documentation:** `http://127.0.0.1:8000/docs`
- **Interactive OpenAPI ReDoc:** `http://127.0.0.1:8000/redoc`

### 3.2 Start the Next.js Frontend

Run from the `frontend/` directory:

```powershell
cd frontend
npm run dev
```

The Next.js application will start on `http://localhost:3000`.

---

## 4. Running Automated Tests

### 4.1 Backend Test Suite

Run pytest using the virtual environment:

```powershell
# From project root
.\backend\.venv\Scripts\pytest backend\tests -v
```

This tests:
- **Phase 1 Foundations:** HTTP 200 response on `GET /api/v1/health`, schema compliance with `HealthResponse`.
- **Ingestion Hashing:** Streaming 64 KB chunked SHA-256 computation, empty files, and error handling.
- **File Type Detector:** Extension validation, signature inspection, disguised executable blocking.
- **Folder Scanner:** Recursive folder traversal, directory exclusion (`.git`, `node_modules`, `.venv`), missing directory handling.
- **Multi-Format Extractors:** Genuine document parsing for PDF, DOCX, PPTX, XLSX, TXT, Markdown, Source Code, CSV, and HTML.
- **Ingestion Coordinator:** Batch processing, fault isolation, and uninterrupted batch execution upon individual file corruption.
- **Text Normalization:** Unicode NFKC normalization, control character removal, line endings, code indentation preservation.
- **Intelligent Chunking:** Target size ~500 tokens, ~80 token overlap, sentence and code line boundary preservation, location metadata retention.
- **Database Architecture:** Table and index creation, foreign key CASCADE deletions, transaction rollback, persistence across re-open, migrations.
- **Persistent Indexing Service:** New file indexing, duplicate skipping, modified file chunk replacement, deleted file reconciliation, and interrupted job recovery.

### 4.2 Frontend Checks

To run Next.js linting and production build verification:

```powershell
cd frontend
npm run lint
npm run build
```

---

## 5. Git Workflow & Conventions

1. **Branching:** Use clean feature branches branching from `main`.
2. **Commit Convention:** Follow Conventional Commits:
   - `chore: ...` for foundation, setup, and maintenance.
   - `feat: ...` for user-facing features.
   - `fix: ...` for bug fixes.
   - `test: ...` for test additions and updates.
   - `docs: ...` for documentation updates.
3. **Hygiene Rules:**
   - Never commit `.venv/`, `node_modules/`, `.next/`, or `.env` files containing secrets.
   - Keep `.env.example` updated when adding new configuration parameters.
   - All Python code must include type hints.
   - All API endpoints must use explicit Pydantic request/response schemas.

