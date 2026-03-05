# Architecture — PDF Compare AI

> System design, data flow, and architectural decisions.

---

## System Overview

PDF Compare AI is a two-service application that uses AI-augmented document analysis to detect differences between PDF files.

```
┌─────────────────────────────────────────────────────────────┐
│                        User Browser                         │
│                     http://localhost:3000                    │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP (Axios)
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                   Next.js Frontend (Port 3000)               │
│                                                              │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │ Upload View │  │ Results View │  │ Report Generator     │ │
│  │ (dropzone)  │  │ (tabbed UI)  │  │ (HTML export)        │ │
│  └────────────┘  └──────────────┘  └──────────────────────┘ │
│                                                              │
│  lib/api.ts — typed HTTP client                              │
└──────────────────────────┬───────────────────────────────────┘
                           │ POST /compare (multipart/form-data)
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                   FastAPI Backend (Port 8000)                 │
│                                                              │
│  main.py                                                     │
│    ├── POST /compare — orchestrates full pipeline            │
│    ├── GET /health   — health check                          │
│    └── GET /         — welcome page                          │
│                                                              │
│  services/                                                   │
│    ├── pdf_extractor.py                                      │
│    │     ├── extract_all()   — text, tables, bullets, images │
│    │     ├── get_page_renders()  — page → base64 PNG         │
│    │     ├── generate_diff_overlays()  — pixel diff          │
│    │     └── _run_ocr()      — Tesseract fallback            │
│    │                                                         │
│    ├── gemini_service.py                                     │
│    │     ├── compare_text_semantically()                     │
│    │     ├── describe_image()                                │
│    │     ├── compare_images()                                │
│    │     ├── generate_overall_summary()                      │
│    │     ├── compare_table_semantically()                    │
│    │     └── compare_pages_sequentially()                    │
│    │                                                         │
│    └── comparator.py                                         │
│          ├── compare_text_blocks()  → (diffs, total, scores) │
│          ├── compare_tables()       → TableDiff[]            │
│          ├── compare_images()       → ImageDiff[]            │
│          └── compare()              → ComparisonResult (+ai_page_diffs) │
│                                                              │
│  models/schemas.py — Pydantic models                         │
│    ComparisonResult, TextDiff(position), PageDiff,           │
│    TableDiff, TableCellDiff, ImageDiff, DiffType enum        │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │  Google Gemini   │
                  │  AI API          │
                  │  (multimodal)    │
                  └──────────────────┘
```

---

## Data Flow

### 1. Upload Phase

1. User drops two PDF files into the frontend dropzones
2. Frontend sends `POST /compare` with `file1`, `file2`, and optional `gemini_api_key`
3. Backend saves uploads to temporary files

### 2. Extraction Phase

For each PDF, `PDFExtractor.extract_all()` runs:

1. **Text extraction** — `pdfplumber` extracts raw text, split into paragraphs
2. **Heading detection** — heuristic: ALL CAPS, short lines, large font sizes
3. **Bullet detection** — regex patterns (`•`, `–`, `*`, numbered lists)
4. **Table extraction** — `pdfplumber.extract_tables()` with headers + data
5. **Image extraction** — `pypdf` XObject extraction → PIL → PNG base64
6. **Scanned PDF detection** — if text is minimal, falls back to Tesseract OCR
7. **Page rendering** — `pdf2image` renders each page at 120 DPI as base64 PNG

### 3. Comparison Phase

`Comparator.compare()` runs:

1. **Text matching** — greedy matching via `_match_items()` with similarity threshold > 0.3
2. **Similarity scoring** — `difflib.SequenceMatcher` per pair
3. **Classification** — UNCHANGED (≥ 95%), CHANGED, ADDED, or REMOVED
4. **Table diff** — cell-by-cell comparison across matched tables
5. **Image diff** — Gemini Vision analyzes page renders side-by-side
6. **Page AI diff** — Gemini compares each page pair top-to-bottom
7. **Overall similarity** — weighted average of all text pair scores

### 4. AI Analysis Phase

`GeminiService` calls Google Gemini API:

1. **Overall summary** — sends text excerpts + up to 2 page renders from each document
2. **Image comparison** — sends paired images for visual diff analysis
3. **Image description** — individual image captioning for added/removed images
4. **Page sequence comparison** — `compare_pages_sequentially()` produces ordered `ai_page_diffs`

### 5. Overlay Generation

`PDFExtractor.generate_diff_overlays()`:

1. Decodes base64 page renders to numpy arrays
2. Binarizes and aligns page masks to reduce render-offset noise
3. Computes XOR diff mask and applies noise cleanup
4. Overlays semi-transparent red (Doc A) / green (Doc B) on changed regions
5. Returns new base64 PNG images with highlights (toggleable in UI)

### 6. Response

Backend returns `ComparisonResult` JSON with all diffs, renders, overlays, and stats.

---

## Architecture Decision Records

### ADR-001: FastAPI + Next.js Split Architecture

**Status:** Accepted

**Context:** The application needs heavy PDF processing (Poppler, Tesseract, numpy) which is Python-native, combined with a rich interactive UI. A monolithic approach would force compromises in either the backend processing or frontend experience.

**Decision:** Split into FastAPI backend (Python) and Next.js frontend (TypeScript), connected via REST API, orchestrated with Docker Compose.

**Consequences:**

- ✅ Best-in-class libraries for both PDF processing and UI
- ✅ Independent scaling and deployment
- ✅ Clean separation of concerns
- ❌ Two containers, slightly more complex deployment
- ❌ Large file uploads must traverse the network boundary

---

### ADR-002: Gemini AI for Multimodal Analysis

**Status:** Accepted

**Context:** Simple text diffing misses semantic meaning and cannot analyze images. We need both text understanding and vision capabilities in a single model.

**Decision:** Use Google Gemini AI (multimodal model) for semantic text comparison, image description, image comparison, and overall summary generation.

**Consequences:**

- ✅ Single model handles text + vision (no separate OCR model for image analysis)
- ✅ High-quality semantic understanding
- ✅ Configurable model name via environment variable
- ❌ Requires API key and internet connection
- ❌ Per-request API cost (mitigated by free tier)
- ❌ Added latency for API calls (~2–10s per comparison)

---

### ADR-003: Weighted Average for Similarity Scoring

**Status:** Accepted

**Context:** The initial similarity calculation only counted changed items vs total items, but since unchanged items were filtered from diff lists, the formula always produced 0%.

**Decision:** `compare_text_blocks()` returns `(diffs, total_pairs, score_sum)` including unchanged pairs. Overall similarity is computed as `(sum_of_all_scores / total_pairs) * 100` — a true weighted average across all matched text pairs.

**Consequences:**

- ✅ Accurate similarity percentage
- ✅ Reflects actual document similarity (e.g., 87% for two payslips from different periods)
- ✅ Accounts for unchanged content that was previously ignored

---

### ADR-004: Pixel-Level Diff Overlays

**Status:** Accepted

**Context:** Users need to visually see where changes occur on each page, not just read text diffs.

**Decision:** Render each page as PNG, align page content masks, compute cleaned XOR differences, and overlay semi-transparent red/green highlights.

**Consequences:**

- ✅ Intuitive visual diff — users immediately see what changed
- ✅ Works for layout, formatting, and image changes (not just text)
- ❌ Page renders add to response size (~100KB per page per document)
- ✅ Alignment + cleanup reduces anti-aliasing false positives
- ❌ Very different page layouts can still produce broad highlighted regions

---

### ADR-005: Product-Grade App Shell UI

**Status:** Accepted

**Context:** The initial centered-card layout looked like a generic web page. The user wanted a product-like experience similar to Linear, Vercel, or Raycast.

**Decision:** Redesigned the frontend with a full-height app shell pattern: top bar, stats sidebar, tabbed toolbar, and scrollable content area. Uses Geist font family and a carefully tuned dark zinc palette.

**Consequences:**

- ✅ Feels like a professional desktop product, not a webpage
- ✅ Stats sidebar provides at-a-glance metrics
- ✅ Tabbed interface allows quick navigation between diff types
- ❌ More complex CSS and component structure
