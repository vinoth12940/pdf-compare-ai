# GenAI PDF Comparison Tool 🤖📄

AI-powered PDF comparison that detects differences in **images, tables, bullet points, paragraphs, headings**, and scanned PDFs — powered by **Google Gemini 1.5 Pro**.

## ✨ Features

| Content Type     | Detection        | AI Analysis       |
| ---------------- | ---------------- | ----------------- |
| 📝 Paragraphs   | ✅               | ✅ Semantic diff  |
| 🔢 Tables       | ✅ Cell-level    | ✅ Summary        |
| • Bullet Points  | ✅               | ✅ Item diff      |
| 🖼️ Images       | ✅ Embedded      | ✅ Vision desc    |
| 📋 Headings     | ✅               | ✅                |
| 🔍 Scanned PDFs | ✅ OCR           | ✅                |

---

## 🐳 Run with Docker (Recommended)

### 1. Set your Gemini API key

```bash
# Edit backend/.env
GEMINI_API_KEY=your_key_here
```

Get a free key at [aistudio.google.com](https://aistudio.google.com)

### 2. Build & start

```bash
docker compose up --build
```

- **Frontend**: <http://localhost:3000>
- **Backend API**: <http://localhost:8000>
- **Swagger Docs**: <http://localhost:8000/docs>

### 3. Stop

```bash
docker compose down
```

---

## 🖥️ Run Locally (without Docker)

### Prerequisites

```bash
brew install poppler tesseract   # macOS
python3 --version                 # 3.11+
node --version                    # 18+
```

### Backend

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # add your GEMINI_API_KEY
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
PDF Comparison/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── main.py                  # FastAPI app
│   ├── requirements.txt
│   ├── models/schemas.py        # Pydantic models
│   └── services/
│       ├── pdf_extractor.py     # Text/table/image/OCR extraction
│       ├── gemini_service.py    # Gemini Vision AI
│       └── comparator.py       # Diff engine
└── frontend/
    ├── Dockerfile
    ├── app/
    │   ├── page.tsx             # Main UI
    │   ├── layout.tsx
    │   └── globals.css
    └── lib/api.ts               # API client
```

## 📊 How It Works

1. **Extract** — `pdfplumber` parses text, tables, and structure; detects bullets
2. **OCR** — `pytesseract` handles scanned/image-only PDFs
3. **Images** — `pypdf` extracts embedded images; `pdf2image` renders pages
4. **Compare** — `difflib` for text similarity + **Gemini Vision** for semantic/visual AI analysis
5. **Report** — Side-by-side diff UI with AI summary and HTML export
