import difflib
import re
from typing import List, Dict, Any, Tuple, Optional
from models.schemas import (
    DiffType,
    TextDiff,
    TableDiff,
    TableCellDiff,
    ImageDiff,
    PageDiff,
    ComparisonResult,
    BoundingBox,
    ViewerRegion,
    PagePair,
)
from services.gemini_service import GeminiService
import uuid
import logging

logger = logging.getLogger(__name__)


def _sanitize_list(lst):
    """Convert None values in a list to empty strings (for pdfplumber headers/cells)."""
    if lst is None:
        return None
    return [str(v) if v is not None else "" for v in lst]


def _normalize_text(text: str) -> str:
    normalized = (text or "").lower()
    normalized = re.sub(r"\(cid:\d+\)", " ", normalized)
    normalized = re.sub(r"[•●○◦▪▸►▻‣⁃]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _similarity(a: str, b: str) -> float:
    """Compute normalized similarity ratio between two strings."""
    a_norm = _normalize_text(a)
    b_norm = _normalize_text(b)
    if not a_norm and not b_norm:
        return 1.0
    if not a_norm or not b_norm:
        return 0.0
    return difflib.SequenceMatcher(None, a_norm, b_norm).ratio()


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _length_ratio(a: str, b: str) -> float:
    a_len = len((a or "").strip())
    b_len = len((b or "").strip())
    if a_len == 0 and b_len == 0:
        return 1.0
    if a_len == 0 or b_len == 0:
        return 0.0
    return min(a_len, b_len) / max(a_len, b_len)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _item_bbox(item: Optional[Dict[str, Any]]) -> Optional[BoundingBox]:
    if not item:
        return None

    page_width = _to_float(item.get("page_width"))
    page_height = _to_float(item.get("page_height"))
    x0 = _to_float(item.get("x0"))
    x1 = _to_float(item.get("x1"))
    top = _to_float(item.get("top"))
    bottom = _to_float(item.get("bottom"))

    if not all(v is not None for v in (page_width, page_height, x0, x1, top, bottom)):
        return None
    if page_width <= 0 or page_height <= 0 or x1 <= x0 or bottom <= top:
        return None

    pad_x = min(6.0, page_width * 0.015)
    pad_y = min(4.0, page_height * 0.01)

    return BoundingBox(
        x0=round(_clamp01((x0 - pad_x) / page_width), 4),
        y0=round(_clamp01((top - pad_y) / page_height), 4),
        x1=round(_clamp01((x1 + pad_x) / page_width), 4),
        y1=round(_clamp01((bottom + pad_y) / page_height), 4),
    )


def _preview_label(*values: Optional[str], fallback: str = "Difference") -> str:
    for value in values:
        text = re.sub(r"\s+", " ", (value or "")).strip()
        if text:
            return text[:96] + ("..." if len(text) > 96 else "")
    return fallback


def _page_signatures(data: Dict[str, Any]) -> List[str]:
    page_count = int(data.get("page_count", 0) or 0)
    page_text: Dict[int, List[str]] = {page: [] for page in range(1, page_count + 1)}

    for key in ("headings", "paragraphs", "bullets"):
        for item in data.get(key, []):
            page = item.get("page")
            if isinstance(page, int):
                page_text.setdefault(page, []).append(item.get("text", ""))

    for table in data.get("tables", []):
        page = table.get("page")
        if not isinstance(page, int):
            continue
        rows = table.get("rows") or []
        headers = table.get("headers") or []
        row_text = " ".join(" | ".join(str(cell or "") for cell in row) for row in rows[:3])
        page_text.setdefault(page, []).append(f"{' '.join(str(cell or '') for cell in headers)} {row_text}")

    return [
        _normalize_text(" ".join(page_text.get(page, [])))
        for page in range(1, page_count + 1)
    ]


def _match_score(a_item: Dict, b_item: Dict, key: str = "text") -> float:
    text_score = _similarity(a_item.get(key, ""), b_item.get(key, ""))
    if text_score <= 0.0:
        return 0.0

    len_score = _length_ratio(a_item.get(key, ""), b_item.get(key, ""))
    page_a = a_item.get("page")
    page_b = b_item.get("page")
    if isinstance(page_a, int) and isinstance(page_b, int):
        page_penalty = min(abs(page_a - page_b) * 0.08, 0.32)
    else:
        page_penalty = 0.0

    return max(0.0, (text_score * 0.88 + len_score * 0.12) - page_penalty)


def _match_items(
    list_a: List[Dict], list_b: List[Dict], key: str = "text"
) -> List[Tuple[Optional[Dict], Optional[Dict]]]:
    """
    Greedily match items from list_a to list_b based on normalized text + layout proximity.
    Returns pairs of (a_item, b_item) where None means no match.
    """
    used_b = set()
    pairs: List[Tuple[Optional[Dict], Optional[Dict]]] = []

    for a_item in list_a:
        best_score = -1.0
        best_j = -1
        for j, b_item in enumerate(list_b):
            if j in used_b:
                continue
            score = _match_score(a_item, b_item, key=key)
            if score > best_score:
                best_score = score
                best_j = j

        if best_j >= 0 and best_score > 0.34:
            pairs.append((a_item, list_b[best_j]))
            used_b.add(best_j)
        else:
            pairs.append((a_item, None))

    for j, b_item in enumerate(list_b):
        if j not in used_b:
            pairs.append((None, b_item))

    return pairs


def _detect_style_layout_changes(a_item: Dict[str, Any], b_item: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    style_changes: List[str] = []
    layout_changes: List[str] = []

    size_a = _to_float(a_item.get("font_size"))
    size_b = _to_float(b_item.get("font_size"))
    if size_a is not None and size_b is not None and abs(size_a - size_b) >= 0.6:
        style_changes.append(f"Font size {size_a:.1f} -> {size_b:.1f}")

    bold_a = bool(a_item.get("is_bold", False))
    bold_b = bool(b_item.get("is_bold", False))
    if bold_a != bold_b:
        style_changes.append("Bold style changed")

    italic_a = bool(a_item.get("is_italic", False))
    italic_b = bool(b_item.get("is_italic", False))
    if italic_a != italic_b:
        style_changes.append("Italic style changed")

    indent_a = _to_float(a_item.get("indent"))
    indent_b = _to_float(b_item.get("indent"))
    if indent_a is not None and indent_b is not None and abs(indent_a - indent_b) >= 8.0:
        layout_changes.append("Indentation changed")

    gap_a = _to_float(a_item.get("prev_gap"))
    gap_b = _to_float(b_item.get("prev_gap"))
    if gap_a is not None and gap_b is not None and abs(gap_a - gap_b) >= 4.0:
        layout_changes.append("Spacing before block changed")

    page_a = a_item.get("page")
    page_b = b_item.get("page")
    if isinstance(page_a, int) and isinstance(page_b, int) and page_a != page_b:
        layout_changes.append(f"Moved from page {page_a} to {page_b}")

    return style_changes, layout_changes


def _table_signature(table: Dict[str, Any]) -> str:
    headers = " ".join(str(v or "") for v in (table.get("headers") or []))
    rows = table.get("rows") or table.get("data") or []
    preview_rows = rows[:3]
    row_text = " ".join(
        " | ".join(str(cell or "") for cell in row)
        for row in preview_rows
    )
    return _normalize_text(f"{headers} {row_text}")


def _table_match_score(tbl_a: Dict[str, Any], tbl_b: Dict[str, Any]) -> float:
    header_a = " ".join(str(v or "") for v in (tbl_a.get("headers") or []))
    header_b = " ".join(str(v or "") for v in (tbl_b.get("headers") or []))
    header_score = _similarity(header_a, header_b)
    signature_score = _similarity(_table_signature(tbl_a), _table_signature(tbl_b))

    page_a = tbl_a.get("page")
    page_b = tbl_b.get("page")
    if isinstance(page_a, int) and isinstance(page_b, int):
        page_penalty = min(abs(page_a - page_b) * 0.08, 0.28)
    else:
        page_penalty = 0.0

    return max(0.0, (header_score * 0.62 + signature_score * 0.38) - page_penalty)


def _match_tables(
    tables_a: List[Dict[str, Any]],
    tables_b: List[Dict[str, Any]],
) -> List[Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]:
    used_b = set()
    pairs: List[Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]] = []

    for tbl_a in tables_a:
        best_score = -1.0
        best_j = -1
        for j, tbl_b in enumerate(tables_b):
            if j in used_b:
                continue
            score = _table_match_score(tbl_a, tbl_b)
            if score > best_score:
                best_score = score
                best_j = j

        if best_j >= 0 and best_score > 0.35:
            pairs.append((tbl_a, tables_b[best_j]))
            used_b.add(best_j)
        else:
            pairs.append((tbl_a, None))

    for j, tbl_b in enumerate(tables_b):
        if j not in used_b:
            pairs.append((None, tbl_b))

    return pairs


def _bbox_overlap_score(a_item: Dict[str, Any], b_item: Dict[str, Any]) -> float:
    x0_a = _to_float(a_item.get("x0"))
    x1_a = _to_float(a_item.get("x1"))
    top_a = _to_float(a_item.get("top"))
    bottom_a = _to_float(a_item.get("bottom"))
    x0_b = _to_float(b_item.get("x0"))
    x1_b = _to_float(b_item.get("x1"))
    top_b = _to_float(b_item.get("top"))
    bottom_b = _to_float(b_item.get("bottom"))

    if not all(v is not None for v in (x0_a, x1_a, top_a, bottom_a, x0_b, x1_b, top_b, bottom_b)):
        return 0.0

    inter_w = max(0.0, min(x1_a, x1_b) - max(x0_a, x0_b))
    inter_h = max(0.0, min(bottom_a, bottom_b) - max(top_a, top_b))
    intersection = inter_w * inter_h

    area_a = max(0.0, x1_a - x0_a) * max(0.0, bottom_a - top_a)
    area_b = max(0.0, x1_b - x0_b) * max(0.0, bottom_b - top_b)
    union = area_a + area_b - intersection
    if union <= 0:
        return 0.0
    return intersection / union


def _image_match_score(img_a: Dict[str, Any], img_b: Dict[str, Any]) -> float:
    source_width_ratio = _length_ratio(str(img_a.get("width", "")), str(img_b.get("width", "")))
    source_height_ratio = _length_ratio(str(img_a.get("height", "")), str(img_b.get("height", "")))
    source_size_score = (source_width_ratio + source_height_ratio) / 2.0

    placement_overlap = _bbox_overlap_score(img_a, img_b)

    placement_width_a = (_to_float(img_a.get("x1")) or 0.0) - (_to_float(img_a.get("x0")) or 0.0)
    placement_width_b = (_to_float(img_b.get("x1")) or 0.0) - (_to_float(img_b.get("x0")) or 0.0)
    placement_height_a = (_to_float(img_a.get("bottom")) or 0.0) - (_to_float(img_a.get("top")) or 0.0)
    placement_height_b = (_to_float(img_b.get("bottom")) or 0.0) - (_to_float(img_b.get("top")) or 0.0)

    placement_width_score = _length_ratio(str(max(0.0, placement_width_a)), str(max(0.0, placement_width_b)))
    placement_height_score = _length_ratio(str(max(0.0, placement_height_a)), str(max(0.0, placement_height_b)))
    placement_size_score = (placement_width_score + placement_height_score) / 2.0

    x0_a = _to_float(img_a.get("x0"))
    x1_a = _to_float(img_a.get("x1"))
    top_a = _to_float(img_a.get("top"))
    bottom_a = _to_float(img_a.get("bottom"))
    x0_b = _to_float(img_b.get("x0"))
    x1_b = _to_float(img_b.get("x1"))
    top_b = _to_float(img_b.get("top"))
    bottom_b = _to_float(img_b.get("bottom"))
    page_width = max(_to_float(img_a.get("page_width")) or 0.0, _to_float(img_b.get("page_width")) or 0.0, 1.0)
    page_height = max(_to_float(img_a.get("page_height")) or 0.0, _to_float(img_b.get("page_height")) or 0.0, 1.0)

    center_score = 0.0
    if all(v is not None for v in (x0_a, x1_a, top_a, bottom_a, x0_b, x1_b, top_b, bottom_b)):
        center_a = ((x0_a + x1_a) / 2.0, (top_a + bottom_a) / 2.0)
        center_b = ((x0_b + x1_b) / 2.0, (top_b + bottom_b) / 2.0)
        dx = abs(center_a[0] - center_b[0]) / page_width
        dy = abs(center_a[1] - center_b[1]) / page_height
        center_score = max(0.0, 1.0 - ((dx + dy) / 2.0))

    return (
        (placement_overlap * 0.45)
        + (center_score * 0.2)
        + (placement_size_score * 0.2)
        + (source_size_score * 0.15)
    )


def _match_page_images(
    images_a: List[Dict[str, Any]],
    images_b: List[Dict[str, Any]],
) -> List[Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]:
    used_b = set()
    pairs: List[Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]] = []

    for img_a in images_a:
        best_score = -1.0
        best_j = -1
        for j, img_b in enumerate(images_b):
            if j in used_b:
                continue
            score = _image_match_score(img_a, img_b)
            if score > best_score:
                best_score = score
                best_j = j

        if best_j >= 0 and best_score >= 0.35:
            pairs.append((img_a, images_b[best_j]))
            used_b.add(best_j)
        else:
            pairs.append((img_a, None))

    for j, img_b in enumerate(images_b):
        if j not in used_b:
            pairs.append((None, img_b))

    return pairs


class Comparator:
    def __init__(self, gemini: GeminiService):
        self.gemini = gemini

    # ─── Text / Paragraph Comparison ───────────────────────────────────────────

    def compare_text_blocks(
        self, blocks_a: List[Dict], blocks_b: List[Dict], section_type: str = "paragraph"
    ) -> Tuple[List[TextDiff], int, float]:
        """
        Compare text blocks and return (changed_diffs, total_pairs, sum_of_scores).
        total_pairs and sum_of_scores include unchanged items for accurate similarity calc.
        """
        diffs = []
        pairs = _match_items(blocks_a, blocks_b)
        total_pairs = len(pairs)
        score_sum = 0.0

        for a_item, b_item in pairs:
            text_a = a_item["text"] if a_item else ""
            text_b = b_item["text"] if b_item else ""
            page = (a_item or b_item).get("page", 0)

            raw_score = _similarity(text_a, text_b)
            style_changes: List[str] = []
            layout_changes: List[str] = []
            if a_item and b_item:
                style_changes, layout_changes = _detect_style_layout_changes(a_item, b_item)

            # Style/layout differences reduce effective similarity even if text is identical.
            score_penalty = min(0.28, (0.05 * len(style_changes)) + (0.04 * len(layout_changes)))
            score = max(0.0, raw_score - score_penalty)
            score_sum += score

            if not a_item:
                diff_type = DiffType.ADDED
            elif not b_item:
                diff_type = DiffType.REMOVED
            elif score >= 0.97 and not style_changes and not layout_changes:
                diff_type = DiffType.UNCHANGED
            else:
                diff_type = DiffType.CHANGED

            if diff_type != DiffType.UNCHANGED:
                position = (a_item or b_item or {}).get("top", 0.0)
                diffs.append(TextDiff(
                    page=page,
                    page_a=a_item.get("page") if a_item else None,
                    page_b=b_item.get("page") if b_item else None,
                    content_a=text_a,
                    content_b=text_b,
                    diff_type=diff_type,
                    similarity_score=round(score, 3),
                    section_type=section_type,
                    style_changes=style_changes or None,
                    layout_changes=layout_changes or None,
                    position=round(float(position), 2),
                    bbox_a=_item_bbox(a_item),
                    bbox_b=_item_bbox(b_item),
                ))

        return diffs, total_pairs, score_sum

    # ─── Table Comparison ──────────────────────────────────────────────────────

    def compare_tables(self, tables_a: List[Dict], tables_b: List[Dict]) -> List[TableDiff]:
        diffs = []
        table_pairs = _match_tables(tables_a, tables_b)

        for pair_index, (tbl_a, tbl_b) in enumerate(table_pairs):
            table_index = (tbl_a or tbl_b or {}).get("table_index", pair_index)

            if tbl_a is None:
                added_rows = tbl_b.get("rows") or tbl_b.get("data") or []
                diffs.append(TableDiff(
                    page=(tbl_b or {}).get("page", 0),
                    page_a=None,
                    page_b=(tbl_b or {}).get("page"),
                    table_index=table_index,
                    headers_a=None,
                    headers_b=_sanitize_list(tbl_b.get("headers")) if tbl_b else None,
                    cell_diffs=[],
                    rows_added=len(added_rows) if tbl_b else 0,
                    rows_removed=0,
                    diff_type=DiffType.ADDED,
                    bbox_a=None,
                    bbox_b=_item_bbox(tbl_b),
                ))
                continue

            if tbl_b is None:
                removed_rows = tbl_a.get("rows") or tbl_a.get("data") or []
                diffs.append(TableDiff(
                    page=(tbl_a or {}).get("page", 0),
                    page_a=(tbl_a or {}).get("page"),
                    page_b=None,
                    table_index=table_index,
                    headers_a=_sanitize_list(tbl_a.get("headers")) if tbl_a else None,
                    headers_b=None,
                    cell_diffs=[],
                    rows_added=0,
                    rows_removed=len(removed_rows) if tbl_a else 0,
                    diff_type=DiffType.REMOVED,
                    bbox_a=_item_bbox(tbl_a),
                    bbox_b=None,
                ))
                continue

            # Cell-level diff with row alignment.
            rows_a = tbl_a.get("data", [])
            rows_b = tbl_b.get("data", [])
            cell_diffs = []
            rows_added = 0
            rows_removed = 0
            has_changes = False

            row_signatures_a = [" | ".join(str(cell or "") for cell in row) for row in rows_a]
            row_signatures_b = [" | ".join(str(cell or "") for cell in row) for row in rows_b]
            row_matcher = difflib.SequenceMatcher(None, row_signatures_a, row_signatures_b)

            def add_row_cell_diffs(row_idx: int, row_a: List[Any], row_b: List[Any]) -> None:
                nonlocal has_changes
                for c in range(max(len(row_a), len(row_b))):
                    val_a = str(row_a[c] or "") if c < len(row_a) else None
                    val_b = str(row_b[c] or "") if c < len(row_b) else None
                    if val_a != val_b:
                        has_changes = True
                        if val_a is None:
                            dtype = DiffType.ADDED
                        elif val_b is None:
                            dtype = DiffType.REMOVED
                        else:
                            dtype = DiffType.CHANGED
                        cell_diffs.append(TableCellDiff(
                            row=row_idx,
                            col=c,
                            value_a=val_a,
                            value_b=val_b,
                            diff_type=dtype,
                        ))

            for tag, i1, i2, j1, j2 in row_matcher.get_opcodes():
                if tag == "equal":
                    continue

                if tag == "delete":
                    rows_removed += (i2 - i1)
                    for row_idx in range(i1, i2):
                        add_row_cell_diffs(row_idx, rows_a[row_idx], [])
                    continue

                if tag == "insert":
                    rows_added += (j2 - j1)
                    for row_idx in range(j1, j2):
                        add_row_cell_diffs(row_idx, [], rows_b[row_idx])
                    continue

                # replace
                overlap = min(i2 - i1, j2 - j1)
                for k in range(overlap):
                    row_idx_a = i1 + k
                    row_idx_b = j1 + k
                    display_idx = max(row_idx_a, row_idx_b)
                    add_row_cell_diffs(display_idx, rows_a[row_idx_a], rows_b[row_idx_b])

                if (i2 - i1) > overlap:
                    rows_removed += ((i2 - i1) - overlap)
                    for row_idx in range(i1 + overlap, i2):
                        add_row_cell_diffs(row_idx, rows_a[row_idx], [])

                if (j2 - j1) > overlap:
                    rows_added += ((j2 - j1) - overlap)
                    for row_idx in range(j1 + overlap, j2):
                        add_row_cell_diffs(row_idx, [], rows_b[row_idx])

            if has_changes or rows_added or rows_removed:
                diffs.append(TableDiff(
                    page=tbl_a.get("page", 0),
                    page_a=tbl_a.get("page"),
                    page_b=tbl_b.get("page"),
                    table_index=table_index,
                    headers_a=_sanitize_list(tbl_a.get("headers")),
                    headers_b=_sanitize_list(tbl_b.get("headers")),
                    cell_diffs=cell_diffs,
                    rows_added=rows_added,
                    rows_removed=rows_removed,
                    diff_type=DiffType.CHANGED,
                    bbox_a=_item_bbox(tbl_a),
                    bbox_b=_item_bbox(tbl_b),
                ))

        return diffs

    # ─── Image Comparison ──────────────────────────────────────────────────────

    def compare_images(self, images_a: List[Dict], images_b: List[Dict]) -> List[ImageDiff]:
        """Compare images page by page using placement-aware matching."""
        diffs = []
        # Group by page
        pages_a: Dict[int, List[Dict]] = {}
        pages_b: Dict[int, List[Dict]] = {}

        for img in images_a:
            pages_a.setdefault(img["page"], []).append(img)
        for img in images_b:
            pages_b.setdefault(img["page"], []).append(img)

        all_pages = sorted(set(list(pages_a.keys()) + list(pages_b.keys())))

        for page in all_pages:
            imgs_a = pages_a.get(page, [])
            imgs_b = pages_b.get(page, [])
            image_pairs = _match_page_images(imgs_a, imgs_b)

            for idx, (img_a, img_b) in enumerate(image_pairs):
                if img_a and img_b:
                    b64_a = img_a.get("data_b64", "")
                    b64_b = img_b.get("data_b64", "")

                    # Only call Gemini for non-page-renders (to limit cost)
                    if img_a.get("is_page_render") or img_b.get("is_page_render"):
                        ai_result = self.gemini.compare_images(b64_a, b64_b)
                        desc_a = f"Page {page} render (Document A)"
                        desc_b = f"Page {page} render (Document B)"
                    else:
                        desc_a = self.gemini.describe_image(b64_a, f"Document A, page {page}")
                        desc_b = self.gemini.describe_image(b64_b, f"Document B, page {page}")
                        ai_result = self.gemini.compare_images(b64_a, b64_b)

                    diff_type = DiffType.UNCHANGED if ai_result.get("are_same") else DiffType.CHANGED
                    diffs.append(ImageDiff(
                        page=page,
                        page_a=img_a.get("page"),
                        page_b=img_b.get("page"),
                        image_index=idx,
                        description_a=desc_a,
                        description_b=desc_b,
                        diff_type=diff_type,
                        ai_analysis=ai_result.get("summary", ""),
                        bbox_a=_item_bbox(img_a),
                        bbox_b=_item_bbox(img_b),
                    ))

                elif img_a:
                    desc_a = self.gemini.describe_image(img_a.get("data_b64", ""), f"Document A, page {page}")
                    diffs.append(ImageDiff(
                        page=page,
                        page_a=img_a.get("page"),
                        page_b=None,
                        image_index=idx,
                        description_a=desc_a,
                        description_b=None,
                        diff_type=DiffType.REMOVED,
                        ai_analysis=f"Image present only in Document A on page {page}.",
                        bbox_a=_item_bbox(img_a),
                        bbox_b=None,
                    ))

                elif img_b:
                    desc_b = self.gemini.describe_image(img_b.get("data_b64", ""), f"Document B, page {page}")
                    diffs.append(ImageDiff(
                        page=page,
                        page_a=None,
                        page_b=img_b.get("page"),
                        image_index=idx,
                        description_a=None,
                        description_b=desc_b,
                        diff_type=DiffType.ADDED,
                        ai_analysis=f"Image present only in Document B on page {page}.",
                        bbox_a=None,
                        bbox_b=_item_bbox(img_b),
                    ))

        return diffs

    def align_pages(
        self,
        data_a: Dict[str, Any],
        data_b: Dict[str, Any],
    ) -> List[PagePair]:
        signatures_a = _page_signatures(data_a)
        signatures_b = _page_signatures(data_b)
        m = len(signatures_a)
        n = len(signatures_b)

        if m == 0 and n == 0:
            return []

        insert_cost = 0.35
        delete_cost = 0.35
        dp = [[0.0] * (n + 1) for _ in range(m + 1)]
        backtrack: List[List[Optional[str]]] = [[None] * (n + 1) for _ in range(m + 1)]

        for i in range(1, m + 1):
            dp[i][0] = i * delete_cost
            backtrack[i][0] = "delete"
        for j in range(1, n + 1):
            dp[0][j] = j * insert_cost
            backtrack[0][j] = "insert"

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                similarity = _similarity(signatures_a[i - 1], signatures_b[j - 1])
                match_cost = dp[i - 1][j - 1] + (1.0 - similarity)
                delete_path = dp[i - 1][j] + delete_cost
                insert_path = dp[i][j - 1] + insert_cost

                best_cost = match_cost
                best_op = "match"
                if delete_path < best_cost:
                    best_cost = delete_path
                    best_op = "delete"
                if insert_path < best_cost:
                    best_cost = insert_path
                    best_op = "insert"

                dp[i][j] = best_cost
                backtrack[i][j] = best_op

        pairs: List[PagePair] = []
        i = m
        j = n
        while i > 0 or j > 0:
            op = backtrack[i][j]
            if op == "match" and i > 0 and j > 0:
                similarity = _similarity(signatures_a[i - 1], signatures_b[j - 1])
                pairs.append(PagePair(
                    slot=0,
                    page_a=i,
                    page_b=j,
                    relation="matched",
                    similarity_score=round(similarity, 3),
                ))
                i -= 1
                j -= 1
            elif op == "delete" and i > 0:
                pairs.append(PagePair(
                    slot=0,
                    page_a=i,
                    page_b=None,
                    relation="removed",
                    similarity_score=0.0,
                ))
                i -= 1
            elif op == "insert" and j > 0:
                pairs.append(PagePair(
                    slot=0,
                    page_a=None,
                    page_b=j,
                    relation="added",
                    similarity_score=0.0,
                ))
                j -= 1
            elif i > 0:
                pairs.append(PagePair(
                    slot=0,
                    page_a=i,
                    page_b=None,
                    relation="removed",
                    similarity_score=0.0,
                ))
                i -= 1
            elif j > 0:
                pairs.append(PagePair(
                    slot=0,
                    page_a=None,
                    page_b=j,
                    relation="added",
                    similarity_score=0.0,
                ))
                j -= 1

        pairs.reverse()
        for slot, pair in enumerate(pairs, 1):
            pair.slot = slot
        return pairs

    def build_viewer_regions(
        self,
        text_diffs: List[TextDiff],
        bullet_diffs: List[TextDiff],
        table_diffs: List[TableDiff],
        image_diffs: List[ImageDiff],
    ) -> List[ViewerRegion]:
        regions: List[ViewerRegion] = []

        for diff in text_diffs + bullet_diffs:
            if diff.diff_type == DiffType.UNCHANGED:
                continue
            if not diff.bbox_a and not diff.bbox_b:
                continue
            regions.append(ViewerRegion(
                page_a=diff.page_a,
                page_b=diff.page_b,
                bbox_a=diff.bbox_a,
                bbox_b=diff.bbox_b,
                change_type=diff.diff_type,
                source=diff.section_type,
                label=_preview_label(diff.content_b, diff.content_a, fallback=diff.section_type.title()),
                similarity_score=diff.similarity_score,
            ))

        for diff in table_diffs:
            if diff.diff_type == DiffType.UNCHANGED:
                continue
            if not diff.bbox_a and not diff.bbox_b:
                continue
            regions.append(ViewerRegion(
                page_a=diff.page_a,
                page_b=diff.page_b,
                bbox_a=diff.bbox_a,
                bbox_b=diff.bbox_b,
                change_type=diff.diff_type,
                source="table",
                label=_preview_label(
                    " ".join(diff.headers_b or []),
                    " ".join(diff.headers_a or []),
                    fallback=f"Table {diff.table_index + 1}",
                ),
                similarity_score=None,
            ))

        for diff in image_diffs:
            if diff.diff_type == DiffType.UNCHANGED:
                continue
            if not diff.bbox_a and not diff.bbox_b:
                continue
            regions.append(ViewerRegion(
                page_a=diff.page_a,
                page_b=diff.page_b,
                bbox_a=diff.bbox_a,
                bbox_b=diff.bbox_b,
                change_type=diff.diff_type,
                source="image",
                label=_preview_label(diff.description_b, diff.description_a, fallback="Image"),
                similarity_score=None,
            ))

        regions.sort(
            key=lambda region: (
                region.page_a if region.page_a is not None else 10**6,
                region.page_b if region.page_b is not None else 10**6,
                region.bbox_a.y0 if region.bbox_a else (region.bbox_b.y0 if region.bbox_b else 1.0),
            )
        )
        return regions

    # ─── Full Comparison ───────────────────────────────────────────────────────

    def compare(
        self,
        data_a: Dict[str, Any],
        data_b: Dict[str, Any],
        file1_name: str,
        file2_name: str,
        page_renders_a: List[str],
        page_renders_b: List[str],
    ) -> ComparisonResult:
        comparison_id = str(uuid.uuid4())

        # --- Text diffs ---
        para_diffs, para_total, para_scores = self.compare_text_blocks(
            data_a.get("paragraphs", []), data_b.get("paragraphs", []), "paragraph"
        )
        heading_diffs, heading_total, heading_scores = self.compare_text_blocks(
            data_a.get("headings", []), data_b.get("headings", []), "heading"
        )
        bullet_diffs, bullet_total, bullet_scores = self.compare_text_blocks(
            data_a.get("bullets", []), data_b.get("bullets", []), "bullet"
        )
        all_text_diffs = para_diffs + heading_diffs
        page_pairs = self.align_pages(data_a, data_b)

        # Sort text and bullet diffs by page + vertical position (top-to-bottom)
        all_text_diffs.sort(key=lambda d: (d.page, d.position))
        bullet_diffs.sort(key=lambda d: (d.page, d.position))

        # --- Table diffs ---
        table_diffs = self.compare_tables(
            data_a.get("tables", []), data_b.get("tables", [])
        )

        # --- Image diffs ---
        image_diffs = self.compare_images(
            data_a.get("images", []), data_b.get("images", [])
        )
        viewer_regions = self.build_viewer_regions(all_text_diffs, bullet_diffs, table_diffs, image_diffs)

        # --- Similarity score ---
        # Weighted average of all individual text similarity scores (including unchanged)
        total_pairs = para_total + heading_total + bullet_total
        total_score_sum = para_scores + heading_scores + bullet_scores
        if total_pairs > 0:
            similarity = round((total_score_sum / total_pairs) * 100, 1)
        else:
            similarity = 100.0  # No text to compare = identical
        similarity = max(0.0, min(100.0, similarity))

        # --- Overall Gemini summary ---
        text_a_combined = " ".join(
            item.get("text", "")
            for key in ("headings", "paragraphs", "bullets")
            for item in data_a.get(key, [])
        )
        text_b_combined = " ".join(
            item.get("text", "")
            for key in ("headings", "paragraphs", "bullets")
            for item in data_b.get(key, [])
        )

        overall_summary = self.gemini.generate_overall_summary(
            file1_name, file2_name,
            page_renders_a, page_renders_b,
            text_a_combined, text_b_combined,
        )

        # --- AI Page-by-Page Comparison (Gemini Vision) ---
        ai_page_diffs: List[PageDiff] = []
        if self.gemini.enabled:
            logger.info("Running Gemini page-by-page visual comparison...")
            raw_page_diffs = self.gemini.compare_pages_sequentially(
                page_renders_a, page_renders_b,
            )
            for d in raw_page_diffs:
                ai_page_diffs.append(PageDiff(
                    page=d.get("page", 0),
                    location=d.get("location", "unknown"),
                    section=d.get("section", ""),
                    change_type=d.get("change_type", "changed"),
                    description=d.get("description", ""),
                    text_in_a=d.get("text_in_a"),
                    text_in_b=d.get("text_in_b"),
                ))
            logger.info(f"Gemini found {len(ai_page_diffs)} page-level differences")

        # --- Stats ---
        stats = {
            "paragraphs_changed": sum(1 for d in para_diffs if d.diff_type == DiffType.CHANGED),
            "paragraphs_added": sum(1 for d in para_diffs if d.diff_type == DiffType.ADDED),
            "paragraphs_removed": sum(1 for d in para_diffs if d.diff_type == DiffType.REMOVED),
            "bullets_changed": sum(1 for d in bullet_diffs if d.diff_type == DiffType.CHANGED),
            "bullets_added": sum(1 for d in bullet_diffs if d.diff_type == DiffType.ADDED),
            "bullets_removed": sum(1 for d in bullet_diffs if d.diff_type == DiffType.REMOVED),
            "tables_changed": len(table_diffs),
            "images_changed": sum(1 for d in image_diffs if d.diff_type == DiffType.CHANGED),
            "images_added": sum(1 for d in image_diffs if d.diff_type == DiffType.ADDED),
            "images_removed": sum(1 for d in image_diffs if d.diff_type == DiffType.REMOVED),
            "formatting_changed": sum(
                1 for d in (all_text_diffs + bullet_diffs) if d.style_changes
            ),
            "layout_changed": sum(
                1 for d in (all_text_diffs + bullet_diffs) if d.layout_changes
            ),
            "doc_a_is_scanned": data_a.get("is_scanned", False),
            "doc_b_is_scanned": data_b.get("is_scanned", False),
        }

        return ComparisonResult(
            comparison_id=comparison_id,
            file1_name=file1_name,
            file2_name=file2_name,
            overall_summary=overall_summary,
            similarity_percentage=similarity,
            text_diffs=all_text_diffs,
            table_diffs=table_diffs,
            image_diffs=image_diffs,
            bullet_diffs=bullet_diffs,
            ai_page_diffs=ai_page_diffs if ai_page_diffs else None,
            page_count_a=data_a.get("page_count", 0),
            page_count_b=data_b.get("page_count", 0),
            viewer_regions=viewer_regions or None,
            page_pairs=page_pairs or None,
            stats=stats,
        )
