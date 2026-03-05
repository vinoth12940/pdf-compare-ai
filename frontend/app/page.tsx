'use client';

import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import {
    FileText, Upload, CheckCircle, AlertCircle,
    ChevronDown, ChevronUp, Download, Loader2,
    Table2, Image as ImageIcon, List, AlignLeft,
    Key, Eye, ArrowLeft, ArrowRight, ScanSearch, Zap, X, Paintbrush
} from 'lucide-react';
import { comparePDFs, ComparisonResult, TextDiff, TableDiff, ImageDiff, PageDiff } from '@/lib/api';
import axios from 'axios';

/* ═══════════════════════════════════════════════════════════════
   Sub-Components
   ═══════════════════════════════════════════════════════════════ */

function FileDropzone({ label, variant, file, onFile }: {
    label: string; variant: 'a' | 'b'; file: File | null; onFile: (f: File) => void;
}) {
    const onDrop = useCallback((a: File[]) => { if (a[0]) onFile(a[0]); }, [onFile]);
    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop, accept: { 'application/pdf': ['.pdf'] }, multiple: false,
    });

    return (
        <div {...getRootProps()} className={`dropzone ${isDragActive ? 'active' : ''} ${file ? 'has-file' : ''}`}>
            <input {...getInputProps()} />
            <div className={`dropzone-label ${variant === 'a' ? 'doc-a' : 'doc-b'}`}>{label}</div>
            <div className="dropzone-icon">
                {file
                    ? <CheckCircle size={20} color="var(--green)" />
                    : <Upload size={20} color="var(--text-ghost)" />}
            </div>
            {file ? (
                <>
                    <div className="dropzone-file">{file.name}</div>
                    <div className="dropzone-meta">{(file.size / 1024 / 1024).toFixed(2)} MB · Click to replace</div>
                </>
            ) : (
                <>
                    <div className="dropzone-title">Drop PDF here</div>
                    <div className="dropzone-hint">or click to browse</div>
                </>
            )}
        </div>
    );
}

function SideBySideViewer({ result }: { result: ComparisonResult }) {
    const [page, setPage] = useState(0);
    const [showOverlay, setShowOverlay] = useState(true);
    const maxPages = Math.max(result.page_count_a, result.page_count_b);
    const hasOverlay = !!(result.diff_overlay_a?.length || result.diff_overlay_b?.length);
    const imgA = showOverlay && hasOverlay
        ? (result.diff_overlay_a?.[page] || result.page_renders_a?.[page])
        : result.page_renders_a?.[page];
    const imgB = showOverlay && hasOverlay
        ? (result.diff_overlay_b?.[page] || result.page_renders_b?.[page])
        : result.page_renders_b?.[page];

    return (
        <div className="sbs-viewer">
            <div className="sbs-header">
                <button className="btn-icon" disabled={page === 0} onClick={() => setPage(p => Math.max(0, p - 1))}>
                    <ArrowLeft size={14} />
                </button>
                <div style={{ display: 'flex', gap: 3 }}>
                    {Array.from({ length: maxPages }, (_, i) => (
                        <button key={i} onClick={() => setPage(i)} className={`page-dot ${page === i ? 'active' : ''}`}>
                            {i + 1}
                        </button>
                    ))}
                </div>
                <button className="btn-icon" disabled={page >= maxPages - 1} onClick={() => setPage(p => Math.min(maxPages - 1, p + 1))}>
                    <ArrowRight size={14} />
                </button>
                <span style={{ color: 'var(--text-ghost)', fontSize: 11, marginLeft: 4, fontFamily: "'Geist Mono', monospace" }}>
                    {page + 1}/{maxPages}
                </span>
                {hasOverlay && (
                    <button
                        onClick={() => setShowOverlay(v => !v)}
                        style={{
                            marginLeft: 'auto',
                            padding: '4px 10px',
                            fontSize: 11,
                            fontFamily: "'Geist Mono', monospace",
                            borderRadius: 6,
                            border: '1px solid var(--border)',
                            background: showOverlay ? 'var(--accent)' : 'var(--bg-card)',
                            color: showOverlay ? '#fff' : 'var(--text-secondary)',
                            cursor: 'pointer',
                            transition: 'all 0.15s ease',
                        }}
                    >
                        {showOverlay ? '● Diff Overlay ON' : '○ Diff Overlay OFF'}
                    </button>
                )}
            </div>
            <div className="sbs-panels">
                <div className="sbs-panel">
                    {imgA ? <img src={`data:image/png;base64,${imgA}`} alt={`Doc A page ${page + 1}`} /> : <EmptyPage />}
                </div>
                <div className="sbs-panel">
                    {imgB ? <img src={`data:image/png;base64,${imgB}`} alt={`Doc B page ${page + 1}`} /> : <EmptyPage />}
                </div>
            </div>
        </div>
    );
}

function EmptyPage() {
    return (
        <div style={{ color: 'var(--text-ghost)', fontSize: 12, padding: 40, textAlign: 'center' }}>
            No page render available
        </div>
    );
}

/* ── Word-level diff helper ── */
function getWordDiffParts(textA: string, textB: string): {
    partsA: Array<{ text: string; highlight: boolean }>;
    partsB: Array<{ text: string; highlight: boolean }>;
} {
    if (!textA && !textB) return { partsA: [], partsB: [] };
    if (!textA) return { partsA: [], partsB: [{ text: textB, highlight: true }] };
    if (!textB) return { partsA: [{ text: textA, highlight: true }], partsB: [] };

    const wordsA = textA.split(/\s+/).filter(Boolean);
    const wordsB = textB.split(/\s+/).filter(Boolean);
    const m = wordsA.length, n = wordsB.length;

    // Bail out for very long texts
    if (m > 400 || n > 400) {
        return {
            partsA: [{ text: textA, highlight: true }],
            partsB: [{ text: textB, highlight: true }],
        };
    }

    // LCS table
    const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
    for (let i = 1; i <= m; i++) {
        for (let j = 1; j <= n; j++) {
            dp[i][j] = wordsA[i - 1].toLowerCase() === wordsB[j - 1].toLowerCase()
                ? dp[i - 1][j - 1] + 1
                : Math.max(dp[i - 1][j], dp[i][j - 1]);
        }
    }

    // Backtrack
    let i = m, j = n;
    const seqA: { word: string; hl: boolean }[] = [];
    const seqB: { word: string; hl: boolean }[] = [];
    while (i > 0 || j > 0) {
        if (i > 0 && j > 0 && wordsA[i - 1].toLowerCase() === wordsB[j - 1].toLowerCase()) {
            seqA.unshift({ word: wordsA[i - 1], hl: false });
            seqB.unshift({ word: wordsB[j - 1], hl: false });
            i--; j--;
        } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
            seqB.unshift({ word: wordsB[j - 1], hl: true });
            j--;
        } else if (i > 0) {
            seqA.unshift({ word: wordsA[i - 1], hl: true });
            i--;
        } else break;
    }

    // Merge consecutive same-type words
    const merge = (seq: { word: string; hl: boolean }[]) => {
        const result: { text: string; highlight: boolean }[] = [];
        for (const { word, hl } of seq) {
            const last = result[result.length - 1];
            if (last && last.highlight === hl) {
                last.text += ' ' + word;
            } else {
                result.push({ text: word, highlight: hl });
            }
        }
        return result;
    };

    return { partsA: merge(seqA), partsB: merge(seqB) };
}

function HighlightedText({ parts, variant }: {
    parts: Array<{ text: string; highlight: boolean }>;
    variant: 'a' | 'b';
}) {
    if (parts.length === 0) return <span style={{ color: 'var(--text-ghost)', fontStyle: 'italic' }}>empty</span>;
    return (
        <>
            {parts.map((part, i) =>
                part.highlight
                    ? <mark key={i} className={`word-diff-${variant}`}>{part.text}</mark>
                    : <span key={i}>{part.text} </span>
            )}
        </>
    );
}

function TextDiffCard({ diff }: { diff: TextDiff }) {
    const [open, setOpen] = useState(diff.diff_type !== 'unchanged');
    const styleChanges = diff.style_changes || [];
    const layoutChanges = diff.layout_changes || [];
    const hasFormatting = styleChanges.length > 0 || layoutChanges.length > 0;
    const { partsA, partsB } = diff.diff_type === 'changed'
        ? getWordDiffParts(diff.content_a, diff.content_b)
        : { partsA: diff.content_a ? [{ text: diff.content_a, highlight: false }] : [], partsB: diff.content_b ? [{ text: diff.content_b, highlight: false }] : [] };
    return (
        <div className="diff-card animate-in">
            <div className="diff-card-header" onClick={() => setOpen(!open)}>
                <div className="diff-card-header-left">
                    <AlignLeft size={14} color="var(--text-ghost)" />
                    <span style={{ color: 'var(--text-tertiary)', fontFamily: "'Geist Mono', monospace" }}>p.{diff.page}</span>
                    <span className={`badge badge-${diff.diff_type}`}>{diff.diff_type}</span>
                    <span style={{ color: 'var(--text-ghost)', fontFamily: "'Geist Mono', monospace", fontSize: 11 }}>
                        {Math.round(diff.similarity_score * 100)}%
                    </span>
                    {hasFormatting && <span className="badge badge-changed">format/layout</span>}
                </div>
                {open ? <ChevronUp size={14} color="var(--text-ghost)" /> : <ChevronDown size={14} color="var(--text-ghost)" />}
            </div>
            {open && (
                <div className="diff-card-body">
                    <div className="diff-grid">
                        <div className={`diff-col ${diff.diff_type === 'removed' ? 'removed' : diff.diff_type === 'changed' ? 'removed' : ''}`}>
                            <div className="diff-col-label a">Document A</div>
                            <HighlightedText parts={partsA} variant="a" />
                        </div>
                        <div className={`diff-col ${diff.diff_type === 'added' ? 'added' : diff.diff_type === 'changed' ? 'added' : ''}`}>
                            <div className="diff-col-label b">Document B</div>
                            <HighlightedText parts={partsB} variant="b" />
                        </div>
                    </div>
                    {hasFormatting && (
                        <div style={{ marginTop: 12, display: 'grid', gap: 6 }}>
                            {styleChanges.length > 0 && (
                                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                                    <strong style={{ color: 'var(--text-primary)' }}>Formatting:</strong> {styleChanges.join(' · ')}
                                </div>
                            )}
                            {layoutChanges.length > 0 && (
                                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                                    <strong style={{ color: 'var(--text-primary)' }}>Layout:</strong> {layoutChanges.join(' · ')}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

function TableDiffCard({ diff }: { diff: TableDiff }) {
    const [open, setOpen] = useState(true);
    const allHeaders = [...new Set([...(diff.headers_a || []), ...(diff.headers_b || [])])];

    return (
        <div className="diff-card animate-in">
            <div className="diff-card-header" onClick={() => setOpen(!open)}>
                <div className="diff-card-header-left">
                    <Table2 size={14} color="var(--text-ghost)" />
                    <span style={{ color: 'var(--text-tertiary)', fontFamily: "'Geist Mono', monospace" }}>p.{diff.page}</span>
                    <span className={`badge badge-${diff.diff_type}`}>{diff.diff_type}</span>
                    {diff.rows_added > 0 && <span style={{ color: 'var(--green)', fontSize: 11 }}>+{diff.rows_added}</span>}
                    {diff.rows_removed > 0 && <span style={{ color: 'var(--red)', fontSize: 11 }}>-{diff.rows_removed}</span>}
                </div>
                {open ? <ChevronUp size={14} color="var(--text-ghost)" /> : <ChevronDown size={14} color="var(--text-ghost)" />}
            </div>
            {open && (
                <div className="diff-card-body" style={{ overflowX: 'auto' }}>
                    <table className="table-diff">
                        <thead>
                            <tr>{allHeaders.map((h, i) => <th key={i}>{h}</th>)}</tr>
                        </thead>
                        <tbody>
                            {diff.cell_diffs && buildTableRows(diff.cell_diffs, allHeaders.length).map((row, ri) => (
                                <tr key={ri}>
                                    {row.map((cell, ci) => (
                                        <td key={ci} className={cell ? `cell-${cell.diff_type === 'changed' ? 'changed-b' : cell.diff_type}` : ''}>
                                            {cell ? (cell.value_b ?? cell.value_a ?? '') : ''}
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}

function buildTableRows(cells: { row: number; col: number; value_a: string | null; value_b: string | null; diff_type: string }[], cols: number) {
    const rowMap = new Map<number, (typeof cells[0] | null)[]>();
    cells.forEach(c => {
        if (!rowMap.has(c.row)) rowMap.set(c.row, Array(cols).fill(null));
        const arr = rowMap.get(c.row)!;
        if (c.col < cols) arr[c.col] = c;
    });
    return Array.from(rowMap.values());
}

function ImageDiffCard({ diff }: { diff: ImageDiff }) {
    return (
        <div className="diff-card animate-in">
            <div className="diff-card-header">
                <div className="diff-card-header-left">
                    <ImageIcon size={14} color="var(--text-ghost)" />
                    <span style={{ color: 'var(--text-tertiary)', fontFamily: "'Geist Mono', monospace" }}>p.{diff.page}</span>
                    <span className={`badge badge-${diff.diff_type}`}>{diff.diff_type}</span>
                </div>
            </div>
            <div className="diff-card-body" style={{ padding: 16 }}>
                <div style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--text-secondary)' }}>{diff.ai_analysis}</div>
            </div>
        </div>
    );
}

function AIDiffCard({ diff, index }: { diff: PageDiff; index: number }) {
    const [open, setOpen] = useState(true);
    const changeIcon = diff.change_type === 'added' ? '+'
        : diff.change_type === 'removed' ? '−'
        : '~';

    return (
        <div className="ai-diff-card animate-in">
            <div className="ai-diff-header" onClick={() => setOpen(!open)}>
                <div className="ai-diff-header-left">
                    <span className={`ai-diff-icon ai-diff-icon-${diff.change_type}`}>{changeIcon}</span>
                    <span className="ai-diff-page">Page {diff.page}</span>
                    <span className="ai-diff-location">{diff.location}</span>
                    <span className={`badge badge-${diff.change_type}`}>{diff.change_type}</span>
                    {diff.section && (
                        <span style={{ color: 'var(--text-tertiary)', fontSize: 12, fontWeight: 500 }}>
                            {diff.section}
                        </span>
                    )}
                </div>
                {open ? <ChevronUp size={14} color="var(--text-ghost)" /> : <ChevronDown size={14} color="var(--text-ghost)" />}
            </div>
            {open && (
                <div className="ai-diff-body">
                    <div className="ai-diff-description">{diff.description}</div>
                    {(diff.text_in_a || diff.text_in_b) && (
                        <div className="ai-diff-text-grid">
                            {diff.text_in_a && (
                                <div className="ai-diff-text-block removed">
                                    <div className="ai-diff-text-label">Document A</div>
                                    <div className="ai-diff-text-content">{diff.text_in_a}</div>
                                </div>
                            )}
                            {diff.text_in_b && (
                                <div className="ai-diff-text-block added">
                                    <div className="ai-diff-text-label">Document B</div>
                                    <div className="ai-diff-text-content">{diff.text_in_b}</div>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

function SimilarityGauge({ value }: { value: number }) {
    const circumference = 2 * Math.PI * 42;
    const offset = circumference - (value / 100) * circumference;
    const color = value >= 80 ? 'var(--green)' : value >= 50 ? 'var(--amber)' : 'var(--red)';

    return (
        <div className="similarity-gauge">
            <div className="gauge-ring">
                <svg viewBox="0 0 100 100">
                    <circle className="track" cx="50" cy="50" r="42" />
                    <circle className="fill" cx="50" cy="50" r="42"
                        stroke={color}
                        strokeDasharray={circumference}
                        strokeDashoffset={offset}
                    />
                </svg>
                <div className="gauge-value" style={{ color }}>{Math.round(value)}%</div>
            </div>
            <div style={{ color: 'var(--text-ghost)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: '0.8px' }}>
                Similarity
            </div>
        </div>
    );
}

/* ═══════════════════════════════════════════════════════════════
   Main Page
   ═══════════════════════════════════════════════════════════════ */

type Tab = 'ai-analysis' | 'viewer' | 'summary' | 'paragraphs' | 'bullets' | 'formatting' | 'tables' | 'images';

export default function Home() {
    const [file1, setFile1] = useState<File | null>(null);
    const [file2, setFile2] = useState<File | null>(null);
    const [apiKey, setApiKey] = useState('');
    const [loading, setLoading] = useState(false);
    const [progress, setProgress] = useState(0);
    const [statusMsg, setStatusMsg] = useState('');
    const [error, setError] = useState('');
    const [result, setResult] = useState<ComparisonResult | null>(null);
    const [activeTab, setActiveTab] = useState<Tab>('ai-analysis');

    const canCompare = file1 && file2 && !loading;

    const handleCompare = async () => {
        if (!file1 || !file2) return;
        setLoading(true); setError(''); setProgress(0); setResult(null);
        setStatusMsg('Uploading documents…');
        try {
            setProgress(15);
            setStatusMsg('Analyzing with Gemini AI…');
            const r = await comparePDFs(file1, file2, apiKey, (pct: number) => {
                setProgress(pct);
                if (pct < 30) setStatusMsg('Uploading documents…');
                else if (pct < 60) setStatusMsg('Extracting content…');
                else setStatusMsg('Comparing differences…');
            });
            setProgress(100);
            setStatusMsg('');
            setResult(r);
            setActiveTab('ai-analysis');
        } catch (err: unknown) {
            if (axios.isAxiosError(err)) {
                setError(err.response?.data?.detail || err.message);
            } else if (err instanceof Error) {
                setError(err.message);
            } else {
                setError('An unexpected error occurred');
            }
        } finally {
            setLoading(false);
        }
    };

    const handleDownload = () => {
        if (!result) return;
        const html = generateReportHTML(result);
        const blob = new Blob([html], { type: 'text/html' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = `comparison-report-${Date.now()}.html`;
        a.click(); URL.revokeObjectURL(url);
    };

    const handleReset = () => {
        setResult(null); setFile1(null); setFile2(null);
        setError(''); setProgress(0); setStatusMsg('');
    };

    /* ── Derived data ── */
    const changedTextDiffs = result?.text_diffs.filter((d: TextDiff) => d.diff_type !== 'unchanged') || [];
    const changedBulletDiffs = result?.bullet_diffs.filter((d: TextDiff) => d.diff_type !== 'unchanged') || [];
    const formattingDiffs = [...changedTextDiffs, ...changedBulletDiffs].filter(
        (d: TextDiff) => (d.style_changes && d.style_changes.length > 0)
            || (d.layout_changes && d.layout_changes.length > 0)
    );

    const aiPageDiffs = result?.ai_page_diffs || [];

    const tabs: { key: Tab; label: string; icon: React.ReactNode; count?: number }[] = [
        { key: 'ai-analysis', label: 'AI Analysis', icon: <Zap size={13} />, count: aiPageDiffs.length },
        { key: 'viewer', label: 'Side by Side', icon: <Eye size={13} /> },
        { key: 'summary', label: 'Summary', icon: <ScanSearch size={13} /> },
        { key: 'paragraphs', label: 'Paragraphs', icon: <AlignLeft size={13} />, count: changedTextDiffs.length },
        { key: 'bullets', label: 'Bullets', icon: <List size={13} />, count: changedBulletDiffs.length },
        { key: 'formatting', label: 'Format/Layout', icon: <Paintbrush size={13} />, count: formattingDiffs.length },
        { key: 'tables', label: 'Tables', icon: <Table2 size={13} />, count: result?.table_diffs.length },
        { key: 'images', label: 'Images', icon: <ImageIcon size={13} />, count: result?.image_diffs.filter((d: ImageDiff) => d.diff_type !== 'unchanged').length },
    ];

    return (
        <div className="app-shell">
            {/* ── Top bar ── */}
            <div className="topbar">
                <div className="topbar-left">
                    <div className="topbar-logo">
                        <FileText size={15} color="white" strokeWidth={2.5} />
                    </div>
                    <span className="topbar-title">PDF Compare AI</span>
                    <span className="topbar-badge">Gemini</span>
                </div>
                <div className="topbar-right">
                    {result && (
                        <>
                            <button className="btn btn-secondary" style={{ height: 30, fontSize: 12 }} onClick={handleDownload}>
                                <Download size={13} /> Export Report
                            </button>
                            <button className="btn btn-ghost" style={{ height: 30, fontSize: 12 }} onClick={handleReset}>
                                <X size={13} /> New
                            </button>
                        </>
                    )}
                </div>
            </div>

            {/* ── Workspace ── */}
            <div className="workspace">
                {!result && !loading && (
                    /* ═══ Upload View ═══ */
                    <div className="upload-view">
                        <div className="upload-hero">
                            <h1>Compare PDFs with AI</h1>
                            <p>
                                Upload two documents and let Gemini AI detect every text, table, image,
                                and layout difference — including scanned PDFs via OCR.
                            </p>
                        </div>
                        <div className="upload-grid">
                            <FileDropzone label="Document A" variant="a" file={file1} onFile={setFile1} />
                            <FileDropzone label="Document B" variant="b" file={file2} onFile={setFile2} />
                        </div>
                        <div className="upload-footer">
                            <div className="api-key-bar">
                                <label><Key size={13} /> API Key</label>
                                <input
                                    className="api-key-input"
                                    type="password"
                                    placeholder="Gemini API key (optional if set in .env)"
                                    value={apiKey}
                                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setApiKey(e.target.value)}
                                />
                            </div>
                            <button
                                className="btn btn-primary btn-lg btn-full"
                                disabled={!canCompare}
                                onClick={handleCompare}
                            >
                                <Zap size={16} /> Compare Documents
                            </button>
                            {error && (
                                <div className="alert alert-error">
                                    <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
                                    <span>{error}</span>
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {loading && (
                    /* ═══ Loading state ═══ */
                    <div className="loading-state">
                        <div className="loading-spinner" />
                        <div style={{ width: 200 }}>
                            <div className="progress-bar"><div className="progress-fill" style={{ width: `${progress}%` }} /></div>
                        </div>
                        <div className="loading-text">
                            {statusMsg}<br />
                            <span style={{ fontSize: 11, color: 'var(--text-ghost)' }}>This may take up to a minute for large files</span>
                        </div>
                    </div>
                )}

                {result && !loading && (
                    /* ═══ Results View ═══ */
                    <div className="results-view">
                        {/* Results toolbar */}
                        <div className="results-toolbar">
                            <div className="results-tabs">
                                {tabs.map(t => (
                                    <button
                                        key={t.key}
                                        className={`tab ${activeTab === t.key ? 'active' : ''}`}
                                        onClick={() => setActiveTab(t.key)}
                                    >
                                        {t.icon}
                                        {t.label}
                                        {t.count !== undefined && t.count > 0 && (
                                            <span className="count">{t.count}</span>
                                        )}
                                    </button>
                                ))}
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <span style={{ color: 'var(--text-ghost)', fontSize: 11, fontFamily: "'Geist Mono', monospace" }}>
                                    {result.file1_name} ↔ {result.file2_name}
                                </span>
                            </div>
                        </div>

                        {/* Results body */}
                        <div className="results-body">
                            {/* Stats sidebar */}
                            <div className="stats-sidebar">
                                <SimilarityGauge value={result.similarity_percentage} />

                                <div className="stats-section">
                                    <div className="stats-section-title">Overview</div>
                                    <div className="stat-item">
                                        <span className="stat-label"><FileText size={12} /> Pages (A)</span>
                                        <span className="stat-value">{result.page_count_a}</span>
                                    </div>
                                    <div className="stat-item">
                                        <span className="stat-label"><FileText size={12} /> Pages (B)</span>
                                        <span className="stat-value">{result.page_count_b}</span>
                                    </div>
                                </div>

                                <div className="stats-section">
                                    <div className="stats-section-title">Differences</div>
                                    <div className="stat-item">
                                        <span className="stat-label"><AlignLeft size={12} /> Paragraphs</span>
                                        <span className={`stat-value ${changedTextDiffs.length > 0 ? 'amber' : 'green'}`}>
                                            {changedTextDiffs.length}
                                        </span>
                                    </div>
                                    <div className="stat-item">
                                        <span className="stat-label"><List size={12} /> Bullets</span>
                                        <span className={`stat-value ${changedBulletDiffs.length > 0 ? 'amber' : 'green'}`}>
                                            {changedBulletDiffs.length}
                                        </span>
                                    </div>
                                    <div className="stat-item">
                                        <span className="stat-label"><Table2 size={12} /> Tables</span>
                                        <span className={`stat-value ${(result.table_diffs.length) > 0 ? 'amber' : 'green'}`}>
                                            {result.table_diffs.length}
                                        </span>
                                    </div>
                                    <div className="stat-item">
                                        <span className="stat-label"><Paintbrush size={12} /> Format/Layout</span>
                                        <span className={`stat-value ${formattingDiffs.length > 0 ? 'amber' : 'green'}`}>
                                            {formattingDiffs.length}
                                        </span>
                                    </div>
                                    <div className="stat-item">
                                        <span className="stat-label"><ImageIcon size={12} /> Images</span>
                                        <span className={`stat-value ${result.image_diffs.filter((d: ImageDiff) => d.diff_type !== 'unchanged').length > 0 ? 'amber' : 'green'}`}>
                                            {result.image_diffs.filter((d: ImageDiff) => d.diff_type !== 'unchanged').length}
                                        </span>
                                    </div>
                                </div>
                            </div>

                            {/* Content area */}
                            <div className="content-area">
                                {activeTab === 'ai-analysis' && (
                                    <div style={{ maxWidth: 900 }}>
                                        <div className="section-heading">
                                            <Zap size={15} /> Gemini AI Analysis — Page-by-Page Differences
                                            <span className="badge badge-changed" style={{ marginLeft: 4 }}>{aiPageDiffs.length}</span>
                                        </div>
                                        {aiPageDiffs.length === 0
                                            ? <div className="summary-block" style={{ color: 'var(--text-ghost)' }}>
                                                No differences detected by AI analysis, or Gemini API key not provided.
                                            </div>
                                            : (() => {
                                                // Group by page for better top-to-bottom display
                                                const pages = new Map<number, PageDiff[]>();
                                                aiPageDiffs.forEach((d: PageDiff) => {
                                                    if (!pages.has(d.page)) pages.set(d.page, []);
                                                    pages.get(d.page)!.push(d);
                                                });
                                                return Array.from(pages.entries()).map(([pageNum, diffs]) => (
                                                    <div key={pageNum} style={{ marginBottom: 24 }}>
                                                        <div className="ai-page-group-header">
                                                            <FileText size={13} />
                                                            Page {pageNum}
                                                            <span style={{ color: 'var(--text-ghost)', fontWeight: 400 }}>
                                                                — {diffs.length} difference{diffs.length !== 1 ? 's' : ''}
                                                            </span>
                                                        </div>
                                                        {diffs.map((d: PageDiff, i: number) => (
                                                            <AIDiffCard key={`${pageNum}-${i}`} diff={d} index={i} />
                                                        ))}
                                                    </div>
                                                ));
                                            })()}
                                    </div>
                                )}

                                {activeTab === 'viewer' && <SideBySideViewer result={result} />}

                                {activeTab === 'summary' && (
                                    <div style={{ maxWidth: 800 }}>
                                        <div className="section-heading"><ScanSearch size={15} /> AI Summary</div>
                                        <div className="summary-block">{result.overall_summary}</div>
                                    </div>
                                )}

                                {activeTab === 'paragraphs' && (
                                    <div style={{ maxWidth: 900 }}>
                                        <div className="section-heading">
                                            <AlignLeft size={15} /> Paragraph Differences
                                            <span className="badge badge-changed" style={{ marginLeft: 4 }}>{changedTextDiffs.length}</span>
                                        </div>
                                        {changedTextDiffs.length === 0
                                            ? <p style={{ color: 'var(--text-ghost)' }}>No paragraph differences found.</p>
                                            : changedTextDiffs.map((d: TextDiff, i: number) => <TextDiffCard key={i} diff={d} />)}
                                    </div>
                                )}

                                {activeTab === 'bullets' && (
                                    <div style={{ maxWidth: 900 }}>
                                        <div className="section-heading">
                                            <List size={15} /> Bullet Point Differences
                                            <span className="badge badge-changed" style={{ marginLeft: 4 }}>{changedBulletDiffs.length}</span>
                                        </div>
                                        {changedBulletDiffs.length === 0
                                            ? <p style={{ color: 'var(--text-ghost)' }}>No bullet point differences found.</p>
                                            : changedBulletDiffs.map((d: TextDiff, i: number) => <TextDiffCard key={i} diff={d} />)}
                                    </div>
                                )}

                                {activeTab === 'formatting' && (
                                    <div style={{ maxWidth: 900 }}>
                                        <div className="section-heading">
                                            <Paintbrush size={15} /> Formatting & Layout Differences
                                            <span className="badge badge-changed" style={{ marginLeft: 4 }}>{formattingDiffs.length}</span>
                                        </div>
                                        {formattingDiffs.length === 0
                                            ? <p style={{ color: 'var(--text-ghost)' }}>No formatting or spacing differences found.</p>
                                            : formattingDiffs.map((d: TextDiff, i: number) => <TextDiffCard key={i} diff={d} />)}
                                    </div>
                                )}

                                {activeTab === 'tables' && (
                                    <div style={{ maxWidth: 900 }}>
                                        <div className="section-heading">
                                            <Table2 size={15} /> Table Differences
                                            <span className="badge badge-changed" style={{ marginLeft: 4 }}>{result.table_diffs.length}</span>
                                        </div>
                                        {result.table_diffs.length === 0
                                            ? <p style={{ color: 'var(--text-ghost)' }}>No table differences found.</p>
                                            : result.table_diffs.map((d: TableDiff, i: number) => <TableDiffCard key={i} diff={d} />)}
                                    </div>
                                )}

                                {activeTab === 'images' && (
                                    <div style={{ maxWidth: 900 }}>
                                        <div className="section-heading"><ImageIcon size={15} /> Image Differences</div>
                                        {result.image_diffs.filter((d: ImageDiff) => d.diff_type !== 'unchanged').length === 0
                                            ? <p style={{ color: 'var(--text-ghost)' }}>No image differences detected.</p>
                                            : result.image_diffs
                                                .filter((d: ImageDiff) => d.diff_type !== 'unchanged')
                                                .map((d: ImageDiff, i: number) => <ImageDiffCard key={i} diff={d} />)}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

/* ════════════════════════ Report Generator ════════════════════════ */

function generateReportHTML(r: ComparisonResult): string {
    const changed = r.text_diffs.filter((d: TextDiff) => d.diff_type !== 'unchanged');
    const bullets = r.bullet_diffs.filter((d: TextDiff) => d.diff_type !== 'unchanged');

    const rowHtml = (diffs: TextDiff[]) => diffs.map((d: TextDiff) => `
    <tr>
      <td>${d.page}</td>
      <td><span class="badge badge-${d.diff_type}">${d.diff_type}</span></td>
      <td>${d.content_a || ''}</td>
      <td>${d.content_b || ''}</td>
      <td>${Math.round(d.similarity_score * 100)}%</td>
    </tr>`).join('');

    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>PDF Comparison Report</title>
<style>
  body{font-family:'Geist',system-ui,sans-serif;background:#f8f9fa;color:#18181b;margin:0}
  header{background:#09090b;color:#fafafa;padding:24px 40px}
  header h1{font-size:1.3rem;margin:0;font-weight:700;letter-spacing:-0.02em}
  header p{color:#71717a;font-size:12px;margin:4px 0 0}
  main{max-width:1100px;margin:32px auto;padding:0 24px}
  h2{font-size:1rem;margin:28px 0 12px;border-bottom:1px solid #e4e4e7;padding-bottom:8px;color:#3f3f46}
  table{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:24px}
  th,td{padding:8px 12px;border:1px solid #e4e4e7;text-align:left}
  th{background:#f4f4f5;font-weight:600;font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:#71717a}
  .badge{padding:2px 8px;border-radius:12px;font-size:10px;font-weight:700;text-transform:uppercase}
  .badge-added{background:#dcfce7;color:#166534}
  .badge-removed{background:#fef2f2;color:#991b1b}
  .badge-changed{background:#fef9c3;color:#854d0e}
  .summary{background:#f0f4ff;border:1px solid #c8d2f8;padding:16px;border-radius:8px;line-height:1.7;font-size:13px}
  .stat{display:inline-block;background:white;border:1px solid #e4e4e7;padding:10px 20px;border-radius:8px;margin:0 8px 8px 0}
  .stat .v{font-size:1.3rem;font-weight:800}.stat .l{font-size:11px;color:#71717a}
</style>
</head>
<body>
<header>
  <h1>PDF Comparison Report</h1>
  <p>Generated ${new Date().toLocaleString()}</p>
</header>
<main>
  <div>
    <div class="stat"><div class="v">${Math.round(r.similarity_percentage)}%</div><div class="l">Similarity</div></div>
    <div class="stat"><div class="v">${r.page_count_a}</div><div class="l">Pages (A)</div></div>
    <div class="stat"><div class="v">${r.page_count_b}</div><div class="l">Pages (B)</div></div>
    <div class="stat"><div class="v">${changed.length}</div><div class="l">Text Diffs</div></div>
    <div class="stat"><div class="v">${r.table_diffs.length}</div><div class="l">Table Diffs</div></div>
  </div>
  <h2>AI Summary</h2>
  <div class="summary">${r.overall_summary.replace(/\n/g, '<br>')}</div>
  <h2>Text Differences</h2>
  <table><thead><tr><th>Page</th><th>Type</th><th>Document A</th><th>Document B</th><th>Score</th></tr></thead><tbody>${rowHtml(changed)}</tbody></table>
  <h2>Bullet Differences</h2>
  <table><thead><tr><th>Page</th><th>Type</th><th>Document A</th><th>Document B</th><th>Score</th></tr></thead><tbody>${rowHtml(bullets)}</tbody></table>
  <h2>Image Differences</h2>
  <table><thead><tr><th>Page</th><th>Type</th><th>AI Analysis</th></tr></thead><tbody>${r.image_diffs.filter((d: ImageDiff) => d.diff_type !== 'unchanged').map((d: ImageDiff) => `
    <tr><td>${d.page}</td><td><span class="badge badge-${d.diff_type}">${d.diff_type}</span></td><td>${d.ai_analysis}</td></tr>`).join('')}</tbody></table>
</main>
</body>
</html>`;
}
