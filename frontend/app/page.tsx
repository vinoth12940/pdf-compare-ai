'use client';

import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import {
    FileText, Upload, X, CheckCircle, AlertCircle,
    ChevronDown, ChevronUp, Download, Loader2,
    FileCheck, Table2, Image as ImageIcon, List, AlignLeft, Zap
} from 'lucide-react';
import { comparePDFs, ComparisonResult, TextDiff, TableDiff, ImageDiff } from '@/lib/api';
import axios from 'axios';

// ─── Sub-components ──────────────────────────────────────────────────────────

function FileDropzone({ label, file, onFile }: { label: string; file: File | null; onFile: (f: File) => void }) {
    const onDrop = useCallback((accepted: File[]) => { if (accepted[0]) onFile(accepted[0]); }, [onFile]);
    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop, accept: { 'application/pdf': ['.pdf'] }, multiple: false,
    });

    return (
        <div
            {...getRootProps()}
            className={`dropzone ${isDragActive ? 'active' : ''} ${file ? 'has-file' : ''}`}
        >
            <input {...getInputProps()} />
            {file ? (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
                    <CheckCircle size={32} color="var(--green)" />
                    <div style={{ fontWeight: 600, color: 'var(--green)' }}>{file.name}</div>
                    <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                        {(file.size / 1024 / 1024).toFixed(2)} MB · Click to change
                    </div>
                </div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
                    <Upload size={32} color={isDragActive ? 'var(--accent)' : 'var(--text-dim)'} />
                    <div style={{ fontWeight: 600, color: isDragActive ? 'var(--accent)' : 'var(--text-muted)' }}>{label}</div>
                    <div style={{ color: 'var(--text-dim)', fontSize: 12 }}>Drag & drop or click to browse</div>
                </div>
            )}
        </div>
    );
}

function DiffBadge({ type }: { type: string }) {
    const map: Record<string, { cls: string; label: string }> = {
        added: { cls: 'badge-added', label: 'Added' },
        removed: { cls: 'badge-removed', label: 'Removed' },
        changed: { cls: 'badge-changed', label: 'Changed' },
        unchanged: { cls: 'badge-unchanged', label: 'Unchanged' },
    };
    const d = map[type] || map.unchanged;
    return <span className={`badge ${d.cls}`}>{d.label}</span>;
}

function TextDiffCard({ diff }: { diff: TextDiff }) {
    const [open, setOpen] = useState(false);
    if (diff.diff_type === 'unchanged') return null;

    return (
        <div className="card" style={{ marginBottom: 10, padding: 0, overflow: 'hidden' }}>
            <div
                style={{ padding: '12px 16px', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--surface-2)' }}
                onClick={() => setOpen(!open)}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <DiffBadge type={diff.diff_type} />
                    <span style={{ fontWeight: 500, fontSize: 13 }}>
                        Page {diff.page} · {diff.section_type.charAt(0).toUpperCase() + diff.section_type.slice(1)}
                    </span>
                    <span style={{ color: 'var(--text-dim)', fontSize: 11 }}>
                        {Math.round(diff.similarity_score * 100)}% similar
                    </span>
                </div>
                {open ? <ChevronUp size={14} color="var(--text-muted)" /> : <ChevronDown size={14} color="var(--text-muted)" />}
            </div>

            {open && (
                <div className="diff-grid animate-fade-in" style={{ borderRadius: 0 }}>
                    <div className={`diff-panel ${diff.diff_type === 'removed' ? 'removed' : diff.diff_type === 'added' ? '' : 'changed-a'}`}>
                        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--red)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>Document A</div>
                        <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{diff.content_a || <em style={{ color: 'var(--text-dim)' }}>(not present)</em>}</div>
                    </div>
                    <div className={`diff-panel ${diff.diff_type === 'added' ? 'added' : diff.diff_type === 'removed' ? '' : 'changed-b'}`}>
                        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--green)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>Document B</div>
                        <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{diff.content_b || <em style={{ color: 'var(--text-dim)' }}>(not present)</em>}</div>
                    </div>
                </div>
            )}
        </div>
    );
}

function TableDiffCard({ diff }: { diff: TableDiff }) {
    const [open, setOpen] = useState(false);
    const headers = [...(diff.headers_a || []), ...(diff.headers_b || [])].filter(Boolean);
    const maxCols = Math.max((diff.headers_a?.length || 0), (diff.headers_b?.length || 0));
    const changedCells = new Set(diff.cell_diffs.map(c => `${c.row}-${c.col}`));
    const cellDiffMap: Record<string, { diff_type: string; value_a: string | null; value_b: string | null }> = {};
    for (const c of diff.cell_diffs) { cellDiffMap[`${c.row}-${c.col}`] = c; }

    return (
        <div className="card" style={{ marginBottom: 10, padding: 0, overflow: 'hidden' }}>
            <div
                style={{ padding: '12px 16px', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--surface-2)' }}
                onClick={() => setOpen(!open)}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <DiffBadge type={diff.diff_type} />
                    <span style={{ fontWeight: 500, fontSize: 13 }}>Table {diff.table_index + 1} · Page {diff.page}</span>
                    {diff.rows_added > 0 && <span className="badge badge-added">+{diff.rows_added} rows</span>}
                    {diff.rows_removed > 0 && <span className="badge badge-removed">-{diff.rows_removed} rows</span>}
                    <span style={{ color: 'var(--text-dim)', fontSize: 11 }}>{diff.cell_diffs.length} cell changes</span>
                </div>
                {open ? <ChevronUp size={14} color="var(--text-muted)" /> : <ChevronDown size={14} color="var(--text-muted)" />}
            </div>

            {open && (
                <div style={{ padding: 16, overflowX: 'auto' }} className="animate-fade-in">
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                        {['A', 'B'].map(side => {
                            const headers = side === 'A' ? diff.headers_a : diff.headers_b;
                            if (!headers) return <div key={side} style={{ color: 'var(--text-dim)', fontStyle: 'italic', padding: 12 }}>Not present in Document {side}</div>;
                            return (
                                <div key={side}>
                                    <div style={{ fontSize: 11, fontWeight: 700, color: side === 'A' ? 'var(--red)' : 'var(--green)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>Document {side}</div>
                                    <table className="table-diff">
                                        <thead><tr>{headers.map((h, i) => <th key={i}>{h || '-'}</th>)}</tr></thead>
                                        <tbody>
                                            {diff.cell_diffs.filter(c => c.diff_type !== 'unchanged').map((c, i) => (
                                                c.row > 0 && (
                                                    <tr key={i}>
                                                        <td colSpan={maxCols || 1} className={`cell-${side === 'A' ? 'changed-a' : 'changed-b'}`}>
                                                            <strong>Row {c.row}, Col {c.col}:</strong> {side === 'A' ? (c.value_a ?? <em>empty</em>) : (c.value_b ?? <em>empty</em>)}
                                                        </td>
                                                    </tr>
                                                )
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
}

function ImageDiffCard({ diff }: { diff: ImageDiff }) {
    const [open, setOpen] = useState(false);
    if (diff.diff_type === 'unchanged') return null;

    return (
        <div className="card" style={{ marginBottom: 10, padding: 0, overflow: 'hidden' }}>
            <div
                style={{ padding: '12px 16px', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--surface-2)' }}
                onClick={() => setOpen(!open)}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <DiffBadge type={diff.diff_type} />
                    <span style={{ fontWeight: 500, fontSize: 13 }}>Image {diff.image_index + 1} · Page {diff.page}</span>
                </div>
                {open ? <ChevronUp size={14} color="var(--text-muted)" /> : <ChevronDown size={14} color="var(--text-muted)" />}
            </div>

            {open && (
                <div style={{ padding: 16 }} className="animate-fade-in">
                    <div className="diff-grid" style={{ borderRadius: 8 }}>
                        <div className="diff-panel changed-a">
                            <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--red)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>Document A</div>
                            <p style={{ color: 'var(--text-muted)', fontSize: 12, lineHeight: 1.7 }}>{diff.description_a || <em>No image</em>}</p>
                        </div>
                        <div className="diff-panel changed-b">
                            <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--green)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>Document B</div>
                            <p style={{ color: 'var(--text-muted)', fontSize: 12, lineHeight: 1.7 }}>{diff.description_b || <em>No image</em>}</p>
                        </div>
                    </div>
                    {diff.ai_analysis && (
                        <div style={{ marginTop: 12, padding: 12, background: 'var(--blue-bg)', borderRadius: 8, border: '1px solid #1f6feb40', fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.7 }}>
                            <span style={{ color: 'var(--accent)', fontWeight: 600 }}>🤖 AI Analysis: </span>{diff.ai_analysis}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

function SimilarityRing({ value }: { value: number }) {
    const color = value >= 80 ? 'var(--green)' : value >= 50 ? 'var(--yellow)' : 'var(--red)';
    return (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
            <div className="similarity-ring" style={{ borderColor: color }}>
                <div style={{ fontSize: 28, fontWeight: 800, color }}>{value}%</div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>similar</div>
            </div>
        </div>
    );
}

function SideBySideViewer({ renders_a, renders_b, overlays_a, overlays_b, name_a, name_b }: {
    renders_a: string[]; renders_b: string[];
    overlays_a?: string[]; overlays_b?: string[];
    name_a: string; name_b: string;
}) {
    const maxPages = Math.max(renders_a.length, renders_b.length);
    const [page, setPage] = useState(0);
    const [showOverlay, setShowOverlay] = useState(true);

    const hasOverlays = overlays_a && overlays_a.length > 0 && overlays_b && overlays_b.length > 0;

    // Pick which images to show based on toggle
    const imgA = (showOverlay && hasOverlays && overlays_a[page]) ? overlays_a[page] : (page < renders_a.length ? renders_a[page] : null);
    const imgB = (showOverlay && hasOverlays && overlays_b && overlays_b[page]) ? overlays_b[page] : (page < renders_b.length ? renders_b[page] : null);

    if (maxPages === 0) return <p style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}>No page renders available.</p>;

    return (
        <div>
            {/* Page navigation + change toggle */}
            <div style={{
                display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 12,
                marginBottom: 16, padding: '10px 16px', background: 'var(--surface-2)', borderRadius: 10,
                flexWrap: 'wrap',
            }}>
                <button
                    className="btn btn-ghost"
                    style={{ padding: '6px 12px', fontSize: 12 }}
                    disabled={page === 0}
                    onClick={() => setPage(p => Math.max(0, p - 1))}
                >
                    ← Prev
                </button>
                <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                    {Array.from({ length: maxPages }, (_, i) => (
                        <button
                            key={i}
                            onClick={() => setPage(i)}
                            style={{
                                width: 28, height: 28, borderRadius: 6, border: 'none',
                                cursor: 'pointer', fontSize: 11, fontWeight: 700,
                                background: page === i ? 'var(--accent)' : 'var(--surface-3)',
                                color: page === i ? '#0d1117' : 'var(--text-muted)',
                                transition: 'all .15s ease',
                            }}
                        >
                            {i + 1}
                        </button>
                    ))}
                </div>
                <button
                    className="btn btn-ghost"
                    style={{ padding: '6px 12px', fontSize: 12 }}
                    disabled={page >= maxPages - 1}
                    onClick={() => setPage(p => Math.min(maxPages - 1, p + 1))}
                >
                    Next →
                </button>
                <span style={{ color: 'var(--text-dim)', fontSize: 11 }}>
                    Page {page + 1} of {maxPages}
                </span>

                {/* Highlight toggle */}
                {hasOverlays && (
                    <button
                        onClick={() => setShowOverlay(v => !v)}
                        style={{
                            marginLeft: 12,
                            padding: '6px 14px',
                            fontSize: 11,
                            fontWeight: 700,
                            borderRadius: 8,
                            border: 'none',
                            cursor: 'pointer',
                            background: showOverlay
                                ? 'linear-gradient(135deg, #ff4d4d, #4dff4d)'
                                : 'var(--surface-3)',
                            color: showOverlay ? '#0d1117' : 'var(--text-muted)',
                            transition: 'all .2s ease',
                        }}
                    >
                        {showOverlay ? '🔍 Highlights ON' : '📄 Highlights OFF'}
                    </button>
                )}
            </div>

            {/* Legend */}
            {showOverlay && hasOverlays && (
                <div style={{
                    display: 'flex', justifyContent: 'center', gap: 24, marginBottom: 12,
                    fontSize: 11, color: 'var(--text-dim)',
                }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ width: 14, height: 14, borderRadius: 3, background: 'rgba(255, 60, 60, 0.5)', display: 'inline-block' }} />
                        Changed / Removed (Doc A)
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ width: 14, height: 14, borderRadius: 3, background: 'rgba(60, 200, 60, 0.5)', display: 'inline-block' }} />
                        Changed / Added (Doc B)
                    </span>
                </div>
            )}

            {/* Side-by-side panels */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                {/* Document A */}
                <div style={{
                    border: '2px solid var(--red-border)', borderRadius: 10,
                    background: 'var(--surface)', overflow: 'hidden',
                }}>
                    <div style={{
                        padding: '8px 14px', background: 'var(--red-bg)',
                        borderBottom: '1px solid var(--red-border)',
                        display: 'flex', alignItems: 'center', gap: 8,
                    }}>
                        <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--red)', textTransform: 'uppercase', letterSpacing: 1 }}>
                            📄 Document A
                        </span>
                        <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>{name_a}</span>
                    </div>
                    <div style={{ padding: 8, display: 'flex', justifyContent: 'center', background: '#1a1a2e', minHeight: 500 }}>
                        {imgA ? (
                            <img
                                src={`data:image/png;base64,${imgA}`}
                                alt={`Doc A - Page ${page + 1}`}
                                style={{ maxWidth: '100%', height: 'auto', borderRadius: 4, boxShadow: '0 4px 20px rgba(0,0,0,0.4)' }}
                            />
                        ) : (
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-dim)', fontStyle: 'italic', fontSize: 13 }}>
                                No page {page + 1} in this document
                            </div>
                        )}
                    </div>
                </div>

                {/* Document B */}
                <div style={{
                    border: '2px solid var(--green-border)', borderRadius: 10,
                    background: 'var(--surface)', overflow: 'hidden',
                }}>
                    <div style={{
                        padding: '8px 14px', background: 'var(--green-bg)',
                        borderBottom: '1px solid var(--green-border)',
                        display: 'flex', alignItems: 'center', gap: 8,
                    }}>
                        <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--green)', textTransform: 'uppercase', letterSpacing: 1 }}>
                            📄 Document B
                        </span>
                        <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>{name_b}</span>
                    </div>
                    <div style={{ padding: 8, display: 'flex', justifyContent: 'center', background: '#1a1a2e', minHeight: 500 }}>
                        {imgB ? (
                            <img
                                src={`data:image/png;base64,${imgB}`}
                                alt={`Doc B - Page ${page + 1}`}
                                style={{ maxWidth: '100%', height: 'auto', borderRadius: 4, boxShadow: '0 4px 20px rgba(0,0,0,0.4)' }}
                            />
                        ) : (
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-dim)', fontStyle: 'italic', fontSize: 13 }}>
                                No page {page + 1} in this document
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

type Tab = 'sidebyside' | 'summary' | 'paragraphs' | 'bullets' | 'tables' | 'images';

export default function Home() {
    const [file1, setFile1] = useState<File | null>(null);
    const [file2, setFile2] = useState<File | null>(null);
    const [apiKey, setApiKey] = useState('');
    const [loading, setLoading] = useState(false);
    const [progress, setProgress] = useState(0);
    const [result, setResult] = useState<ComparisonResult | null>(null);
    const [error, setError] = useState('');
    const [activeTab, setActiveTab] = useState<Tab>('summary');
    const [statusMsg, setStatusMsg] = useState('');

    const handleCompare = async () => {
        if (!file1 || !file2) { setError('Please upload both PDF files.'); return; }
        setError('');
        setLoading(true);
        setProgress(5);
        setResult(null);

        const steps = [
            { pct: 15, msg: '📂 Extracting content from PDFs...' },
            { pct: 35, msg: '🔍 Detecting tables, bullets & images...' },
            { pct: 55, msg: '🤖 Running Gemini AI analysis...' },
            { pct: 75, msg: '📊 Computing differences...' },
            { pct: 90, msg: '✨ Generating comparison report...' },
        ];

        let stepIdx = 0;
        const interval = setInterval(() => {
            if (stepIdx < steps.length) {
                setProgress(steps[stepIdx].pct);
                setStatusMsg(steps[stepIdx].msg);
                stepIdx++;
            }
        }, 2000);

        try {
            const data = await comparePDFs(file1, file2, apiKey, setProgress);
            setResult(data);
            setActiveTab('sidebyside');
            setProgress(100);
        } catch (err: unknown) {
            const msg = axios.isAxiosError(err)
                ? err.response?.data?.detail || err.message
                : String(err);
            setError(msg);
        } finally {
            clearInterval(interval);
            setLoading(false);
            setProgress(0);
            setStatusMsg('');
        }
    };

    const handleExport = () => {
        if (!result) return;
        const html = generateReportHTML(result);
        const blob = new Blob([html], { type: 'text/html' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `pdf-comparison-${result.comparison_id.slice(0, 8)}.html`;
        a.click();
        URL.revokeObjectURL(url);
    };

    const changedTextDiffs = result?.text_diffs.filter(d => d.diff_type !== 'unchanged') || [];
    const changedBulletDiffs = result?.bullet_diffs.filter(d => d.diff_type !== 'unchanged') || [];

    return (
        <div style={{ minHeight: '100vh' }}>
            {/* ── Header ── */}
            <header style={{
                borderBottom: '1px solid var(--border)',
                background: 'linear-gradient(180deg, var(--surface) 0%, var(--bg) 100%)',
                padding: '0 24px',
            }}>
                <div className="container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', height: 56 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div style={{
                            background: 'linear-gradient(135deg, #58a6ff, #79c0ff)',
                            borderRadius: 8,
                            width: 32, height: 32,
                            display: 'flex', alignItems: 'center', justifyContent: 'center'
                        }}>
                            <FileCheck size={18} color="#0d1117" />
                        </div>
                        <div>
                            <div style={{ fontWeight: 700, fontSize: 15 }}>PDF Compare AI</div>
                            <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>Powered by Gemini AI</div>
                        </div>
                    </div>
                    {result && (
                        <button className="btn btn-ghost" onClick={handleExport} style={{ fontSize: 12 }}>
                            <Download size={14} /> Export Report
                        </button>
                    )}
                </div>
            </header>

            <main className="container" style={{ padding: '32px 24px' }}>
                {/* ── Upload Section ── */}
                <div className="card" style={{ marginBottom: 24 }}>
                    <h2 style={{ marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Upload size={18} color="var(--accent)" /> Upload PDFs to Compare
                    </h2>
                    <p style={{ color: 'var(--text-muted)', fontSize: 12, marginBottom: 20 }}>
                        Supports text, tables, bullet points, images, headings — and scanned PDFs via OCR
                    </p>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
                        <div>
                            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--red)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>📄 Document A (Original)</div>
                            <FileDropzone label="Drop first PDF here" file={file1} onFile={setFile1} />
                        </div>
                        <div>
                            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--green)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>📄 Document B (Compare)</div>
                            <FileDropzone label="Drop second PDF here" file={file2} onFile={setFile2} />
                        </div>
                    </div>

                    <div style={{ marginBottom: 16 }}>
                        <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>
                            🔑 Gemini API Key <span style={{ fontWeight: 400, color: 'var(--text-dim)' }}>(optional if set in .env)</span>
                        </label>
                        <input
                            className="input"
                            type="password"
                            placeholder="AIza..."
                            value={apiKey}
                            onChange={e => setApiKey(e.target.value)}
                        />
                    </div>

                    {error && (
                        <div style={{
                            display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 16,
                            background: 'var(--red-bg)', border: '1px solid var(--red-border)',
                            borderRadius: 8, padding: '12px 14px', color: 'var(--red)', fontSize: 13
                        }}>
                            <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
                            <span>{error}</span>
                        </div>
                    )}

                    {loading && (
                        <div style={{ marginBottom: 16 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 12, color: 'var(--text-muted)' }}>
                                <span className="animate-pulse">{statusMsg || 'Processing...'}</span>
                                <span>{progress}%</span>
                            </div>
                            <div className="progress-bar">
                                <div className="progress-fill" style={{ width: `${progress}%` }} />
                            </div>
                        </div>
                    )}

                    <button
                        className="btn btn-primary"
                        style={{ width: '100%', justifyContent: 'center', padding: '12px 20px', fontSize: 14 }}
                        disabled={!file1 || !file2 || loading}
                        onClick={handleCompare}
                    >
                        {loading ? (
                            <><Loader2 size={16} className="animate-spin" /> Analyzing with AI...</>
                        ) : (
                            <><Zap size={16} /> Compare PDFs</>
                        )}
                    </button>
                </div>

                {/* ── Results ── */}
                {result && (
                    <div className="animate-fade-in">
                        {/* Stats row */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginBottom: 20, flexWrap: 'wrap' }}>
                            <SimilarityRing value={Math.round(result.similarity_percentage)} />
                            <div className="stats-grid" style={{ flex: 1, minWidth: 300 }}>
                                {[
                                    { label: 'Paragraph Changes', value: (result.stats.paragraphs_changed as number) + (result.stats.paragraphs_added as number) + (result.stats.paragraphs_removed as number), color: 'yellow' },
                                    { label: 'Bullet Changes', value: (result.stats.bullets_changed as number) + (result.stats.bullets_added as number) + (result.stats.bullets_removed as number), color: 'yellow' },
                                    { label: 'Table Changes', value: result.stats.tables_changed as number, color: 'accent' },
                                    { label: 'Image Changes', value: (result.stats.images_changed as number) + (result.stats.images_added as number) + (result.stats.images_removed as number), color: 'accent' },
                                    { label: 'Pages (A / B)', value: `${result.page_count_a} / ${result.page_count_b}`, color: '' },
                                ].map(s => (
                                    <div className="stat-card" key={s.label}>
                                        <div className="label">{s.label}</div>
                                        <div className={`value ${s.color}`}>{s.value}</div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Tab navigation */}
                        <div className="card" style={{ padding: 0 }}>
                            <div className="tab-bar">
                                {([
                                    { id: 'sidebyside', label: 'Side by Side', icon: <FileText size={13} />, count: undefined },
                                    { id: 'summary', label: 'AI Summary', icon: <Zap size={13} /> },
                                    { id: 'paragraphs', label: 'Paragraphs', icon: <AlignLeft size={13} />, count: changedTextDiffs.length },
                                    { id: 'bullets', label: 'Bullets', icon: <List size={13} />, count: changedBulletDiffs.length },
                                    { id: 'tables', label: 'Tables', icon: <Table2 size={13} />, count: result.table_diffs.length },
                                    { id: 'images', label: 'Images', icon: <ImageIcon size={13} />, count: result.image_diffs.filter(d => d.diff_type !== 'unchanged').length },
                                ] as { id: Tab; label: string; icon: React.ReactNode; count?: number }[]).map(tab => (
                                    <button
                                        key={tab.id}
                                        className={`tab ${activeTab === tab.id ? 'active' : ''}`}
                                        onClick={() => setActiveTab(tab.id)}
                                    >
                                        {tab.icon} {tab.label}
                                        {tab.count !== undefined && <span className="count">{tab.count}</span>}
                                    </button>
                                ))}
                            </div>

                            <div style={{ padding: 20 }}>
                                {/* Side by Side */}
                                {activeTab === 'sidebyside' && result.page_renders_a && result.page_renders_b && (
                                    <SideBySideViewer
                                        renders_a={result.page_renders_a}
                                        renders_b={result.page_renders_b}
                                        overlays_a={result.diff_overlay_a}
                                        overlays_b={result.diff_overlay_b}
                                        name_a={result.file1_name}
                                        name_b={result.file2_name}
                                    />
                                )}

                                {/* Summary */}
                                {activeTab === 'summary' && (
                                    <div>
                                        <h3 style={{ marginBottom: 14, color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 6 }}>
                                            <Zap size={16} /> AI-Powered Comparison Summary
                                        </h3>
                                        <div className="summary-block">
                                            <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12, display: 'flex', gap: 16 }}>
                                                <span><strong style={{ color: 'var(--red)' }}>A:</strong> {result.file1_name}</span>
                                                <span style={{ color: 'var(--text-dim)' }}>↔</span>
                                                <span><strong style={{ color: 'var(--green)' }}>B:</strong> {result.file2_name}</span>
                                            </div>
                                            <p style={{ fontSize: 14, lineHeight: 1.8, color: 'var(--text)' }}>{result.overall_summary}</p>
                                        </div>
                                        {(result.stats.doc_a_is_scanned || result.stats.doc_b_is_scanned) && (
                                            <div style={{ marginTop: 12, padding: '10px 14px', background: 'var(--yellow-bg)', border: '1px solid var(--yellow-border)', borderRadius: 8, fontSize: 12, color: 'var(--yellow)' }}>
                                                ⚠️ {result.stats.doc_a_is_scanned ? 'Document A' : 'Document B'} is a scanned PDF — text extracted via OCR (accuracy may vary)
                                            </div>
                                        )}
                                    </div>
                                )}

                                {/* Paragraphs */}
                                {activeTab === 'paragraphs' && (
                                    <div>
                                        <h3 style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 6 }}>
                                            <AlignLeft size={15} color="var(--accent)" /> Paragraph Differences
                                            <span className="badge badge-changed" style={{ marginLeft: 4 }}>{changedTextDiffs.length}</span>
                                        </h3>
                                        {changedTextDiffs.length === 0
                                            ? <p style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}>No paragraph differences found.</p>
                                            : changedTextDiffs.map((d, i) => <TextDiffCard key={i} diff={d} />)}
                                    </div>
                                )}

                                {/* Bullets */}
                                {activeTab === 'bullets' && (
                                    <div>
                                        <h3 style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 6 }}>
                                            <List size={15} color="var(--accent)" /> Bullet Point Differences
                                            <span className="badge badge-changed" style={{ marginLeft: 4 }}>{changedBulletDiffs.length}</span>
                                        </h3>
                                        {changedBulletDiffs.length === 0
                                            ? <p style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}>No bullet point differences found.</p>
                                            : changedBulletDiffs.map((d, i) => <TextDiffCard key={i} diff={d} />)}
                                    </div>
                                )}

                                {/* Tables */}
                                {activeTab === 'tables' && (
                                    <div>
                                        <h3 style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 6 }}>
                                            <Table2 size={15} color="var(--accent)" /> Table Differences
                                            <span className="badge badge-changed" style={{ marginLeft: 4 }}>{result.table_diffs.length}</span>
                                        </h3>
                                        {result.table_diffs.length === 0
                                            ? <p style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}>No table differences found.</p>
                                            : result.table_diffs.map((d, i) => <TableDiffCard key={i} diff={d} />)}
                                    </div>
                                )}

                                {/* Images */}
                                {activeTab === 'images' && (
                                    <div>
                                        <h3 style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 6 }}>
                                            <ImageIcon size={15} color="var(--accent)" /> Image Differences
                                        </h3>
                                        {result.image_diffs.filter(d => d.diff_type !== 'unchanged').length === 0
                                            ? <p style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}>No image differences detected.</p>
                                            : result.image_diffs
                                                .filter(d => d.diff_type !== 'unchanged')
                                                .map((d, i) => <ImageDiffCard key={i} diff={d} />)}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
}

// ─── Report HTML Generator ────────────────────────────────────────────────────

function generateReportHTML(r: ComparisonResult): string {
    const changed = r.text_diffs.filter(d => d.diff_type !== 'unchanged');
    const bullets = r.bullet_diffs.filter(d => d.diff_type !== 'unchanged');

    const rowHtml = (diffs: TextDiff[]) => diffs.map(d => `
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
  body { font-family: system-ui; background: #f6f8fa; color: #1f2328; margin: 0; }
  header { background: #0d1117; color: white; padding: 20px 40px; }
  header h1 { font-size: 1.4rem; margin: 0; }
  header p { color: #8b949e; font-size: 12px; margin: 4px 0 0; }
  main { max-width: 1200px; margin: 32px auto; padding: 0 24px; }
  h2 { font-size: 1.1rem; margin: 28px 0 12px; border-bottom: 1px solid #d0d7de; padding-bottom: 8px; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; margin-bottom: 24px; }
  th, td { padding: 8px 12px; border: 1px solid #d0d7de; text-align: left; }
  th { background: #f6f8fa; font-weight: 600; }
  .badge { padding: 2px 8px; border-radius: 12px; font-size: 10px; font-weight: 700; text-transform: uppercase; }
  .badge-added { background: #dafbe1; color: #116329; }
  .badge-removed { background: #ffeef0; color: #a40e26; }
  .badge-changed { background: #fff8c5; color: #7d4e00; }
  .summary { background: #eef2ff; border: 1px solid #c8d2f8; padding: 16px; border-radius: 8px; line-height: 1.7; }
  .stat { display: inline-block; background: white; border: 1px solid #d0d7de; padding: 10px 20px; border-radius: 8px; margin: 0 8px 8px 0; }
  .stat .v { font-size: 1.4rem; font-weight: 700; }
  .stat .l { font-size: 11px; color: #656d76; }
</style>
</head>
<body>
<header>
  <h1>📄 PDF Comparison Report</h1>
  <p>Generated ${new Date().toLocaleString()}</p>
</header>
<main>
  <div>
    <div class="stat"><div class="v">${Math.round(r.similarity_percentage)}%</div><div class="l">Similarity</div></div>
    <div class="stat"><div class="v">${r.page_count_a}</div><div class="l">Pages (Doc A)</div></div>
    <div class="stat"><div class="v">${r.page_count_b}</div><div class="l">Pages (Doc B)</div></div>
    <div class="stat"><div class="v">${changed.length}</div><div class="l">Paragraph Diffs</div></div>
    <div class="stat"><div class="v">${r.table_diffs.length}</div><div class="l">Table Diffs</div></div>
  </div>

  <h2>🤖 AI Summary</h2>
  <div class="summary">${r.overall_summary.replace(/\n/g, '<br>')}</div>

  <h2>Paragraph Differences</h2>
  <table>
    <thead><tr><th>Page</th><th>Type</th><th>Document A</th><th>Document B</th><th>Similarity</th></tr></thead>
    <tbody>${rowHtml(changed)}</tbody>
  </table>

  <h2>Bullet Point Differences</h2>
  <table>
    <thead><tr><th>Page</th><th>Type</th><th>Document A</th><th>Document B</th><th>Similarity</th></tr></thead>
    <tbody>${rowHtml(bullets)}</tbody>
  </table>

  <h2>Image Differences</h2>
  <table>
    <thead><tr><th>Page</th><th>Type</th><th>AI Analysis</th></tr></thead>
    <tbody>${r.image_diffs.filter(d => d.diff_type !== 'unchanged').map(d => `
      <tr><td>${d.page}</td><td><span class="badge badge-${d.diff_type}">${d.diff_type}</span></td><td>${d.ai_analysis}</td></tr>`).join('')}
    </tbody>
  </table>
</main>
</body>
</html>`;
}
