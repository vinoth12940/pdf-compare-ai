# Workflow and Processing Notes

> End-to-end explanation of how PDF Compare AI processes two uploaded PDFs, where deterministic comparison is used, where OCR is used, and where Gemini is used.

---

## Why the LLM Exists

The LLM is **not** the primary comparison engine.

The primary comparison engine is deterministic:

- `pdfplumber` and `pypdf` extract structure and content
- `pytesseract` is used only for scanned PDFs
- `difflib` and geometry-based matching drive the actual text/table/image pairing
- `numpy` and page renders are used for pixel overlay diffs

Gemini is used on top of that deterministic pipeline for:

1. **Overall summary generation**
2. **Page-by-page visual explanation**
3. **Semantic image comparison and image description**

If Gemini is unavailable, the app still produces structured diffs, similarity scores, page renders, and overlay highlights. The main loss is AI-written explanations.

---

## High-Level Flow

```text
Frontend upload
  -> FastAPI /compare
  -> save both PDFs to temp files
  -> extract content from PDF A
  -> extract content from PDF B
  -> render pages to PNG
  -> deterministic comparison
  -> optional Gemini analysis
  -> visual overlay generation
  -> ComparisonResult JSON
  -> frontend renders tabs + side-by-side view
```

---

## Step 1: Upload

Frontend entry point:

- `frontend/lib/api.ts`
- `comparePDFs()`

What happens:

1. User selects or drops two files.
2. Frontend sends `multipart/form-data` to `POST /compare`.
3. Optional Gemini API key can be supplied per request.

Backend entry point:

- `backend/main.py`
- `compare_pdfs()`

What happens:

1. Backend validates that both files end with `.pdf`
2. Files are written to temporary files on disk
3. Those temp files are passed into the extraction pipeline

---

## Step 2: PDF Extraction

Main module:

- `backend/services/pdf_extractor.py`
- `PDFExtractor.extract_all()`

This module is responsible for extracting all machine-readable content from each PDF.

### 2.1 Metadata

Library:

- `pypdf`

Used for:

- page count
- title
- author
- subject
- creator

### 2.2 Native Text Extraction

Library:

- `pdfplumber`

Used for:

- reading positioned words from each page
- grouping words into lines
- preserving layout hints such as `x0`, `x1`, `top`, `bottom`, `font size`

Important internal helpers:

- `_extract_page_lines()`
- `_classify_lines()`
- `is_heading()`
- `is_bullet_line()`

The extractor converts page lines into:

- `paragraphs`
- `headings`
- `bullets`

Each extracted block carries geometry and layout metadata such as:

- page number
- x/y coordinates
- font size
- bold/italic flags
- indentation
- previous vertical gap
- page width and page height

That metadata is later used for matching and for viewer highlight regions.

### 2.3 Table Extraction

Library:

- `pdfplumber.find_tables()`

Used for:

- table cell extraction
- table headers and rows
- table bounding boxes on the page

Important detail:

Table areas are removed from normal paragraph extraction so table text does not get double-counted as paragraph content.

### 2.4 Image Extraction

Libraries:

- `pdfplumber`
- `pypdf`
- `Pillow`

Used for:

- extracting embedded image streams
- converting raw PDF image bytes into PNG
- collecting exact image placement boxes from the page

Current behavior:

1. `pdfplumber` is used first to find placed images and their page coordinates.
2. The underlying image stream is decoded into PNG base64.
3. Placement metadata is stored so the viewer can highlight where the image changed.

Important detail:

Page renders are **not** treated as embedded images. They are separate viewer assets.

### 2.5 Page Rendering

Libraries:

- `pdf2image`
- `pypdfium2` fallback

Used for:

- viewer page images
- Gemini visual analysis
- pixel-level diff overlays

Behavior:

1. Try `pdf2image`
2. If Poppler is unavailable, fall back to `pypdfium2`

This keeps rendering working both locally and in environments where Poppler is missing.

---

## Step 3: OCR for Scanned PDFs

Main functions:

- `_run_ocr()`
- `_extract_ocr_lines()`

Libraries:

- `pytesseract`
- Tesseract binary inside Docker

OCR is used only when the PDF appears to be scanned or image-only.

Detection rule:

- if native extracted text is too small relative to page count, the extractor marks the PDF as scanned and switches to OCR

How OCR works:

1. Each page is rendered to an image
2. Tesseract `image_to_data()` is used instead of plain `image_to_string()`
3. OCR output is grouped into line blocks
4. Each OCR line gets geometry:
   - `x0`, `x1`, `top`, `bottom`
   - estimated font height
   - page width and page height
5. Those OCR lines are passed into the **same** `_classify_lines()` function used by native PDF text extraction

Why that matters:

- OCR output becomes paragraphs, headings, and bullets in the same format as native PDF text
- downstream comparison code does not need a separate OCR-specific path

---

## Step 4: Deterministic Comparison

Main module:

- `backend/services/comparator.py`
- `Comparator.compare()`

This is the core comparison engine.

### 4.1 Text Comparison

Functions:

- `compare_text_blocks()`
- `_match_items()`

Used for:

- paragraph comparison
- heading comparison
- bullet comparison

How it works:

1. Text from document A is matched against text from document B
2. Matching uses normalized text similarity plus page proximity
3. `difflib.SequenceMatcher` calculates similarity
4. Style and layout changes reduce the effective similarity score
5. Each match is classified as:
   - `unchanged`
   - `changed`
   - `added`
   - `removed`

Result objects:

- `TextDiff`

These diffs include:

- content from A and B
- similarity score
- section type
- style/layout changes
- viewer bounding boxes

### 4.2 Table Comparison

Function:

- `compare_tables()`

How it works:

1. Tables are matched using headers and a table signature
2. Rows are aligned using `difflib.SequenceMatcher`
3. Changed, inserted, and deleted rows are converted into `TableCellDiff`
4. Overall table diff becomes `TableDiff`

### 4.3 Image Comparison

Function:

- `compare_images()`

How it works:

1. Images are grouped by page
2. Images are matched using placement overlap, placement size, source size, and center position
3. When Gemini is available, paired images are sent for semantic comparison
4. Geometry from the placed image is attached to the final diff object

Result object:

- `ImageDiff`

### 4.4 Page Alignment for the Viewer

Function:

- `align_pages()`

Why it exists:

- page `n` in document A may not always correspond to page `n` in document B

How it works:

1. Build page-level text signatures
2. Use dynamic-programming alignment with match/insert/delete costs
3. Return `PagePair` objects

The side-by-side viewer uses these page pairs instead of assuming simple page-number equality.

### 4.5 Viewer Regions

Function:

- `build_viewer_regions()`

Purpose:

- convert text/table/image diffs into exact viewer highlight boxes

Sources:

- text block bounding boxes
- table bounding boxes
- image placement boxes

Result object:

- `ViewerRegion`

This is what allows the side-by-side UI to draw precise boxes instead of just highlighting the whole page.

---

## Step 5: LLM and AI Layer

Main module:

- `backend/services/gemini_service.py`

Gemini is optional and layered on top of the deterministic pipeline.

### 5.1 Overall Summary

Function:

- `generate_overall_summary()`

Inputs:

- extracted text excerpts from both documents
- a small number of page renders

Output:

- human-readable executive summary

### 5.2 Page-by-Page Visual Explanation

Function:

- `compare_pages_sequentially()`

Inputs:

- page renders from both PDFs

Output:

- ordered `PageDiff` items describing page-level changes from top to bottom

### 5.3 Image Description and Image Comparison

Functions:

- `describe_image()`
- `compare_images()`

Inputs:

- paired embedded image PNGs

Outputs:

- image-level explanation
- whether two images appear the same

### Important Note

The LLM does **not** decide the full document diff structure.

It explains and summarizes.

The structured comparison objects come primarily from the deterministic extractor and comparator.

---

## Step 6: Visual Overlay Generation

Function:

- `generate_diff_overlays()`

Libraries:

- `numpy`
- `Pillow`

How it works:

1. Page renders are converted to grayscale masks
2. Minor render shifts are aligned
3. XOR diff masks are computed
4. Noise is cleaned up
5. Red overlay is generated for document A
6. Green overlay is generated for document B

These overlays are useful for visual review, but they are not the only viewer signal anymore. Structured viewer regions are more precise for block-level differences.

---

## Step 7: Final Result Object

Main schema:

- `backend/models/schemas.py`
- `ComparisonResult`

The final response contains:

- `comparison_id`
- `file1_name`
- `file2_name`
- `overall_summary`
- `similarity_percentage`
- `text_diffs`
- `bullet_diffs`
- `table_diffs`
- `image_diffs`
- `ai_page_diffs`
- `page_pairs`
- `viewer_regions`
- `page_renders_a`
- `page_renders_b`
- `diff_overlay_a`
- `diff_overlay_b`
- `stats`

This JSON is returned by FastAPI and rendered by the frontend.

---

## Frontend Usage of the Result

Main UI file:

- `frontend/app/page.tsx`

How the frontend uses the backend result:

1. Summary tab shows `overall_summary`
2. Paragraph/Bullet/Table/Image tabs show structured diffs
3. AI Analysis tab shows `ai_page_diffs`
4. Side-by-side viewer uses:
   - `page_pairs`
   - `viewer_regions`
   - `page_renders_a`
   - `page_renders_b`
   - `diff_overlay_a`
   - `diff_overlay_b`

The viewer can switch between:

- region-based highlights
- pixel overlay highlights
- clean page view

---

## Module Summary

| Module | Responsibility |
|:---|:---|
| `backend/main.py` | Request orchestration and response assembly |
| `backend/services/pdf_extractor.py` | Native extraction, OCR, page rendering, overlay generation |
| `backend/services/comparator.py` | Deterministic diff logic and similarity calculation |
| `backend/services/gemini_service.py` | Optional Gemini summary and visual explanation |
| `backend/models/schemas.py` | Response models and diff object shapes |
| `frontend/lib/api.ts` | Upload and API client |
| `frontend/app/page.tsx` | Result rendering and side-by-side viewer |

---

## Practical Summary

The system works in this order:

1. Extract as much structure as possible directly from the PDFs
2. Fall back to OCR only when necessary
3. Build deterministic text/table/image/page matches
4. Generate exact highlight regions for the viewer
5. Use Gemini to explain and summarize what the deterministic system found
6. Return one structured response that the frontend can render in multiple views

That is why the app can still function without the LLM, but the LLM makes the results easier for humans to review.
