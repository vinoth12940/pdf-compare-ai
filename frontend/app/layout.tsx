import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
    title: 'PDF Compare AI — Compare PDFs with Gemini',
    description: 'Upload two PDFs and get AI-powered comparison of paragraphs, tables, images, and bullet points using Gemini AI',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
    return (
        <html lang="en">
            <head>
                <link rel="preconnect" href="https://fonts.googleapis.com" />
                <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
                <link
                    href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Instrument+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap"
                    rel="stylesheet"
                />
            </head>
            <body>
                {/* Ambient gradient mesh background */}
                <div className="ambient-mesh" aria-hidden="true">
                    <div className="ambient-blob" />
                </div>
                {children}
            </body>
        </html>
    );
}
