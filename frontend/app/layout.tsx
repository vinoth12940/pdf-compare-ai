import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
    title: "PDF Compare AI — Compare PDFs with Gemini",
    description:
        "AI-powered PDF comparison tool. Detects text, table, image, and layout differences using Google Gemini.",
};

export default function RootLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <html lang="en">
            <body>{children}</body>
        </html>
    );
}
