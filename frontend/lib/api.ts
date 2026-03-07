import axios from 'axios';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface ComparisonResult {
    comparison_id: string;
    file1_name: string;
    file2_name: string;
    overall_summary: string;
    similarity_percentage: number;
    text_diffs: TextDiff[];
    table_diffs: TableDiff[];
    image_diffs: ImageDiff[];
    bullet_diffs: TextDiff[];
    ai_page_diffs?: PageDiff[] | null;
    page_count_a: number;
    page_count_b: number;
    page_renders_a?: string[];
    page_renders_b?: string[];
    diff_overlay_a?: string[];
    diff_overlay_b?: string[];
    viewer_regions?: ViewerRegion[] | null;
    page_pairs?: PagePair[] | null;
    stats: Record<string, number | boolean>;
}

export interface BoundingBox {
    x0: number;
    y0: number;
    x1: number;
    y1: number;
}

export interface TextDiff {
    page: number;
    page_a?: number | null;
    page_b?: number | null;
    content_a: string;
    content_b: string;
    diff_type: 'added' | 'removed' | 'changed' | 'unchanged';
    similarity_score: number;
    section_type: string;
    style_changes?: string[] | null;
    layout_changes?: string[] | null;
    bbox_a?: BoundingBox | null;
    bbox_b?: BoundingBox | null;
}

export interface TableDiff {
    page: number;
    page_a?: number | null;
    page_b?: number | null;
    table_index: number;
    headers_a: string[] | null;
    headers_b: string[] | null;
    cell_diffs: TableCellDiff[];
    rows_added: number;
    rows_removed: number;
    diff_type: 'added' | 'removed' | 'changed' | 'unchanged';
    bbox_a?: BoundingBox | null;
    bbox_b?: BoundingBox | null;
}

export interface TableCellDiff {
    row: number;
    col: number;
    value_a: string | null;
    value_b: string | null;
    diff_type: 'added' | 'removed' | 'changed' | 'unchanged';
}

export interface ImageDiff {
    page: number;
    page_a?: number | null;
    page_b?: number | null;
    image_index: number;
    description_a: string | null;
    description_b: string | null;
    diff_type: 'added' | 'removed' | 'changed' | 'unchanged';
    ai_analysis: string;
    bbox_a?: BoundingBox | null;
    bbox_b?: BoundingBox | null;
}

export interface PageDiff {
    page: number;
    location: string;
    section: string;
    change_type: 'added' | 'removed' | 'changed';
    description: string;
    text_in_a: string | null;
    text_in_b: string | null;
}

export interface ViewerRegion {
    page_a?: number | null;
    page_b?: number | null;
    bbox_a?: BoundingBox | null;
    bbox_b?: BoundingBox | null;
    change_type: 'added' | 'removed' | 'changed' | 'unchanged';
    source: string;
    label: string;
    similarity_score?: number | null;
}

export interface PagePair {
    slot: number;
    page_a?: number | null;
    page_b?: number | null;
    relation: string;
    similarity_score: number;
}

export async function comparePDFs(
    file1: File,
    file2: File,
    geminiApiKey: string,
    onProgress?: (pct: number) => void
): Promise<ComparisonResult> {
    const formData = new FormData();
    formData.append('file1', file1);
    formData.append('file2', file2);
    formData.append('gemini_api_key', geminiApiKey);

    const response = await axios.post<ComparisonResult>(`${API_BASE}/compare`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
            if (e.total && onProgress) {
                onProgress(Math.round((e.loaded / e.total) * 30));
            }
        },
        timeout: 300000, // 5 min timeout for large files
    });

    return response.data;
}
