import difflib
import re
from typing import List, Dict, Any, Tuple, Optional
from models.schemas import DiffType, TextDiff, TableDiff, TableCellDiff, ImageDiff, PageDiff, ComparisonResult
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
                    content_a=text_a,
                    content_b=text_b,
                    diff_type=diff_type,
                    similarity_score=round(score, 3),
                    section_type=section_type,
                    style_changes=style_changes or None,
                    layout_changes=layout_changes or None,
                    position=round(float(position), 2),
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
                    table_index=table_index,
                    headers_a=None,
                    headers_b=_sanitize_list(tbl_b.get("headers")) if tbl_b else None,
                    cell_diffs=[],
                    rows_added=len(added_rows) if tbl_b else 0,
                    rows_removed=0,
                    diff_type=DiffType.ADDED,
                ))
                continue

            if tbl_b is None:
                removed_rows = tbl_a.get("rows") or tbl_a.get("data") or []
                diffs.append(TableDiff(
                    page=(tbl_a or {}).get("page", 0),
                    table_index=table_index,
                    headers_a=_sanitize_list(tbl_a.get("headers")) if tbl_a else None,
                    headers_b=None,
                    cell_diffs=[],
                    rows_added=0,
                    rows_removed=len(removed_rows) if tbl_a else 0,
                    diff_type=DiffType.REMOVED,
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
                    table_index=table_index,
                    headers_a=_sanitize_list(tbl_a.get("headers")),
                    headers_b=_sanitize_list(tbl_b.get("headers")),
                    cell_diffs=cell_diffs,
                    rows_added=rows_added,
                    rows_removed=rows_removed,
                    diff_type=DiffType.CHANGED,
                ))

        return diffs

    # ─── Image Comparison ──────────────────────────────────────────────────────

    def compare_images(self, images_a: List[Dict], images_b: List[Dict]) -> List[ImageDiff]:
        """Compare images page by page. Use Gemini Vision where available."""
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

            max_imgs = max(len(imgs_a), len(imgs_b))
            for idx in range(max_imgs):
                img_a = imgs_a[idx] if idx < len(imgs_a) else None
                img_b = imgs_b[idx] if idx < len(imgs_b) else None

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
                        image_index=idx,
                        description_a=desc_a,
                        description_b=desc_b,
                        diff_type=diff_type,
                        ai_analysis=ai_result.get("summary", ""),
                    ))

                elif img_a:
                    desc_a = self.gemini.describe_image(img_a.get("data_b64", ""), f"Document A, page {page}")
                    diffs.append(ImageDiff(
                        page=page,
                        image_index=idx,
                        description_a=desc_a,
                        description_b=None,
                        diff_type=DiffType.REMOVED,
                        ai_analysis=f"Image present only in Document A on page {page}.",
                    ))

                else:
                    desc_b = self.gemini.describe_image(img_b.get("data_b64", ""), f"Document B, page {page}")
                    diffs.append(ImageDiff(
                        page=page,
                        image_index=idx,
                        description_a=None,
                        description_b=desc_b,
                        diff_type=DiffType.ADDED,
                        ai_analysis=f"Image present only in Document B on page {page}.",
                    ))

        return diffs

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
            stats=stats,
        )
