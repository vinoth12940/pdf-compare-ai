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
    page_count_a: number;
    page_count_b: number;
    page_renders_a?: string[];
    page_renders_b?: string[];
    diff_overlay_a?: string[];
    diff_overlay_b?: string[];
    stats: Record<string, number | boolean>;
}

export interface TextDiff {
    page: number;
    content_a: string;
    content_b: string;
    diff_type: 'added' | 'removed' | 'changed' | 'unchanged';
    similarity_score: number;
    section_type: string;
}

export interface TableDiff {
    page: number;
    table_index: number;
    headers_a: string[] | null;
    headers_b: string[] | null;
    cell_diffs: TableCellDiff[];
    rows_added: number;
    rows_removed: number;
    diff_type: 'added' | 'removed' | 'changed' | 'unchanged';
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
    image_index: number;
    description_a: string | null;
    description_b: string | null;
    diff_type: 'added' | 'removed' | 'changed' | 'unchanged';
    ai_analysis: string;
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
