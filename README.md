<p align="center">
  <h1 align="center">PDF Compare AI</h1>
  <p align="center">
    <strong>AI-powered PDF comparison tool with visual diff highlighting</strong>
  </p>
  <p align="center">
    <em>Powered by Google Gemini AI · Dockerized · Side-by-Side Visual Comparison</em>
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white" alt="Python 3.11"/>
  <img src="https://img.shields.io/badge/Next.js-14-black?logo=nextdotjs&logoColor=white" alt="Next.js 14"/>
  <img src="https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white" alt="React 18"/>
  <img src="https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/Gemini_AI-Flash_3.1-4285F4?logo=google&logoColor=white" alt="Gemini AI"/>
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white" alt="Docker"/>
</p>

---

## Overview

**PDF Compare AI** is an intelligent document comparison tool that goes beyond simple text diff. Upload two PDFs and get a comprehensive, AI-powered analysis covering text, tables, images, bullet points, and headings — with a side-by-side visual comparison that highlights exactly what changed on every page.

Built for technical writers, legal teams, QA reviewers, and anyone who works with versioned documents.

---

## Key Features

### Side-by-Side Visual Comparison

- Renders every page of both PDFs as high-quality images
- **Overlay toggle in viewer** lets you switch between clean pages and highlighted diff mode
- **Aligned visual diff overlay** highlights changes directly on the pages
  - 🔴 Red overlay = Changed/removed content (Document A)
  - 🟢 Green overlay = Changed/added content (Document B)
- Navigate pages with dot pagination controls
- Responsive split panel with scroll

### AI-Powered Analysis (Gemini)

- **Page-by-page AI analysis** (differences ordered top-to-bottom)
- **Semantic text comparison** — understands meaning, not just characters
- **Image description & comparison** — uses Gemini Vision to describe and compare embedded images
- **Intelligent summary generation** — produces an overall executive change report
- **Table semantic analysis** — AI-powered summary of table differences

### Multi-Format Content Detection

| Content Type | Detection Method | AI Analysis |
|:---|:---|:---|
| Paragraphs | `pdfplumber` text extraction | ✅ Similarity scoring via `difflib` |
| Headings | Pattern + font-size heuristics | ✅ Structure change tracking |
| Bullet Points | Regex pattern matching | ✅ Item-level diff |
| Tables | Cell-level extraction via `pdfplumber` | ✅ Row/column change detection |
| Images | XObject extraction via `pypdf` + PIL conversion | ✅ Gemini Vision comparison |
| Scanned PDFs | Tesseract OCR fallback | ✅ Full text comparison after OCR |

### Similarity Scoring

- **Weighted average** of per-pair text similarity scores across all paragraphs, headings, and bullets
- Individual diff scores shown per text block (0–100%)
- Overall similarity gauge in the results sidebar

### Export

- **HTML report export** — generates a downloadable, self-contained comparison report with all diffs, stats, and the AI summary

---

## Tech Stack

### Backend

| Technology | Version | Purpose |
|:---|:---|:---|
| **Python** | 3.11 | Runtime |
| **FastAPI** | 0.111.0 | REST API framework |
| **Uvicorn** | 0.30.1 | ASGI server |
| **pdfplumber** | 0.11.0 | Text, table, and layout extraction |
| **pypdf** | 4.2.0 | PDF metadata and embedded image extraction |
| **pdf2image** | 1.17.0 | PDF page rendering (via Poppler) |
| **Pillow** | 10.3.0 | Image processing and format conversion |
| **pytesseract** | 0.3.10 | OCR for scanned PDFs |
| **numpy** | ≥1.26.0 | Pixel-level diff computation |
| **google-genai** | ≥1.0.0 | Gemini AI SDK (text + vision) |
| **pandas** | 2.2.2 | Data manipulation for table comparison |
| **python-multipart** | 0.0.9 | Multipart form data parsing for file uploads |
| **aiofiles** | 23.2.1 | Async file I/O |
| **python-dotenv** | 1.0.1 | Environment variable management |

### Frontend

| Technology | Version | Purpose |
|:---|:---|:---|
| **Next.js** | 14.2.3 | React framework with standalone output |
| **React** | 18.3.1 | UI component library |
| **TypeScript** | 5.4.5 | Type-safe JavaScript |
| **Axios** | 1.7.2 | HTTP client for API calls |
| **react-dropzone** | 14.2.3 | Drag-and-drop file upload |
| **lucide-react** | 0.395.0 | SVG icon library |
| **react-diff-viewer-continued** | 4.0.0 | Text diff visualization |

### Infrastructure

| Technology | Purpose |
|:---|:---|
| **Docker** | Containerization |
| **Docker Compose** | Multi-container orchestration |
| **Poppler** | PDF rendering engine (inside backend Docker image) |
| **Tesseract** | OCR engine (inside backend Docker image) |

### AI Model

| Model | Provider | Capabilities |
|:---|:---|:---|
| **gemini-3.1-flash-lite-preview** | Google | Multimodal (text + vision), fast inference |

> The model name is configurable via `.env` — you can switch to `gemini-2.0-flash` or any other Gemini model.

---

## Getting Started

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop) installed and running
- A [Google Gemini API key](https://aistudio.google.com) (free tier available)

### 1. Clone the repository

```bash
git clone https://github.com/vinoth12940/pdf-compare-ai.git
cd pdf-compare-ai
```

### 2. Configure your API key

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` and add your key:

```env
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-3.1-flash-lite-preview
```

### 3. Build and run with Docker

```bash
docker compose up --build -d
```

### 4. Open in browser

| Service | URL |
|:---|:---|
| **Frontend** | [http://localhost:3000](http://localhost:3000) |
| **Backend API** | [http://localhost:8000](http://localhost:8000) |
| **Swagger Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) |

### 5. Stop

```bash
docker compose down
```

---

## Run Locally (without Docker)

### Prerequisites

<details>
<summary><strong>macOS</strong></summary>

```bash
brew install poppler tesseract
python3 --version   # 3.11+
node --version       # 18+
```

</details>

<details>
<summary><strong>Ubuntu / Debian</strong></summary>

```bash
sudo apt-get update
sudo apt-get install -y poppler-utils tesseract-ocr
python3 --version   # 3.11+
node --version       # 18+
```

</details>

<details>
<summary><strong>Windows</strong></summary>

#### Option A: Using Chocolatey (recommended)

```powershell
# Run PowerShell as Administrator
choco install poppler tesseract python3 nodejs-lts -y
```

#### Option B: Using Scoop

```powershell
scoop install poppler tesseract python nodejs-lts
```

#### Option C: Manual Installation

1. **Python 3.11+** — Download from [python.org](https://www.python.org/downloads/). Check ✅ "Add Python to PATH" during install.
2. **Node.js 18+** — Download LTS from [nodejs.org](https://nodejs.org/)
3. **Poppler** — Download from [poppler releases](https://github.com/ossamamehmood/Poppler-Windows/releases). Extract to `C:\poppler` and add `C:\poppler\Library\bin` to your system PATH.
4. **Tesseract** — Download the installer from [UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki). Default install path is `C:\Program Files\Tesseract-OCR` (automatically added to PATH).

#### Verify Installation (PowerShell)

```powershell
python --version      # 3.11+
node --version        # 18+
pdftoppm -h           # Should show usage (Poppler)
tesseract --version   # Should show version (Tesseract)
```

</details>

---

### Backend

**macOS / Linux:**

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your GEMINI_API_KEY
uvicorn main:app --reload --port 8000
```

**Windows (PowerShell):**

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # edit .env and add your GEMINI_API_KEY
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install --legacy-peer-deps
npm run dev
```

> **Tip:** On Windows, if you get `pdftoppm is not installed` errors, make sure Poppler's `bin` directory is in your system PATH and restart your terminal.

---

## Project Structure

```
pdf-compare-ai/
├── docker-compose.yml              # Multi-container orchestration
├── CHANGELOG.md                    # Version history (Keep a Changelog)
├── llms.txt                        # AI-friendly documentation for RAG/crawlers
│
├── docs/
│   ├── api.md                      # Detailed API reference
│   └── architecture.md             # System architecture + ADRs
│
├── backend/
│   ├── Dockerfile                   # Python 3.11-slim + Poppler + Tesseract
│   ├── requirements.txt             # Python dependencies (13 packages)
│   ├── .env.example                 # Environment variable template
│   ├── main.py                      # FastAPI app — /compare, /health endpoints
│   ├── models/
│   │   └── schemas.py               # Pydantic models (ComparisonResult, TextDiff,
│   │                                #   PageDiff, TableDiff, TableCellDiff, ImageDiff, DiffType)
│   └── services/
│       ├── pdf_extractor.py         # PDF parsing, OCR, image extraction, diff overlays
│       ├── gemini_service.py        # Google Gemini AI (text compare, image describe,
│       │                            #   image compare, overall summary, table analysis,
│       │                            #   page-by-page sequential comparison)
│       └── comparator.py            # Text, table, image, bullet comparison engine
│                                    #   with weighted similarity scoring
│
└── frontend/
    ├── Dockerfile                   # Node 20-alpine, multi-stage build (deps → build → runner)
    ├── package.json                 # npm dependencies (7 runtime, 3 dev)
    ├── tsconfig.json                # TypeScript configuration
    ├── next.config.js               # Next.js config (standalone output, API URL env)
    ├── app/
    │   ├── page.tsx                 # Main app — upload view, results view,
    │   │                            #   stats sidebar, tabbed navigation,
    │   │                            #   side-by-side viewer, diff cards, report export
    │   ├── layout.tsx               # Root layout with metadata
    │   └── globals.css              # Product design system — Geist font,
    │                                #   app shell, dark theme, diff styling
    └── lib/
        └── api.ts                   # Typed API client (ComparisonResult, TextDiff,
                                     #   TableDiff, TableCellDiff, ImageDiff interfaces)
```

---

## Architecture

```
┌──────────────┐     ┌──────────────┐
│  Upload      │     │  Upload      │
│  PDF A       │     │  PDF B       │
└──────┬───────┘     └──────┬───────┘
       │                     │
       ▼                     ▼
┌─────────────────────────────────────┐
│          FastAPI Backend            │
│                                     │
│  1. EXTRACT                         │
│     pdfplumber → text, tables       │
│     pypdf → embedded images (PNG)   │
│     pytesseract → OCR (if scanned)  │
│     pdf2image → page renders        │
│                                     │
│  2. COMPARE                         │
│     difflib → text similarity       │
│     cell-level → table diff         │
│     matched text/table/image diff   │
│                                     │
│  3. AI ANALYZE (Gemini)             │
│     Semantic text comparison        │
│     Vision-based image comparison   │
│     Overall summary generation      │
│     Table semantic analysis         │
│     Page-by-page ordered diff       │
│                                     │
│  4. OVERLAY                         │
│     Aligned render-mask diff        │
│     Toggle ON/OFF in viewer         │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│          Next.js Frontend           │
│                                     │
│  AI Analysis Tab (default)          │
│  Side-by-Side Viewer + Overlay Toggle │
│  AI Summary Tab                     │
│  Paragraph Diff Tab                 │
│  Bullet Point Diff Tab              │
│  Formatting Diff Tab                │
│  Table Diff Tab                     │
│  Image Diff Tab                     │
│  Stats Sidebar + Similarity Gauge   │
│  HTML Report Export                  │
└─────────────────────────────────────┘
```

---

## API Reference

### `POST /compare`

Upload two PDFs for comparison.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|:---|:---|:---|:---|
| `file1` | File (PDF) | ✅ | First document |
| `file2` | File (PDF) | ✅ | Second document |
| `gemini_api_key` | String | ❌ | Override API key (optional if set in `.env`) |

**Response:** `application/json`

```jsonc
{
  "comparison_id": "uuid",
  "file1_name": "original.pdf",
  "file2_name": "updated.pdf",
  "overall_summary": "AI-generated executive summary...",
  "similarity_percentage": 87.3,
  "text_diffs": [
    {
      "page": 1,
      "content_a": "Text from Document A",
      "content_b": "Text from Document B",
      "diff_type": "changed",       // "added" | "removed" | "changed" | "unchanged"
      "similarity_score": 0.85,
      "section_type": "paragraph"    // "paragraph" | "heading" | "bullet"
    }
  ],
  "table_diffs": [
    {
      "page": 1,
      "table_index": 0,
      "headers_a": ["Col1", "Col2"],
      "headers_b": ["Col1", "Col2"],
      "cell_diffs": [
        { "row": 0, "col": 1, "value_a": "100", "value_b": "200", "diff_type": "changed" }
      ],
      "rows_added": 0,
      "rows_removed": 0,
      "diff_type": "changed"
    }
  ],
  "image_diffs": [
    {
      "page": 1,
      "image_index": 0,
      "description_a": "Gemini description of image A",
      "description_b": "Gemini description of image B",
      "diff_type": "changed",
      "ai_analysis": "The images show different data values..."
    }
  ],
  "bullet_diffs": [...],            // Same structure as text_diffs
  "ai_page_diffs": [
    {
      "page": 1,
      "location": "top",
      "section": "Header",
      "change_type": "changed",
      "description": "Company name updated",
      "text_in_a": "ABC Pvt Ltd",
      "text_in_b": "ABC Technologies Pvt Ltd"
    }
  ],
  "page_count_a": 3,
  "page_count_b": 3,
  "page_renders_a": ["base64..."],  // Base64 PNG page images (Document A)
  "page_renders_b": ["base64..."],  // Base64 PNG page images (Document B)
  "diff_overlay_a": ["base64..."],  // Base64 PNG with red highlights (Document A)
  "diff_overlay_b": ["base64..."],  // Base64 PNG with green highlights (Document B)
  "stats": {
    "paragraphs_changed": 5,
    "paragraphs_added": 1,
    "paragraphs_removed": 0,
    "bullets_changed": 2,
    "bullets_added": 0,
    "bullets_removed": 0,
    "tables_changed": 1,
    "images_changed": 1,
    "images_added": 0,
    "images_removed": 0,
    "doc_a_is_scanned": false,
    "doc_b_is_scanned": false
  }
}
```

### `GET /health`

Health check endpoint.

**Response:**

```json
{
  "status": "ok",
  "ocr_available": true,
  "gemini_configured": true
}
```

---

## UI Design

The frontend uses a **product-grade app shell** design inspired by Linear, Vercel, and Raycast:

- **Geist** font family for a clean, modern look
- **App shell layout** — top bar + full-height workspace area
- **Dark theme** with carefully tuned zinc/gray palette
- **Stats sidebar** — similarity gauge (SVG ring), page counts, and per-type diff counts
- **Tabbed toolbar** — AI Analysis, Side by Side, Summary, Paragraphs, Bullets, Formatting, Tables, Images  
- **Drag-and-drop** file upload with visual state feedback (idle → active → uploaded)
- **Progress indicator** with shimmer animation during AI analysis
- **Collapsible diff cards** with color-coded badges (added/removed/changed)
- **Word-level text highlighting** for changed text blocks
- **Side-by-side split panels** with dot pagination and overlay ON/OFF toggle
- **HTML report export** with matching stats and diff tables
- **Responsive design** — collapses sidebar and stacks panels on smaller screens
- **Reduced motion support** via `prefers-reduced-motion` media query

---

## Environment Variables

| Variable | Required | Default | Description |
|:---|:---|:---|:---|
| `GEMINI_API_KEY` | ✅ | — | Google Gemini API key |
| `GEMINI_MODEL` | ❌ | `gemini-3.1-flash-lite-preview` | Gemini model to use |
| `NEXT_PUBLIC_API_URL` | ❌ | `http://localhost:8000` | Backend API URL (set in `docker-compose.yml`) |

---

## Docker Details

### Backend Dockerfile

- Base: `python:3.11-slim`
- Installs: `poppler-utils`, `tesseract-ocr`, `tesseract-ocr-eng`, `libgl1`
- Runs on port `8000`

### Frontend Dockerfile

- Multi-stage build: `node:20-alpine`
  - **deps stage** — installs `npm` packages
  - **builder stage** — runs `next build` with standalone output
  - **runner stage** — minimal production image with `node server.js`
- Runs on port `3000`

### Docker Compose

- Backend health check: `curl http://localhost:8000/health` every 30s
- Frontend depends on backend
- Both services have `restart: unless-stopped`
- Backend env file: `./backend/.env`

---

## Documentation

| Document | Description |
|:---|:---|
| [API Reference](./docs/api.md) | Detailed endpoint specs, request/response schemas, examples |
| [Architecture](./docs/architecture.md) | System diagram, data flow, and Architecture Decision Records |
| [Changelog](./CHANGELOG.md) | Version history and release notes |
| [llms.txt](./llms.txt) | AI-friendly project documentation for RAG/crawlers |

---

## License

MIT

---

<p align="center">
  Built with ❤️ using <strong>FastAPI</strong> + <strong>Next.js</strong> + <strong>Google Gemini AI</strong>
</p>
