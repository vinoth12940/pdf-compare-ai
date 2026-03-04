import difflib
import re
from typing import List, Dict, Any, Tuple, Optional
from models.schemas import DiffType, TextDiff, TableDiff, TableCellDiff, ImageDiff, ComparisonResult
from services.gemini_service import GeminiService
import uuid
import logging

logger = logging.getLogger(__name__)


def _sanitize_list(lst):
    """Convert None values in a list to empty strings (for pdfplumber headers/cells)."""
    if lst is None:
        return None
    return [str(v) if v is not None else "" for v in lst]


def _similarity(a: str, b: str) -> float:
    """Compute normalized similarity ratio between two strings."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _match_items(list_a: List[Dict], list_b: List[Dict], key: str = "text") -> List[Tuple[Optional[Dict], Optional[Dict]]]:
    """
    Greedily match items from list_a to list_b based on text similarity.
    Returns pairs of (a_item, b_item) where None means no match.
    """
    used_b = set()
    pairs = []

    for a_item in list_a:
        best_score = -1
        best_j = -1
        for j, b_item in enumerate(list_b):
            if j in used_b:
                continue
            score = _similarity(a_item.get(key, ""), b_item.get(key, ""))
            if score > best_score:
                best_score = score
                best_j = j

        if best_j >= 0 and best_score > 0.3:
            pairs.append((a_item, list_b[best_j]))
            used_b.add(best_j)
        else:
            pairs.append((a_item, None))

    # Add unmatched b items
    for j, b_item in enumerate(list_b):
        if j not in used_b:
            pairs.append((None, b_item))

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

            score = _similarity(text_a, text_b)
            score_sum += score

            if not a_item:
                diff_type = DiffType.ADDED
            elif not b_item:
                diff_type = DiffType.REMOVED
            elif score >= 0.95:
                diff_type = DiffType.UNCHANGED
            else:
                diff_type = DiffType.CHANGED

            if diff_type != DiffType.UNCHANGED:
                diffs.append(TextDiff(
                    page=page,
                    content_a=text_a,
                    content_b=text_b,
                    diff_type=diff_type,
                    similarity_score=round(score, 3),
                    section_type=section_type,
                ))

        return diffs, total_pairs, score_sum

    # ─── Table Comparison ──────────────────────────────────────────────────────

    def compare_tables(self, tables_a: List[Dict], tables_b: List[Dict]) -> List[TableDiff]:
        diffs = []
        max_tables = max(len(tables_a), len(tables_b))

        for i in range(max_tables):
            tbl_a = tables_a[i] if i < len(tables_a) else None
            tbl_b = tables_b[i] if i < len(tables_b) else None

            if tbl_a is None:
                diffs.append(TableDiff(
                    page=(tbl_b or {}).get("page", 0),
                    table_index=i,
                    headers_a=None,
                    headers_b=_sanitize_list(tbl_b.get("headers")) if tbl_b else None,
                    cell_diffs=[],
                    rows_added=len(tbl_b.get("rows", [])) if tbl_b else 0,
                    rows_removed=0,
                    diff_type=DiffType.ADDED,
                ))
                continue

            if tbl_b is None:
                diffs.append(TableDiff(
                    page=(tbl_a or {}).get("page", 0),
                    table_index=i,
                    headers_a=_sanitize_list(tbl_a.get("headers")) if tbl_a else None,
                    headers_b=None,
                    cell_diffs=[],
                    rows_added=0,
                    rows_removed=len(tbl_a.get("rows", [])) if tbl_a else 0,
                    diff_type=DiffType.REMOVED,
                ))
                continue

            # Cell-level diff
            rows_a = tbl_a.get("data", [])
            rows_b = tbl_b.get("data", [])
            cell_diffs = []
            rows_added = max(0, len(rows_b) - len(rows_a))
            rows_removed = max(0, len(rows_a) - len(rows_b))
            has_changes = False

            for r in range(max(len(rows_a), len(rows_b))):
                row_a = rows_a[r] if r < len(rows_a) else []
                row_b = rows_b[r] if r < len(rows_b) else []

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
                            row=r, col=c,
                            value_a=val_a, value_b=val_b,
                            diff_type=dtype,
                        ))

            if has_changes or rows_added or rows_removed:
                diffs.append(TableDiff(
                    page=tbl_a.get("page", 0),
                    table_index=i,
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
        text_a_combined = " ".join(p["text"] for p in data_a.get("paragraphs", []))
        text_b_combined = " ".join(p["text"] for p in data_b.get("paragraphs", []))

        overall_summary = self.gemini.generate_overall_summary(
            file1_name, file2_name,
            page_renders_a, page_renders_b,
            text_a_combined, text_b_combined,
        )

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
            page_count_a=data_a.get("page_count", 0),
            page_count_b=data_b.get("page_count", 0),
            stats=stats,
        )
