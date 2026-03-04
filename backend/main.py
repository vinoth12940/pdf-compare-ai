import os
import sys
import uuid
import tempfile
import logging
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse

from models.schemas import ComparisonResult
from services.pdf_extractor import PDFExtractor
from services.gemini_service import GeminiService
from services.comparator import Comparator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="GenAI PDF Comparison API",
    description="Compare PDF documents using AI — handles images, tables, bullets, paragraphs",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

extractor = PDFExtractor()


@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html><body>
      <h1>GenAI PDF Comparison API</h1>
      <p><a href="/docs">📄 API Docs (Swagger)</a></p>
      <p>POST /compare — Upload two PDFs to compare</p>
    </body></html>
    """


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "ocr_available": extractor.ocr_available,
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
    }


@app.post("/compare", response_model=ComparisonResult)
async def compare_pdfs(
    file1: UploadFile = File(..., description="First PDF file"),
    file2: UploadFile = File(..., description="Second PDF file"),
    gemini_api_key: str = Form(default="", description="Optional Gemini API key (overrides env variable)"),
):
    """
    Compare two PDF documents. Returns structured diff for all content types:
    paragraphs, tables, bullet points, headings, and images.
    """
    # Validate file types
    for f in [file1, file2]:
        if not f.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"'{f.filename}' is not a PDF file.")

    # Write uploads to temp files
    tmp_paths = []
    try:
        for upload in [file1, file2]:
            suffix = f"_{upload.filename}"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                contents = await upload.read()
                if len(contents) == 0:
                    raise HTTPException(status_code=400, detail=f"'{upload.filename}' is empty.")
                tmp.write(contents)
                tmp_paths.append(tmp.name)

        path_a, path_b = tmp_paths[0], tmp_paths[1]

        logger.info(f"Extracting: {file1.filename}")
        data_a = extractor.extract_all(path_a)

        logger.info(f"Extracting: {file2.filename}")
        data_b = extractor.extract_all(path_b)

        logger.info("Rendering pages for Gemini Vision...")
        renders_a = extractor.get_page_renders(path_a, dpi=120)
        renders_b = extractor.get_page_renders(path_b, dpi=120)

        # Init Gemini (API key from form or env)
        api_key = gemini_api_key.strip() or os.getenv("GEMINI_API_KEY", "")
        gemini = GeminiService(api_key=api_key if api_key else None)
        comparator = Comparator(gemini=gemini)

        logger.info("Running AI comparison...")
        result = comparator.compare(
            data_a=data_a,
            data_b=data_b,
            file1_name=file1.filename,
            file2_name=file2.filename,
            page_renders_a=renders_a,
            page_renders_b=renders_b,
        )

        # Include page renders for side-by-side view
        result.page_renders_a = renders_a
        result.page_renders_b = renders_b

        # Generate diff overlays with highlighted changes
        logger.info("Generating diff overlay highlights...")
        overlay_a, overlay_b = extractor.generate_diff_overlays(renders_a, renders_b)
        result.diff_overlay_a = overlay_a
        result.diff_overlay_b = overlay_b

        return result

    finally:
        for p in tmp_paths:
            try:
                os.unlink(p)
            except Exception:
                pass


@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
