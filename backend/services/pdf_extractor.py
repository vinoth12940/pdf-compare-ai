import pdfplumber
import pypdf
import base64
import re
import io
from typing import List, Dict, Any, Optional, Tuple
from pdf2image import convert_from_path
from PIL import Image, ImageFilter
import pytesseract
import logging

logger = logging.getLogger(__name__)


def normalize_extracted_text(text: str) -> str:
    """Normalize extracted PDF text for stable matching and display."""
    cleaned = (text or "").strip()
    # pdfplumber often encodes bullet glyphs as `(cid:127)` etc.
    cleaned = re.sub(r"^\(cid:\d+\)\s*", "• ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def is_bullet_line(text: str) -> bool:
    """Detect if a line is a bullet point."""
    stripped = (text or "").strip()
    normalized = normalize_extracted_text(stripped)
    bullet_patterns = [
        r"^\(cid:\d+\)\s*",  # Common bullet glyph encoding from pdfplumber
        r"^[•●○◦▪▸►▻‣⁃]\s",
        r"^[-–—]\s",
        r"^\*\s",
        r"^\d+[.)]\s",
        r"^[a-zA-Z][.)]\s",
        r"^\([a-zA-Z0-9]+\)\s",
    ]
    for pattern in bullet_patterns:
        if re.match(pattern, stripped) or re.match(pattern, normalized):
            return True
    return False


def _looks_like_table_row(text: str) -> bool:
    stripped = text.strip()
    if "|" in stripped:
        return True
    if re.search(r"\$\s?\d", stripped):
        return True
    if re.search(r"^\d+\s+\S+", stripped):
        return True
    return False


def is_heading(
    text: str,
    font_sizes: Optional[List[float]] = None,
    is_bold: bool = False,
) -> bool:
    """Detect if a line looks like a heading."""
    stripped = normalize_extracted_text(text)
    words = stripped.split()

    if is_bullet_line(stripped):
        return False
    if len(stripped) < 3 or len(stripped) > 200:
        return False
    if _looks_like_table_row(stripped):
        return False
    if len(words) < 2 or len(words) > 14:
        return False

    max_font = max(font_sizes) if font_sizes else 0.0

    # Strong heading signals
    if max_font >= 13.0:
        return True
    if stripped.isupper() and len(words) <= 12:
        return True
    if is_bold and len(words) <= 12 and not stripped.endswith((".", ",", ";", ":", "?", "!")):
        return True

    # Fallback: short title-like line without terminal punctuation.
    if (
        not stripped.endswith((".", ",", ";", ":", "?", "!"))
        and 2 <= len(words) <= 10
        and stripped[0].isupper()
        and not re.search(r"\d{4,}", stripped)
    ):
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

    @staticmethod
    def _extract_page_lines(page) -> List[Dict[str, Any]]:
        """Extract page lines with text + lightweight style/layout metadata."""
        def _to_float(value: Any, default: float = 0.0) -> float:
            try:
                return float(value)
            except Exception:
                return default

        page_width = _to_float(getattr(page, "width", 0.0), 0.0)

        try:
            words = page.extract_words(
                extra_attrs=["fontname", "size"],
                keep_blank_chars=False,
                use_text_flow=True,
            ) or []
        except Exception:
            words = []

        # Fallback when word-level extraction fails.
        if not words:
            fallback_lines = []
            raw_text = page.extract_text() or ""
            y_cursor = 0.0
            for raw_line in raw_text.split("\n"):
                text = normalize_extracted_text(raw_line)
                if not text:
                    y_cursor += 10.0
                    continue
                fallback_lines.append({
                    "text": text,
                    "top": y_cursor,
                    "bottom": y_cursor + 10.0,
                    "x0": 0.0,
                    "x1": page_width,
                    "font_size": None,
                    "is_bold": False,
                    "is_italic": False,
                    "page_width": page_width,
                })
                y_cursor += 12.0
            return fallback_lines

        normalized_words: List[Dict[str, Any]] = []
        for word in words:
            text = normalize_extracted_text(str(word.get("text", "")))
            if not text:
                continue
            normalized_words.append({
                "text": text,
                "top": _to_float(word.get("top", 0.0), 0.0),
                "bottom": _to_float(word.get("bottom", 0.0), 0.0),
                "x0": _to_float(word.get("x0", 0.0), 0.0),
                "x1": _to_float(word.get("x1", 0.0), 0.0),
                "size": _to_float(word.get("size", 0.0), 0.0),
                "fontname": str(word.get("fontname", "")),
            })

        normalized_words.sort(key=lambda w: (w["top"], w["x0"]))

        def _build_line(words_in_line: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
            if not words_in_line:
                return None
            words_in_line = sorted(words_in_line, key=lambda w: w["x0"])
            text = normalize_extracted_text(" ".join(w["text"] for w in words_in_line))
            if not text:
                return None

            sizes = [w["size"] for w in words_in_line if w["size"] > 0]
            avg_font_size = round(sum(sizes) / len(sizes), 2) if sizes else None
            fontnames = [w["fontname"].lower() for w in words_in_line if w["fontname"]]

            return {
                "text": text,
                "top": min(w["top"] for w in words_in_line),
                "bottom": max(w["bottom"] for w in words_in_line),
                "x0": min(w["x0"] for w in words_in_line),
                "x1": max(w["x1"] for w in words_in_line),
                "font_size": avg_font_size,
                "is_bold": any(
                    token in name for name in fontnames
                    for token in ("bold", "black", "demi", "semibold")
                ),
                "is_italic": any(("italic" in name) or ("oblique" in name) for name in fontnames),
                "page_width": page_width,
            }

        lines: List[Dict[str, Any]] = []
        current_line: List[Dict[str, Any]] = []
        current_top: Optional[float] = None
        line_tolerance = 2.2

        for word in normalized_words:
            if not current_line:
                current_line = [word]
                current_top = word["top"]
                continue

            if current_top is not None and abs(word["top"] - current_top) > line_tolerance:
                line = _build_line(current_line)
                if line:
                    lines.append(line)
                current_line = [word]
                current_top = word["top"]
            else:
                current_line.append(word)
                current_top = (
                    (current_top * (len(current_line) - 1) + word["top"]) / len(current_line)
                    if current_top is not None else word["top"]
                )

        trailing = _build_line(current_line)
        if trailing:
            lines.append(trailing)

        lines.sort(key=lambda line: (line["top"], line["x0"]))
        return lines

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

                    # Text classification with style/layout metadata.
                    lines = self._extract_page_lines(page)
                    total_text_chars += sum(len((line.get("text") or "").strip()) for line in lines)

                    if lines:
                        current_paragraph_lines: List[Dict[str, Any]] = []
                        prev_bottom: Optional[float] = None

                        def flush_paragraph() -> None:
                            nonlocal current_paragraph_lines
                            if not current_paragraph_lines:
                                return

                            para_text = normalize_extracted_text(
                                " ".join(line["text"] for line in current_paragraph_lines)
                            )
                            font_sizes = [
                                float(line["font_size"]) for line in current_paragraph_lines
                                if line.get("font_size") is not None
                            ]
                            result["paragraphs"].append({
                                "page": page_num,
                                "text": para_text,
                                "font_size": round(sum(font_sizes) / len(font_sizes), 2) if font_sizes else None,
                                "is_bold": any(bool(line.get("is_bold")) for line in current_paragraph_lines),
                                "is_italic": any(bool(line.get("is_italic")) for line in current_paragraph_lines),
                                "indent": round(min(float(line.get("x0", 0.0) or 0.0) for line in current_paragraph_lines), 2),
                                "top": round(float(current_paragraph_lines[0].get("top", 0.0) or 0.0), 2),
                                "bottom": round(float(current_paragraph_lines[-1].get("bottom", 0.0) or 0.0), 2),
                                "prev_gap": round(float(current_paragraph_lines[0].get("prev_gap", 0.0) or 0.0), 2),
                                "line_count": len(current_paragraph_lines),
                                "page_width": float(current_paragraph_lines[0].get("page_width", 0.0) or 0.0),
                            })
                            current_paragraph_lines = []

                        for line in lines:
                            text = normalize_extracted_text(line.get("text", ""))
                            if not text:
                                continue

                            top = float(line.get("top", 0.0) or 0.0)
                            bottom = float(line.get("bottom", top) or top)
                            line_gap = max(0.0, top - prev_bottom) if prev_bottom is not None else 0.0
                            prev_bottom = max(bottom, top)

                            line_item = {
                                **line,
                                "text": text,
                                "prev_gap": round(line_gap, 2),
                            }

                            line_font_sizes = (
                                [float(line_item["font_size"])]
                                if line_item.get("font_size") is not None else None
                            )
                            line_is_bold = bool(line_item.get("is_bold"))

                            if is_bullet_line(text):
                                flush_paragraph()
                                result["bullets"].append({
                                    "page": page_num,
                                    "text": text,
                                    "font_size": line_item.get("font_size"),
                                    "is_bold": line_is_bold,
                                    "is_italic": bool(line_item.get("is_italic")),
                                    "indent": round(float(line_item.get("x0", 0.0) or 0.0), 2),
                                    "top": round(float(line_item.get("top", 0.0) or 0.0), 2),
                                    "bottom": round(float(line_item.get("bottom", 0.0) or 0.0), 2),
                                    "prev_gap": line_item.get("prev_gap", 0.0),
                                    "page_width": float(line_item.get("page_width", 0.0) or 0.0),
                                })
                            elif is_heading(text, font_sizes=line_font_sizes, is_bold=line_is_bold):
                                flush_paragraph()
                                result["headings"].append({
                                    "page": page_num,
                                    "text": text,
                                    "font_size": line_item.get("font_size"),
                                    "is_bold": line_is_bold,
                                    "is_italic": bool(line_item.get("is_italic")),
                                    "indent": round(float(line_item.get("x0", 0.0) or 0.0), 2),
                                    "top": round(float(line_item.get("top", 0.0) or 0.0), 2),
                                    "bottom": round(float(line_item.get("bottom", 0.0) or 0.0), 2),
                                    "prev_gap": line_item.get("prev_gap", 0.0),
                                    "page_width": float(line_item.get("page_width", 0.0) or 0.0),
                                })
                            else:
                                current_paragraph_lines.append(line_item)

                        flush_paragraph()

                # If very little text extracted → likely scanned
                if total_text_chars < 50 * result["page_count"] and self.ocr_available:
                    result["is_scanned"] = True
                    result["paragraphs"] = []
                    result["bullets"] = []
                    result["headings"] = []
                    result = self._run_ocr(pdf_path, result)

        except Exception as e:
            logger.error(f"pdfplumber extraction failed: {e}")
            if self.ocr_available:
                result["is_scanned"] = True
                result["paragraphs"] = []
                result["bullets"] = []
                result["headings"] = []
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
                    stripped = normalize_extracted_text(line)
                    if not stripped:
                        if para_lines:
                            result["paragraphs"].append({
                                "page": page_num,
                                "text": normalize_extracted_text(" ".join(para_lines)),
                                "ocr": True,
                                "font_size": None,
                                "is_bold": False,
                                "is_italic": False,
                                "indent": 0.0,
                                "top": 0.0,
                                "bottom": 0.0,
                                "prev_gap": 0.0,
                                "page_width": 0.0,
                            })
                            para_lines = []
                        continue

                    if is_bullet_line(stripped):
                        if para_lines:
                            result["paragraphs"].append({
                                "page": page_num,
                                "text": normalize_extracted_text(" ".join(para_lines)),
                                "ocr": True,
                                "font_size": None,
                                "is_bold": False,
                                "is_italic": False,
                                "indent": 0.0,
                                "top": 0.0,
                                "bottom": 0.0,
                                "prev_gap": 0.0,
                                "page_width": 0.0,
                            })
                            para_lines = []
                        result["bullets"].append({
                            "page": page_num,
                            "text": stripped,
                            "ocr": True,
                            "font_size": None,
                            "is_bold": False,
                            "is_italic": False,
                            "indent": 0.0,
                            "top": 0.0,
                            "bottom": 0.0,
                            "prev_gap": 0.0,
                            "page_width": 0.0,
                        })
                    elif is_heading(stripped):
                        if para_lines:
                            result["paragraphs"].append({
                                "page": page_num,
                                "text": normalize_extracted_text(" ".join(para_lines)),
                                "ocr": True,
                                "font_size": None,
                                "is_bold": False,
                                "is_italic": False,
                                "indent": 0.0,
                                "top": 0.0,
                                "bottom": 0.0,
                                "prev_gap": 0.0,
                                "page_width": 0.0,
                            })
                            para_lines = []
                        result["headings"].append({
                            "page": page_num,
                            "text": stripped,
                            "ocr": True,
                            "font_size": None,
                            "is_bold": False,
                            "is_italic": False,
                            "indent": 0.0,
                            "top": 0.0,
                            "bottom": 0.0,
                            "prev_gap": 0.0,
                            "page_width": 0.0,
                        })
                    else:
                        para_lines.append(stripped)

                if para_lines:
                    result["paragraphs"].append({
                        "page": page_num,
                        "text": normalize_extracted_text(" ".join(para_lines)),
                        "ocr": True,
                        "font_size": None,
                        "is_bold": False,
                        "is_italic": False,
                        "indent": 0.0,
                        "top": 0.0,
                        "bottom": 0.0,
                        "prev_gap": 0.0,
                        "page_width": 0.0,
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
    def _otsu_threshold(gray_arr: "np.ndarray") -> int:
        """Compute an Otsu threshold for a grayscale page image."""
        import numpy as np

        if gray_arr.size == 0:
            return 128

        hist = np.bincount(gray_arr.ravel(), minlength=256).astype(np.float64)
        total = gray_arr.size
        cumulative_count = hist.cumsum()
        cumulative_sum = (hist * np.arange(256)).cumsum()
        global_mean = cumulative_sum[-1] / total

        denominator = cumulative_count * (total - cumulative_count)
        valid = denominator > 0

        variance = np.zeros(256, dtype=np.float64)
        variance[valid] = (
            (global_mean * cumulative_count[valid] - cumulative_sum[valid]) ** 2
        ) / denominator[valid]

        # Slightly bias upward to ignore anti-aliasing fringe pixels.
        return min(245, int(np.argmax(variance)) + 10)

    @classmethod
    def _binarize_page(cls, img: Image.Image) -> "np.ndarray":
        """
        Convert a page render to a foreground mask (True = ink/content).
        Moderate blur suppresses sub-pixel rendering and anti-aliasing noise.
        """
        import numpy as np

        gray = np.array(img.convert("L").filter(ImageFilter.GaussianBlur(radius=1.2)), dtype=np.uint8)
        threshold = cls._otsu_threshold(gray)
        return gray < threshold

    @staticmethod
    def _shift_mask(mask: "np.ndarray", dx: int, dy: int) -> "np.ndarray":
        """Shift a boolean mask by dx/dy with zero padding (no wrap-around)."""
        import numpy as np

        h, w = mask.shape
        shifted = np.zeros_like(mask, dtype=bool)

        if dx >= 0:
            src_x0, src_x1 = 0, w - dx
            dst_x0, dst_x1 = dx, w
        else:
            src_x0, src_x1 = -dx, w
            dst_x0, dst_x1 = 0, w + dx

        if dy >= 0:
            src_y0, src_y1 = 0, h - dy
            dst_y0, dst_y1 = dy, h
        else:
            src_y0, src_y1 = -dy, h
            dst_y0, dst_y1 = 0, h + dy

        if src_x1 <= src_x0 or src_y1 <= src_y0:
            return shifted

        shifted[dst_y0:dst_y1, dst_x0:dst_x1] = mask[src_y0:src_y1, src_x0:src_x1]
        return shifted

    @classmethod
    def _find_best_shift(
        cls, mask_a: "np.ndarray", mask_b: "np.ndarray", max_shift: int = 4
    ) -> Tuple[int, int]:
        """
        Find small translation that minimizes mismatch between document ink masks.
        Handles slight render offsets that otherwise highlight the whole page.
        """
        import numpy as np

        best_dx = 0
        best_dy = 0
        best_score = float("inf")

        for dy in range(-max_shift, max_shift + 1):
            for dx in range(-max_shift, max_shift + 1):
                shifted_b = cls._shift_mask(mask_b, dx=dx, dy=dy)
                union = np.logical_or(mask_a, shifted_b)

                if not union.any():
                    score = 0.0
                else:
                    diff = np.logical_xor(mask_a, shifted_b)
                    score = float(diff[union].mean())

                if score < best_score:
                    best_score = score
                    best_dx = dx
                    best_dy = dy

        return best_dx, best_dy

    @staticmethod
    def _cleanup_diff_mask(mask: "np.ndarray") -> "np.ndarray":
        """
        Remove speckle noise from the raw XOR diff mask.
        Keeps regions where content genuinely changed while filtering out
        single-pixel anti-aliasing artifacts.
        """
        import numpy as np

        if mask.size == 0:
            return mask

        pil_mask = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
        # Erode to remove thin single-pixel rendering noise
        pil_mask = pil_mask.filter(ImageFilter.MinFilter(3))
        # Dilate back so surviving regions keep their shape
        pil_mask = pil_mask.filter(ImageFilter.MaxFilter(5))
        cleaned = np.array(pil_mask) > 127

        h, w = cleaned.shape
        block_size = 12  # moderate block size
        filtered = np.zeros_like(cleaned, dtype=bool)

        for y in range(0, h, block_size):
            y2 = min(h, y + block_size)
            for x in range(0, w, block_size):
                x2 = min(w, x + block_size)
                region = cleaned[y:y2, x:x2]
                changed_ratio = float(region.mean())
                changed_pixels = int(region.sum())
                # Block must have >=20% changed pixels AND at least 10 pixels
                if changed_ratio >= 0.20 and changed_pixels >= 10:
                    filtered[y:y2, x:x2] = True

        return filtered

    @staticmethod
    def _expand_mask(mask: "np.ndarray", radius: int = 1) -> "np.ndarray":
        """Slightly expand changed regions so highlights are visible but readable."""
        import numpy as np

        size = max(3, radius * 2 + 1)
        pil_mask = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
        pil_mask = pil_mask.filter(ImageFilter.MaxFilter(size))
        return np.array(pil_mask) > 127

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

                mask_a = PDFExtractor._binarize_page(img_a)
                mask_b = PDFExtractor._binarize_page(img_b)

                # Align small render offsets before differencing.
                shift_x, shift_y = PDFExtractor._find_best_shift(mask_a, mask_b, max_shift=6)
                aligned_mask_b = PDFExtractor._shift_mask(mask_b, dx=shift_x, dy=shift_y)

                raw_changed_mask_a = np.logical_xor(mask_a, aligned_mask_b)
                cleaned_mask_a = PDFExtractor._cleanup_diff_mask(raw_changed_mask_a)
                visible_mask_a = PDFExtractor._expand_mask(cleaned_mask_a, radius=2)

                # Convert back into document-B coordinates for accurate B overlays.
                raw_changed_mask_b = PDFExtractor._shift_mask(visible_mask_a, dx=-shift_x, dy=-shift_y)
                visible_mask_b = PDFExtractor._expand_mask(raw_changed_mask_b, radius=2)

                # Create overlay for A (red = removed/changed)
                overlay_a = img_a.copy().convert("RGBA")
                red_layer = Image.new("RGBA", overlay_a.size, (0, 0, 0, 0))
                red_arr = np.array(red_layer)
                red_arr[visible_mask_a] = [255, 60, 60, 70]  # visible highlight
                red_layer = Image.fromarray(red_arr)
                overlay_a = Image.alpha_composite(overlay_a, red_layer)

                # Create overlay for B (green = added/changed)
                overlay_b = img_b.copy().convert("RGBA")
                green_layer = Image.new("RGBA", overlay_b.size, (0, 0, 0, 0))
                green_arr = np.array(green_layer)
                green_arr[visible_mask_b] = [50, 180, 50, 70]  # visible highlight
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
