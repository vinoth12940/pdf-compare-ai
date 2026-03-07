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
import pypdfium2 as pdfium

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
        r"^[•●○◦▪▸►▻‣⁃]\s*",
        r"^[-–—]\s*",
        r"^\*\s*",
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
    word_count = len(words)

    if is_bullet_line(stripped):
        return False
    if len(stripped) < 3 or len(stripped) > 200:
        return False
    if _looks_like_table_row(stripped):
        return False
    if word_count == 0 or word_count > 14:
        return False

    max_font = max(font_sizes) if font_sizes else 0.0
    contains_contact_like_content = bool(
        re.search(r"(@|www\.|https?://|\b\d{5}\b|\(\d{3}\)\s*\d{3}-\d{4})", stripped, re.IGNORECASE)
    )
    has_inline_punctuation = (":" in stripped) or ("," in stripped)

    if contains_contact_like_content and max_font < 12.5:
        return False

    # Strong heading signals
    if max_font >= 13.0 and word_count <= 14:
        return True
    if stripped.isupper() and 1 <= word_count <= 12:
        return True
    if (
        is_bold
        and 1 <= word_count <= 12
        and not stripped.endswith((".", ",", ";", ":", "?", "!"))
        and not has_inline_punctuation
    ):
        return True

    # Fallback: title-like line with a modest font bump over body text.
    if (
        max_font >= 11.5
        and
        not stripped.endswith((".", ",", ";", ":", "?", "!"))
        and 1 <= word_count <= 6
        and stripped[0].isupper()
        and not has_inline_punctuation
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
        page_height = _to_float(getattr(page, "height", 0.0), 0.0)

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
                    "page_height": page_height,
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
                "page_height": page_height,
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

    @staticmethod
    def _line_overlaps_bbox(line: Dict[str, Any], bbox: Tuple[float, float, float, float], tolerance: float = 2.0) -> bool:
        x0, top, x1, bottom = bbox
        line_top = float(line.get("top", 0.0) or 0.0)
        line_bottom = float(line.get("bottom", line_top) or line_top)
        line_x0 = float(line.get("x0", 0.0) or 0.0)
        line_x1 = float(line.get("x1", line_x0) or line_x0)

        vertical_overlap = min(line_bottom, bottom) - max(line_top, top)
        horizontal_overlap = min(line_x1, x1) - max(line_x0, x0)
        return vertical_overlap > -tolerance and horizontal_overlap > -tolerance

    @staticmethod
    def _should_split_paragraph(current_lines: List[Dict[str, Any]], next_line: Dict[str, Any]) -> bool:
        if not current_lines:
            return False

        prev_line = current_lines[-1]
        prev_height = max(1.0, float(prev_line.get("bottom", 0.0) or 0.0) - float(prev_line.get("top", 0.0) or 0.0))
        next_gap = float(next_line.get("prev_gap", 0.0) or 0.0)

        if next_gap > max(12.0, prev_height * 1.6):
            return True

        prev_indent = float(prev_line.get("x0", 0.0) or 0.0)
        next_indent = float(next_line.get("x0", 0.0) or 0.0)
        if abs(next_indent - prev_indent) >= 18.0 and next_gap >= 6.0:
            return True

        prev_font = prev_line.get("font_size")
        next_font = next_line.get("font_size")
        if prev_font is not None and next_font is not None and abs(float(next_font) - float(prev_font)) >= 1.5 and next_gap >= 4.0:
            return True

        if bool(prev_line.get("is_bold")) != bool(next_line.get("is_bold")) and next_gap >= 6.0:
            return True

        return False

    @staticmethod
    def _render_pdf_to_images(pdf_path: str, dpi: int = 150) -> List[Image.Image]:
        try:
            return convert_from_path(pdf_path, dpi=dpi, fmt="png")
        except Exception as exc:
            logger.warning(f"pdf2image render failed, falling back to PDFium: {exc}")

        images: List[Image.Image] = []
        try:
            doc = pdfium.PdfDocument(pdf_path)
            scale = dpi / 72.0
            for page_index in range(len(doc)):
                page = doc[page_index]
                bitmap = page.render(scale=scale)
                images.append(bitmap.to_pil().convert("RGB"))
            return images
        except Exception as exc:
            logger.error(f"PDFium render failed: {exc}")
            return []

    @staticmethod
    def _extract_ocr_lines(img: Image.Image, dpi: int = 200) -> List[Dict[str, Any]]:
        scale = 72.0 / float(dpi)
        page_width = round(img.width * scale, 2)
        page_height = round(img.height * scale, 2)

        try:
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        except Exception as exc:
            logger.error(f"OCR TSV extraction failed: {exc}")
            return []

        line_groups: Dict[Tuple[int, int, int], List[Dict[str, Any]]] = {}
        total_items = len(data.get("text", []))
        for idx in range(total_items):
            raw_text = data["text"][idx]
            text = normalize_extracted_text(raw_text)
            if not text:
                continue

            conf_raw = data.get("conf", ["-1"] * total_items)[idx]
            try:
                confidence = float(conf_raw)
            except Exception:
                confidence = -1.0
            if confidence < 0:
                continue

            key = (
                int(data.get("block_num", [0] * total_items)[idx] or 0),
                int(data.get("par_num", [0] * total_items)[idx] or 0),
                int(data.get("line_num", [0] * total_items)[idx] or 0),
            )
            left = float(data.get("left", [0] * total_items)[idx] or 0)
            top = float(data.get("top", [0] * total_items)[idx] or 0)
            width = float(data.get("width", [0] * total_items)[idx] or 0)
            height = float(data.get("height", [0] * total_items)[idx] or 0)

            line_groups.setdefault(key, []).append({
                "text": text,
                "x0": round(left * scale, 2),
                "x1": round((left + width) * scale, 2),
                "top": round(top * scale, 2),
                "bottom": round((top + height) * scale, 2),
                "font_size": round(height * scale, 2),
                "confidence": confidence,
            })

        lines: List[Dict[str, Any]] = []
        for words in line_groups.values():
            if not words:
                continue
            words.sort(key=lambda word: word["x0"])
            line_text = normalize_extracted_text(" ".join(word["text"] for word in words))
            if not line_text:
                continue

            font_sizes = [word["font_size"] for word in words if word["font_size"] > 0]
            lines.append({
                "text": line_text,
                "x0": min(word["x0"] for word in words),
                "x1": max(word["x1"] for word in words),
                "top": min(word["top"] for word in words),
                "bottom": max(word["bottom"] for word in words),
                "font_size": round(sum(font_sizes) / len(font_sizes), 2) if font_sizes else None,
                "is_bold": False,
                "is_italic": False,
                "page_width": page_width,
                "page_height": page_height,
            })

        lines.sort(key=lambda line: (line["top"], line["x0"]))
        return lines

    def _classify_lines(
        self,
        lines: List[Dict[str, Any]],
        page_num: int,
        result: Dict[str, Any],
    ) -> None:
        if not lines:
            return

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
                "x0": round(min(float(line.get("x0", 0.0) or 0.0) for line in current_paragraph_lines), 2),
                "x1": round(max(float(line.get("x1", 0.0) or 0.0) for line in current_paragraph_lines), 2),
                "top": round(float(current_paragraph_lines[0].get("top", 0.0) or 0.0), 2),
                "bottom": round(float(current_paragraph_lines[-1].get("bottom", 0.0) or 0.0), 2),
                "prev_gap": round(float(current_paragraph_lines[0].get("prev_gap", 0.0) or 0.0), 2),
                "line_count": len(current_paragraph_lines),
                "page_width": float(current_paragraph_lines[0].get("page_width", 0.0) or 0.0),
                "page_height": float(current_paragraph_lines[0].get("page_height", 0.0) or 0.0),
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
                    "x0": round(float(line_item.get("x0", 0.0) or 0.0), 2),
                    "x1": round(float(line_item.get("x1", 0.0) or 0.0), 2),
                    "top": round(float(line_item.get("top", 0.0) or 0.0), 2),
                    "bottom": round(float(line_item.get("bottom", 0.0) or 0.0), 2),
                    "prev_gap": line_item.get("prev_gap", 0.0),
                    "page_width": float(line_item.get("page_width", 0.0) or 0.0),
                    "page_height": float(line_item.get("page_height", 0.0) or 0.0),
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
                    "x0": round(float(line_item.get("x0", 0.0) or 0.0), 2),
                    "x1": round(float(line_item.get("x1", 0.0) or 0.0), 2),
                    "top": round(float(line_item.get("top", 0.0) or 0.0), 2),
                    "bottom": round(float(line_item.get("bottom", 0.0) or 0.0), 2),
                    "prev_gap": line_item.get("prev_gap", 0.0),
                    "page_width": float(line_item.get("page_width", 0.0) or 0.0),
                    "page_height": float(line_item.get("page_height", 0.0) or 0.0),
                })
            else:
                if self._should_split_paragraph(current_paragraph_lines, line_item):
                    flush_paragraph()
                current_paragraph_lines.append(line_item)

        flush_paragraph()

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
                    page_width = float(getattr(page, "width", 0.0) or 0.0)
                    page_height = float(getattr(page, "height", 0.0) or 0.0)

                    # Tables: prefer finder API so we retain geometry for viewer highlights.
                    table_bboxes: List[Tuple[float, float, float, float]] = []
                    try:
                        tables = page.find_tables()
                    except Exception:
                        tables = []

                    for tbl_idx, table in enumerate(tables):
                        extracted = table.extract() if table else []
                        if extracted:
                            x0, top, x1, bottom = table.bbox
                            table_bboxes.append((float(x0), float(top), float(x1), float(bottom)))
                            result["tables"].append({
                                "page": page_num,
                                "table_index": tbl_idx,
                                "data": extracted,
                                "headers": extracted[0] if extracted else [],
                                "rows": extracted[1:] if len(extracted) > 1 else [],
                                "x0": round(float(x0), 2),
                                "x1": round(float(x1), 2),
                                "top": round(float(top), 2),
                                "bottom": round(float(bottom), 2),
                                "page_width": page_width,
                                "page_height": page_height,
                            })

                    # Text classification with style/layout metadata.
                    lines = self._extract_page_lines(page)
                    lines = [
                        line for line in lines
                        if not any(self._line_overlaps_bbox(line, bbox) for bbox in table_bboxes)
                    ]
                    total_text_chars += sum(len((line.get("text") or "").strip()) for line in lines)
                    self._classify_lines(lines, page_num, result)

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
            ocr_dpi = 200
            images = self._render_pdf_to_images(pdf_path, dpi=ocr_dpi)
            result["page_count"] = len(images)

            for page_num, img in enumerate(images, 1):
                lines = self._extract_ocr_lines(img, dpi=ocr_dpi)
                self._classify_lines(lines, page_num, result)

        except Exception as e:
            logger.error(f"OCR failed: {e}")

        return result

    @staticmethod
    def _stream_value(stream_obj: Any, key: str, default: Any = None) -> Any:
        if hasattr(stream_obj, "get"):
            try:
                return stream_obj.get(key, default)
            except Exception:
                pass

        attrs = getattr(stream_obj, "attrs", None)
        if isinstance(attrs, dict):
            return attrs.get(key, default)
        return default

    def _pdf_image_to_png_b64(self, stream_obj: Any, width: int, height: int) -> Optional[str]:
        """Convert a raw PDF image stream to valid PNG base64.
        
        PDF images store raw byte streams (JPEG, raw RGB, CMYK, etc.)
        that are NOT valid PNG/JPEG files on their own. This method
        decodes them into PIL Images and re-encodes as PNG.
        """
        try:
            if not hasattr(stream_obj, "get_data"):
                return None

            data = stream_obj.get_data()
            color_space = str(self._stream_value(stream_obj, "/ColorSpace", self._stream_value(stream_obj, "ColorSpace", "/DeviceRGB")))
            bits_per_component = int(self._stream_value(stream_obj, "/BitsPerComponent", self._stream_value(stream_obj, "BitsPerComponent", 8)))
            filt = self._stream_value(stream_obj, "/Filter", self._stream_value(stream_obj, "Filter", ""))

            # If it's DCTDecode (JPEG), the data IS valid JPEG
            filter_str = str(filt)

            if "DCTDecode" in filter_str:
                img = Image.open(io.BytesIO(data))
            elif "FlateDecode" in filter_str or not filt:
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
        """Extract images with placement boxes as valid base64 PNG strings."""
        images = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    page_width = float(getattr(page, "width", 0.0) or 0.0)
                    page_height = float(getattr(page, "height", 0.0) or 0.0)
                    page_images = page.images or []

                    for image_index, image_info in enumerate(page_images):
                        try:
                            stream = image_info.get("stream")
                            if not stream:
                                continue

                            srcsize = image_info.get("srcsize") or (0, 0)
                            width = int(srcsize[0] or self._stream_value(stream, "Width", 0) or 0)
                            height = int(srcsize[1] or self._stream_value(stream, "Height", 0) or 0)
                            if width <= 20 or height <= 20:
                                continue

                            b64 = self._pdf_image_to_png_b64(stream, width, height)
                            if b64:
                                images.append({
                                    "page": page_num,
                                    "image_index": image_index,
                                    "width": width,
                                    "height": height,
                                    "data_b64": b64,
                                    "color_space": str(image_info.get("colorspace", "RGB")),
                                    "x0": round(float(image_info.get("x0", 0.0) or 0.0), 2),
                                    "x1": round(float(image_info.get("x1", 0.0) or 0.0), 2),
                                    "top": round(float(image_info.get("top", 0.0) or 0.0), 2),
                                    "bottom": round(float(image_info.get("bottom", 0.0) or 0.0), 2),
                                    "page_width": page_width,
                                    "page_height": page_height,
                                })
                        except Exception as ex:
                            logger.debug(f"Skip image {image_index} on page {page_num}: {ex}")
        except Exception as e:
            logger.warning(f"Image extraction failed: {e}")

        if not images:
            try:
                reader = pypdf.PdfReader(pdf_path)
                for page_num, page in enumerate(reader.pages, 1):
                    if "/Resources" in page and "/XObject" in page.get("/Resources", {}):
                        xobjects = page["/Resources"]["/XObject"]
                        if not xobjects:
                            continue
                        for obj_name, obj in xobjects.items():
                            try:
                                if hasattr(obj, "get") and obj.get("/Subtype") == "/Image":
                                    width = int(obj.get("/Width", 0))
                                    height = int(obj.get("/Height", 0))
                                    if width <= 20 or height <= 20:
                                        continue

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
                                logger.debug(f"Skip fallback image {obj_name} on page {page_num}: {ex}")
            except Exception as e:
                logger.warning(f"Fallback image extraction failed: {e}")

        return images

    def get_page_renders(self, pdf_path: str, dpi: int = 150) -> List[str]:
        """Render each page as base64 PNG for Gemini Vision."""
        renders = []
        try:
            images = self._render_pdf_to_images(pdf_path, dpi=dpi)
            for img in images:
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                renders.append(b64)
        except Exception as e:
            logger.error(f"Page render failed: {e}")
        return renders
