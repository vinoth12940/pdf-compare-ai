# API Reference — PDF Compare AI

> Base URL: `http://localhost:8000`
> Interactive docs: `http://localhost:8000/docs` (Swagger UI)

---

## Endpoints

| Method | Path | Description |
|:---|:---|:---|
| `POST` | `/compare` | Compare two PDF documents |
| `GET` | `/health` | Health check |
| `GET` | `/` | Welcome page (HTML) |

---

## POST /compare

Upload two PDF files and receive a structured AI-powered comparison.

### Request

**Content-Type:** `multipart/form-data`

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `file1` | `File` | ✅ | First PDF document |
| `file2` | `File` | ✅ | Second PDF document |
| `gemini_api_key` | `string` | ❌ | Gemini API key (overrides `.env` value) |

### Response

**Status:** `200 OK`
**Content-Type:** `application/json`

#### Top-Level Fields

| Field | Type | Description |
|:---|:---|:---|
| `comparison_id` | `string` | Unique UUID for this comparison |
| `file1_name` | `string` | Original filename of first PDF |
| `file2_name` | `string` | Original filename of second PDF |
| `overall_summary` | `string` | AI-generated executive summary of changes |
| `similarity_percentage` | `float` | Weighted average similarity (0–100) |
| `text_diffs` | `TextDiff[]` | Paragraph and heading differences |
| `table_diffs` | `TableDiff[]` | Table-level differences |
| `image_diffs` | `ImageDiff[]` | Image-level differences |
| `bullet_diffs` | `TextDiff[]` | Bullet point differences |
| `page_count_a` | `int` | Number of pages in Document A |
| `page_count_b` | `int` | Number of pages in Document B |
| `page_renders_a` | `string[] \| null` | Base64 PNG renders of Document A pages |
| `page_renders_b` | `string[] \| null` | Base64 PNG renders of Document B pages |
| `diff_overlay_a` | `string[] \| null` | Base64 PNG with red diff highlights (Doc A) |
| `diff_overlay_b` | `string[] \| null` | Base64 PNG with green diff highlights (Doc B) |
| `stats` | `Stats` | Aggregate change counts |

#### TextDiff

| Field | Type | Description |
|:---|:---|:---|
| `page` | `int` | Page number where the text appears |
| `content_a` | `string` | Text content from Document A |
| `content_b` | `string` | Text content from Document B |
| `diff_type` | `DiffType` | `"added"`, `"removed"`, `"changed"`, or `"unchanged"` |
| `similarity_score` | `float` | Similarity between content_a and content_b (0.0–1.0) |
| `section_type` | `string` | `"paragraph"`, `"heading"`, or `"bullet"` |

#### TableDiff

| Field | Type | Description |
|:---|:---|:---|
| `page` | `int` | Page number where the table appears |
| `table_index` | `int` | Index of the table on the page |
| `headers_a` | `string[] \| null` | Column headers from Document A |
| `headers_b` | `string[] \| null` | Column headers from Document B |
| `cell_diffs` | `TableCellDiff[]` | Individual cell-level differences |
| `rows_added` | `int` | Number of rows added in Document B |
| `rows_removed` | `int` | Number of rows removed from Document A |
| `diff_type` | `DiffType` | Overall table diff classification |

#### TableCellDiff

| Field | Type | Description |
|:---|:---|:---|
| `row` | `int` | Row index (0-based) |
| `col` | `int` | Column index (0-based) |
| `value_a` | `string \| null` | Cell value from Document A |
| `value_b` | `string \| null` | Cell value from Document B |
| `diff_type` | `DiffType` | `"added"`, `"removed"`, or `"changed"` |

#### ImageDiff

| Field | Type | Description |
|:---|:---|:---|
| `page` | `int` | Page number where the image appears |
| `image_index` | `int` | Index of the image on the page |
| `description_a` | `string \| null` | AI description of image from Document A |
| `description_b` | `string \| null` | AI description of image from Document B |
| `diff_type` | `DiffType` | `"added"`, `"removed"`, `"changed"`, or `"unchanged"` |
| `ai_analysis` | `string` | AI comparison analysis of the image pair |

#### Stats

| Field | Type | Description |
|:---|:---|:---|
| `paragraphs_changed` | `int` | Paragraphs with modifications |
| `paragraphs_added` | `int` | Paragraphs only in Document B |
| `paragraphs_removed` | `int` | Paragraphs only in Document A |
| `bullets_changed` | `int` | Bullet points with modifications |
| `bullets_added` | `int` | Bullet points only in Document B |
| `bullets_removed` | `int` | Bullet points only in Document A |
| `tables_changed` | `int` | Tables with any cell differences |
| `images_changed` | `int` | Images with visual differences |
| `images_added` | `int` | Images only in Document B |
| `images_removed` | `int` | Images only in Document A |
| `doc_a_is_scanned` | `bool` | Whether Document A required OCR |
| `doc_b_is_scanned` | `bool` | Whether Document B required OCR |

#### DiffType Enum

```
"added"     — Present in Document B but not A
"removed"   — Present in Document A but not B
"changed"   — Present in both but different
"unchanged" — Identical in both documents
```

### Example Request

```bash
curl -X POST http://localhost:8000/compare \
  -F "file1=@document_v1.pdf" \
  -F "file2=@document_v2.pdf" \
  -F "gemini_api_key=AIza..."
```

### Example Response

```json
{
  "comparison_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "file1_name": "document_v1.pdf",
  "file2_name": "document_v2.pdf",
  "overall_summary": "Both documents are quarterly reports. Document B includes updated revenue figures and an additional section on market outlook...",
  "similarity_percentage": 87.3,
  "text_diffs": [
    {
      "page": 1,
      "content_a": "Revenue: $1.2M",
      "content_b": "Revenue: $1.5M",
      "diff_type": "changed",
      "similarity_score": 0.85,
      "section_type": "paragraph"
    }
  ],
  "table_diffs": [],
  "image_diffs": [
    {
      "page": 2,
      "image_index": 0,
      "description_a": "Bar chart showing Q1 product sales",
      "description_b": "Bar chart showing Q1 and Q2 product sales",
      "diff_type": "changed",
      "ai_analysis": "Document B chart includes an additional Q2 data series with higher overall values."
    }
  ],
  "bullet_diffs": [],
  "page_count_a": 3,
  "page_count_b": 4,
  "page_renders_a": ["iVBORw0KGgo..."],
  "page_renders_b": ["iVBORw0KGgo..."],
  "diff_overlay_a": ["iVBORw0KGgo..."],
  "diff_overlay_b": ["iVBORw0KGgo..."],
  "stats": {
    "paragraphs_changed": 3,
    "paragraphs_added": 1,
    "paragraphs_removed": 0,
    "bullets_changed": 0,
    "bullets_added": 0,
    "bullets_removed": 0,
    "tables_changed": 0,
    "images_changed": 1,
    "images_added": 0,
    "images_removed": 0,
    "doc_a_is_scanned": false,
    "doc_b_is_scanned": false
  }
}
```

### Error Responses

| Status | Condition | Body |
|:---|:---|:---|
| `400` | File is not a PDF | `{"detail": "'file.txt' is not a PDF file."}` |
| `400` | File is empty | `{"detail": "'file.pdf' is empty."}` |
| `500` | Gemini API failure or processing error | `{"detail": "Internal server error: ..."}` |

---

## GET /health

Returns the health status of the backend service.

### Response

**Status:** `200 OK`

```json
{
  "status": "ok",
  "ocr_available": true,
  "gemini_configured": true
}
```

| Field | Type | Description |
|:---|:---|:---|
| `status` | `string` | Always `"ok"` if the server is running |
| `ocr_available` | `bool` | Whether Tesseract OCR is installed |
| `gemini_configured` | `bool` | Whether `GEMINI_API_KEY` is set in the environment |

---

## GET /

Welcome page. Returns simple HTML with a link to the Swagger docs.

**Status:** `200 OK`
**Content-Type:** `text/html`

---

## Rate Limits & Timeouts

- No server-side rate limits are enforced
- The frontend client uses a **5-minute timeout** (`300000ms`) for the `/compare` request
- Gemini API has its own rate limits — see [Google AI pricing](https://ai.google.dev/pricing)
- Large PDFs (50+ pages) may take 1–2 minutes to process

---

## Authentication

The API does not require authentication. The optional `gemini_api_key` parameter allows users to provide their own Google Gemini API key per request. If omitted, the server uses the key from the `GEMINI_API_KEY` environment variable.
