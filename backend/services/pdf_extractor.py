import pdfplumber
import pypdf
import base64
import re
import io
from typing import List, Dict, Any, Optional, Tuple
from pdf2image import convert_from_path
from PIL import Image
import pytesseract
import logging

logger = logging.getLogger(__name__)


def is_bullet_line(text: str) -> bool:
    """Detect if a line is a bullet point."""
    stripped = text.strip()
    bullet_patterns = [
        r"^[•●○◦▪▸►▻‣⁃]\s",
        r"^[-–—]\s",
        r"^\*\s",
        r"^\d+[.)]\s",
        r"^[a-zA-Z][.)]\s",
        r"^\([a-zA-Z0-9]+\)\s",
    ]
    for pattern in bullet_patterns:
        if re.match(pattern, stripped):
            return True
    return False


def is_heading(text: str, font_sizes: Optional[List[float]] = None) -> bool:
    """Detect if a line looks like a heading."""
    stripped = text.strip()
    if len(stripped) < 3 or len(stripped) > 200:
        return False
    # Short lines without sentence-ending punctuation tend to be headings
    if not stripped.endswith((".", ",", ";", ":", "?", "!")):
        words = stripped.split()
        if 1 < len(words) <= 12:
            return True
    return False


class PDFExtractor:
    def __init__(self):
        self.ocr_available = self._check_tesseract()

    def _check_tesseract(self) -> bool:
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def extract_all(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extract all content types from a PDF.
        Returns dict with: paragraphs, tables, bullets, images, page_count, metadata
        """
        result = {
            "paragraphs": [],
            "tables": [],
            "bullets": [],
            "images": [],
            "headings": [],
            "page_count": 0,
            "metadata": {},
            "is_scanned": False,
        }

        # --- Metadata via pypdf ---
        try:
            reader = pypdf.PdfReader(pdf_path)
            meta = reader.metadata or {}
            result["metadata"] = {
                "title": meta.get("/Title", ""),
                "author": meta.get("/Author", ""),
                "subject": meta.get("/Subject", ""),
                "creator": meta.get("/Creator", ""),
            }
            result["page_count"] = len(reader.pages)
        except Exception as e:
            logger.warning(f"pypdf metadata extraction failed: {e}")

        # --- Main extraction via pdfplumber ---
        try:
            with pdfplumber.open(pdf_path) as pdf:
                result["page_count"] = len(pdf.pages)
                total_text_chars = 0

                for page_num, page in enumerate(pdf.pages, 1):
                    # Try text extraction
                    raw_text = page.extract_text() or ""
                    total_text_chars += len(raw_text.strip())

                    # Tables
                    tables = page.extract_tables()
                    for tbl_idx, table in enumerate(tables):
                        if table:
                            result["tables"].append({
                                "page": page_num,
                                "table_index": tbl_idx,
                                "data": table,
                                "headers": table[0] if table else [],
                                "rows": table[1:] if len(table) > 1 else [],
                            })

                    # Text classification
                    if raw_text.strip():
                        lines = raw_text.split("\n")
                        current_paragraph_lines = []

                        for line in lines:
                            stripped = line.strip()
                            if not stripped:
                                # Flush current paragraph
                                if current_paragraph_lines:
                                    para_text = " ".join(current_paragraph_lines)
                                    result["paragraphs"].append({
                                        "page": page_num,
                                        "text": para_text,
                                    })
                                    current_paragraph_lines = []
                                continue

                            if is_bullet_line(stripped):
                                # Flush paragraph buffer first
                                if current_paragraph_lines:
                                    para_text = " ".join(current_paragraph_lines)
                                    result["paragraphs"].append({
                                        "page": page_num,
                                        "text": para_text,
                                    })
                                    current_paragraph_lines = []
                                result["bullets"].append({
                                    "page": page_num,
                                    "text": stripped,
                                })
                            elif is_heading(stripped):
                                if current_paragraph_lines:
                                    para_text = " ".join(current_paragraph_lines)
                                    result["paragraphs"].append({
                                        "page": page_num,
                                        "text": para_text,
                                    })
                                    current_paragraph_lines = []
                                result["headings"].append({
                                    "page": page_num,
                                    "text": stripped,
                                })
                            else:
                                current_paragraph_lines.append(stripped)

                        # Flush remaining paragraph
                        if current_paragraph_lines:
                            para_text = " ".join(current_paragraph_lines)
                            result["paragraphs"].append({
                                "page": page_num,
                                "text": para_text,
                            })

                # If very little text extracted → likely scanned
                if total_text_chars < 50 * result["page_count"] and self.ocr_available:
                    result["is_scanned"] = True
                    result = self._run_ocr(pdf_path, result)

        except Exception as e:
            logger.error(f"pdfplumber extraction failed: {e}")
            if self.ocr_available:
                result["is_scanned"] = True
                result = self._run_ocr(pdf_path, result)

        # --- Image extraction ---
        result["images"] = self._extract_images(pdf_path)

        return result

    def _run_ocr(self, pdf_path: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """Run OCR on scanned/image-only PDFs."""
        try:
            images = convert_from_path(pdf_path, dpi=200)
            result["page_count"] = len(images)

            for page_num, img in enumerate(images, 1):
                ocr_text = pytesseract.image_to_string(img)
                lines = ocr_text.split("\n")
                para_lines = []

                for line in lines:
                    stripped = line.strip()
                    if not stripped:
                        if para_lines:
                            result["paragraphs"].append({
                                "page": page_num,
                                "text": " ".join(para_lines),
                                "ocr": True,
                            })
                            para_lines = []
                        continue

                    if is_bullet_line(stripped):
                        if para_lines:
                            result["paragraphs"].append({
                                "page": page_num,
                                "text": " ".join(para_lines),
                                "ocr": True,
                            })
                            para_lines = []
                        result["bullets"].append({"page": page_num, "text": stripped, "ocr": True})
                    elif is_heading(stripped):
                        if para_lines:
                            result["paragraphs"].append({
                                "page": page_num,
                                "text": " ".join(para_lines),
                                "ocr": True,
                            })
                            para_lines = []
                        result["headings"].append({"page": page_num, "text": stripped, "ocr": True})
                    else:
                        para_lines.append(stripped)

                if para_lines:
                    result["paragraphs"].append({
                        "page": page_num,
                        "text": " ".join(para_lines),
                        "ocr": True,
                    })

        except Exception as e:
            logger.error(f"OCR failed: {e}")

        return result

    def _pdf_image_to_png_b64(self, xobject, width: int, height: int) -> Optional[str]:
        """Convert a raw PDF XObject image to valid PNG base64.
        
        PDF images store raw byte streams (JPEG, raw RGB, CMYK, etc.)
        that are NOT valid PNG/JPEG files on their own. This method
        decodes them into PIL Images and re-encodes as PNG.
        """
        try:
            data = xobject.get_data()
            color_space = str(xobject.get("/ColorSpace", "/DeviceRGB"))
            bits_per_component = int(xobject.get("/BitsPerComponent", 8))
            filt = xobject.get("/Filter", "")

            # If it's DCTDecode (JPEG), the data IS valid JPEG
            if "/DCTDecode" in str(filt):
                img = Image.open(io.BytesIO(data))
            elif "/FlateDecode" in str(filt) or not filt:
                # Raw pixel data — need to reconstruct the image
                if "CMYK" in color_space:
                    mode = "CMYK"
                    expected_size = width * height * 4
                elif "Gray" in color_space:
                    mode = "L"
                    expected_size = width * height
                else:
                    mode = "RGB"
                    expected_size = width * height * 3

                if len(data) >= expected_size:
                    img = Image.frombytes(mode, (width, height), data[:expected_size])
                else:
                    return None
            else:
                # Other filters (JPXDecode, CCITTFax, etc.) — try generic PIL open
                try:
                    img = Image.open(io.BytesIO(data))
                except Exception:
                    return None

            # Convert to RGB if needed
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode("utf-8")

        except Exception as e:
            logger.debug(f"Image conversion failed: {e}")
            return None

    @staticmethod
    def generate_diff_overlays(
        renders_a: List[str], renders_b: List[str]
    ) -> Tuple[List[str], List[str]]:
        """Generate diff‐highlighted page overlays using pixel comparison.
        
        Returns two lists of base64 PNGs — one for each document —
        with changed regions highlighted in semi‐transparent red/green.
        """
        import numpy as np

        overlays_a: List[str] = []
        overlays_b: List[str] = []
        max_pages = max(len(renders_a), len(renders_b))

        for i in range(max_pages):
            b64_a = renders_a[i] if i < len(renders_a) else None
            b64_b = renders_b[i] if i < len(renders_b) else None

            if b64_a and b64_b:
                img_a = Image.open(io.BytesIO(base64.b64decode(b64_a))).convert("RGB")
                img_b = Image.open(io.BytesIO(base64.b64decode(b64_b))).convert("RGB")

                # Resize to same dimensions for pixel comparison
                target_w = max(img_a.width, img_b.width)
                target_h = max(img_a.height, img_b.height)
                img_a = img_a.resize((target_w, target_h), Image.LANCZOS)
                img_b = img_b.resize((target_w, target_h), Image.LANCZOS)

                arr_a = np.array(img_a, dtype=np.int16)
                arr_b = np.array(img_b, dtype=np.int16)

                # Compute per-pixel difference (absolute across channels)
                diff = np.abs(arr_a - arr_b).sum(axis=2)  # shape (H, W)
                threshold = 30  # ignore tiny anti-aliasing or compression noise
                changed_mask = diff > threshold

                # Block-based highlighting (8x8 blocks) — smoother overlay
                block = 8
                h, w = changed_mask.shape
                for by in range(0, h, block):
                    for bx in range(0, w, block):
                        region = changed_mask[by:by + block, bx:bx + block]
                        if region.mean() > 0.15:
                            changed_mask[by:by + block, bx:bx + block] = True

                # Create overlay for A (red = removed/changed)
                overlay_a = img_a.copy().convert("RGBA")
                red_layer = Image.new("RGBA", overlay_a.size, (0, 0, 0, 0))
                red_arr = np.array(red_layer)
                red_arr[changed_mask] = [255, 60, 60, 80]  # semi-transparent red
                red_layer = Image.fromarray(red_arr)
                overlay_a = Image.alpha_composite(overlay_a, red_layer)

                # Create overlay for B (green = added/changed)
                overlay_b = img_b.copy().convert("RGBA")
                green_layer = Image.new("RGBA", overlay_b.size, (0, 0, 0, 0))
                green_arr = np.array(green_layer)
                green_arr[changed_mask] = [60, 200, 60, 80]  # semi-transparent green
                green_layer = Image.fromarray(green_arr)
                overlay_b = Image.alpha_composite(overlay_b, green_layer)

                # Encode back to base64 PNG
                buf_a = io.BytesIO()
                overlay_a.save(buf_a, format="PNG")
                overlays_a.append(base64.b64encode(buf_a.getvalue()).decode("utf-8"))

                buf_b = io.BytesIO()
                overlay_b.save(buf_b, format="PNG")
                overlays_b.append(base64.b64encode(buf_b.getvalue()).decode("utf-8"))

            elif b64_a:
                overlays_a.append(b64_a)
                overlays_b.append("")
            elif b64_b:
                overlays_a.append("")
                overlays_b.append(b64_b)

        return overlays_a, overlays_b


    def _extract_images(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Extract images from PDF as valid base64 PNG strings."""
        images = []
        try:
            reader = pypdf.PdfReader(pdf_path)
            for page_num, page in enumerate(reader.pages, 1):
                if "/Resources" in page and "/XObject" in page.get("/Resources", {}):
                    xobjects = page["/Resources"]["/XObject"]
                    if xobjects:
                        for obj_name, obj in xobjects.items():
                            try:
                                if hasattr(obj, "get") and obj.get("/Subtype") == "/Image":
                                    width = int(obj.get("/Width", 0))
                                    height = int(obj.get("/Height", 0))
                                    if width <= 20 or height <= 20:
                                        continue

                                    # Try to convert raw PDF image data to valid PNG
                                    b64 = self._pdf_image_to_png_b64(obj, width, height)
                                    if b64:
                                        images.append({
                                            "page": page_num,
                                            "width": width,
                                            "height": height,
                                            "data_b64": b64,
                                            "color_space": "RGB",
                                        })
                            except Exception as ex:
                                logger.debug(f"Skip image {obj_name} on page {page_num}: {ex}")
        except Exception as e:
            logger.warning(f"Image extraction failed: {e}")

        # Fallback: use pdf2image to render full pages if no embedded images found
        if not images:
            try:
                page_images = convert_from_path(pdf_path, dpi=150, fmt="png")
                for i, img in enumerate(page_images, 1):
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    images.append({
                        "page": i,
                        "width": img.width,
                        "height": img.height,
                        "data_b64": b64,
                        "color_space": "RGB",
                        "is_page_render": True,
                    })
            except Exception as e:
                logger.warning(f"pdf2image page render failed: {e}")

        return images

    def get_page_renders(self, pdf_path: str, dpi: int = 150) -> List[str]:
        """Render each page as base64 PNG for Gemini Vision."""
        renders = []
        try:
            images = convert_from_path(pdf_path, dpi=dpi, fmt="png")
            for img in images:
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                renders.append(b64)
        except Exception as e:
            logger.error(f"Page render failed: {e}")
        return renders
