from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from enum import Enum


class DiffType(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"
    UNCHANGED = "unchanged"


class TextDiff(BaseModel):
    page: int
    content_a: str
    content_b: str
    diff_type: DiffType
    similarity_score: float
    section_type: str  # "paragraph", "heading", "bullet"


class TableCellDiff(BaseModel):
    row: int
    col: int
    value_a: Optional[str]
    value_b: Optional[str]
    diff_type: DiffType


class TableDiff(BaseModel):
    page: int
    table_index: int
    headers_a: Optional[List[str]]
    headers_b: Optional[List[str]]
    cell_diffs: List[TableCellDiff]
    rows_added: int
    rows_removed: int
    diff_type: DiffType


class ImageDiff(BaseModel):
    page: int
    image_index: int
    description_a: Optional[str]
    description_b: Optional[str]
    diff_type: DiffType
    ai_analysis: str


class ComparisonResult(BaseModel):
    comparison_id: str
    file1_name: str
    file2_name: str
    overall_summary: str
    similarity_percentage: float
    text_diffs: List[TextDiff]
    table_diffs: List[TableDiff]
    image_diffs: List[ImageDiff]
    bullet_diffs: List[TextDiff]
    page_count_a: int
    page_count_b: int
    page_renders_a: Optional[List[str]] = None
    page_renders_b: Optional[List[str]] = None
    diff_overlay_a: Optional[List[str]] = None
    diff_overlay_b: Optional[List[str]] = None
    stats: Dict[str, Any]


class CompareRequest(BaseModel):
    gemini_api_key: Optional[str] = None
