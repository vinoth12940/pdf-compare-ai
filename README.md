<p align="center">
  <h1 align="center">🔍 PDF Compare AI</h1>
  <p align="center">
    <strong>GenAI-powered PDF comparison tool with visual diff highlighting</strong>
  </p>
  <p align="center">
    <em>Powered by Google Gemini AI · Dockerized · Side-by-Side Visual Comparison</em>
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white" alt="Python 3.11"/>
  <img src="https://img.shields.io/badge/Next.js-15-black?logo=nextdotjs&logoColor=white" alt="Next.js 15"/>
  <img src="https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/Gemini_AI-Flash_3.1-4285F4?logo=google&logoColor=white" alt="Gemini AI"/>
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white" alt="Docker"/>
</p>

---

## 📖 Overview

**PDF Compare AI** is an intelligent document comparison tool that goes beyond simple text diff. Upload two PDFs and get a comprehensive, AI-powered analysis covering text, tables, images, bullet points, headings — with a side-by-side visual comparison that highlights exactly what changed on every page.

Built for technical writers, legal teams, QA reviewers, and anyone who works with versioned documents.

---

## ✨ Key Features

### 🔎 Side-by-Side Visual Comparison

- Renders every page of both PDFs as high-quality images
- **Pixel-level diff overlay** highlights changes directly on the pages
- 🔴 Red overlay = Changed/removed content (Document A)
- 🟢 Green overlay = Changed/added content (Document B)
- Toggle between highlighted and original views with one click
- Navigate between pages with pagination controls

### 🤖 AI-Powered Analysis (Gemini)

- **Semantic text comparison** — understands meaning, not just characters
- **Image description & comparison** — uses Gemini Vision to describe and compare embedded images
- **Intelligent summary generation** — produces an overall change report
- **Context-aware diff** — groups related changes together

### 📊 Multi-Format Content Detection

| Content Type | Detection Method | AI Analysis |
|:---|:---|:---|
| 📝 Paragraphs | `pdfplumber` text extraction | ✅ Semantic similarity scoring |
| 📋 Headings | Pattern + font-size detection | ✅ Structure change tracking |
| • Bullet Points | Regex pattern matching | ✅ Item-level diff |
| 🔢 Tables | Cell-level extraction | ✅ Row/column change summary |
| 🖼️ Images | XObject extraction + PIL conversion | ✅ Gemini Vision description |
| 🔍 Scanned PDFs | Tesseract OCR | ✅ Full text comparison |

### 📄 Detailed Comparison Reports

- **Overall similarity percentage** with change statistics
- **Per-section diffs** — paragraphs, bullets, tables, images in separate tabs
- **Cell-level table comparison** with added/removed row counts
- **Change type classification** — Added, Removed, Changed, Unchanged

---

## 🏗️ Tech Stack

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
| **python-dotenv** | 1.0.1 | Environment variable management |

### Frontend

| Technology | Version | Purpose |
|:---|:---|:---|
| **Next.js** | 15 | React framework with SSR |
| **React** | 19 | UI component library |
| **TypeScript** | 5 | Type-safe JavaScript |
| **Axios** | 1.7 | HTTP client for API calls |

### Infrastructure

| Technology | Purpose |
|:---|:---|
| **Docker** | Containerization |
| **Docker Compose** | Multi-container orchestration |
| **Poppler** | PDF rendering engine (inside Docker) |
| **Tesseract** | OCR engine (inside Docker) |

### AI Model

| Model | Provider | Capabilities |
|:---|:---|:---|
| **gemini-3.1-flash-lite-preview** | Google | Multimodal (text + vision), fast inference |

> The model name is configurable via `.env` — you can switch to `gemini-2.0-flash` or any other Gemini model.

---

## 🚀 Getting Started

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
| 🌐 **Frontend** | [http://localhost:3000](http://localhost:3000) |
| ⚡ **Backend API** | [http://localhost:8000](http://localhost:8000) |
| 📚 **Swagger Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) |

### 5. Stop

```bash
docker compose down
```

---

## 🖥️ Run Locally (without Docker)

### Prerequisites

```bash
# macOS
brew install poppler tesseract

# Ubuntu / Debian
sudo apt-get install poppler-utils tesseract-ocr

# Verify
python3 --version   # 3.11+
node --version       # 18+
```

### Backend

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your GEMINI_API_KEY
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install --legacy-peer-deps
npm run dev
```

---

## 📁 Project Structure

```
pdf-compare-ai/
├── docker-compose.yml              # Multi-container orchestration
│
├── backend/
│   ├── Dockerfile                   # Python 3.11-slim + Poppler + Tesseract
│   ├── requirements.txt             # Python dependencies
│   ├── .env.example                 # Environment variable template
│   ├── main.py                      # FastAPI application & /compare endpoint
│   ├── models/
│   │   └── schemas.py               # Pydantic request/response models
│   └── services/
│       ├── pdf_extractor.py         # PDF parsing, OCR, image extraction, diff overlays
│       ├── gemini_service.py        # Google Gemini AI integration
│       └── comparator.py           # Text, table, image, bullet comparison engine
│
└── frontend/
    ├── Dockerfile                   # Node 20-alpine multi-stage build
    ├── package.json                 # npm dependencies
    ├── tsconfig.json                # TypeScript configuration
    ├── next.config.js               # Next.js config with API proxy
    ├── app/
    │   ├── page.tsx                 # Main comparison UI + SideBySideViewer
    │   ├── layout.tsx               # Root layout with metadata
    │   └── globals.css              # Dark theme design system (CSS variables)
    └── lib/
        └── api.ts                   # Typed API client with Axios
```

---

## ⚙️ How It Works

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
│     pypdf → embedded images         │
│     pytesseract → OCR (if scanned)  │
│     pdf2image → page renders        │
│                                     │
│  2. COMPARE                         │
│     difflib → text similarity       │
│     cell-level → table diff         │
│     numpy → pixel-level page diff   │
│                                     │
│  3. AI ANALYZE (Gemini)             │
│     Semantic text comparison        │
│     Vision-based image comparison   │
│     Overall summary generation      │
│                                     │
│  4. OVERLAY                         │
│     Generate red/green highlights   │
│     on changed page regions         │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│          Next.js Frontend           │
│                                     │
│  📄 Side-by-Side Viewer (default)   │
│  📝 Paragraph Diff Tab             │
│  • Bullet Point Diff Tab            │
│  🔢 Table Diff Tab                 │
│  🖼️ Image Diff Tab                │
│  📊 AI Summary Tab                 │
└─────────────────────────────────────┘
```

---

## 🔌 API Reference

### `POST /compare`

Upload two PDFs for comparison.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|:---|:---|:---|:---|
| `file_a` | File (PDF) | ✅ | Original document |
| `file_b` | File (PDF) | ✅ | Document to compare |
| `gemini_api_key` | String | ❌ | Override API key (optional if set in `.env`) |

**Response:** `application/json`

```jsonc
{
  "comparison_id": "uuid",
  "file1_name": "original.pdf",
  "file2_name": "updated.pdf",
  "overall_summary": "AI-generated change summary...",
  "similarity_percentage": 85.5,
  "text_diffs": [...],        // Paragraph-level differences
  "table_diffs": [...],       // Cell-level table differences
  "image_diffs": [...],       // Image change descriptions
  "bullet_diffs": [...],      // Bullet point differences
  "page_count_a": 3,
  "page_count_b": 3,
  "page_renders_a": [...],    // Base64 PNG page images (Doc A)
  "page_renders_b": [...],    // Base64 PNG page images (Doc B)
  "diff_overlay_a": [...],    // Base64 PNG with red highlights (Doc A)
  "diff_overlay_b": [...],    // Base64 PNG with green highlights (Doc B)
  "stats": {
    "total_text_diffs": 12,
    "total_table_diffs": 2,
    "total_image_diffs": 1,
    "doc_a_is_scanned": false,
    "doc_b_is_scanned": false
  }
}
```

### `GET /health`

Health check endpoint.

---

## 🎨 UI Features

- **Dark theme** with CSS custom properties design system
- **Drag-and-drop** file upload with visual feedback
- **Real-time progress** bar during comparison
- **Tabbed interface** — Side-by-Side / Summary / Paragraphs / Bullets / Tables / Images
- **Diff highlighting** with red (removed) and green (added) indicators
- **Scanned PDF detection** with automatic OCR warnings
- **Responsive design** that works on desktop and tablet screens

---

## 🔧 Environment Variables

| Variable | Required | Default | Description |
|:---|:---|:---|:---|
| `GEMINI_API_KEY` | ✅ | — | Google Gemini API key |
| `GEMINI_MODEL` | ❌ | `gemini-3.1-flash-lite-preview` | Gemini model to use |

---

## 📝 License

MIT

---

<p align="center">
  Built with ❤️ using <strong>FastAPI</strong> + <strong>Next.js</strong> + <strong>Google Gemini AI</strong>
</p>
