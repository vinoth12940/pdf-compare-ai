"""
Generate sample PDF documents for testing PDF Compare AI.
Creates two similar-but-different PDFs: a quote and a revised quote.
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.graphics import renderPDF
import os

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Colors ──
BRAND_BLUE = HexColor("#1a56db")
BRAND_DARK = HexColor("#111827")
LIGHT_GRAY = HexColor("#f3f4f6")
MID_GRAY = HexColor("#6b7280")
WHITE = HexColor("#ffffff")
GREEN = HexColor("#059669")
RED = HexColor("#dc2626")


def build_styles():
    """Create custom paragraph styles."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="CompanyName",
        fontSize=22,
        leading=26,
        textColor=BRAND_BLUE,
        fontName="Helvetica-Bold",
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="DocTitle",
        fontSize=28,
        leading=34,
        textColor=BRAND_DARK,
        fontName="Helvetica-Bold",
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="Subtitle",
        fontSize=11,
        leading=14,
        textColor=MID_GRAY,
        fontName="Helvetica",
        spaceAfter=20,
    ))
    styles.add(ParagraphStyle(
        name="SectionHeader",
        fontSize=13,
        leading=16,
        textColor=BRAND_DARK,
        fontName="Helvetica-Bold",
        spaceBefore=18,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="BodyText2",
        fontSize=10,
        leading=14,
        textColor=BRAND_DARK,
        fontName="Helvetica",
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="SmallGray",
        fontSize=9,
        leading=12,
        textColor=MID_GRAY,
        fontName="Helvetica",
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="RightAligned",
        fontSize=10,
        leading=14,
        textColor=BRAND_DARK,
        fontName="Helvetica",
        alignment=TA_RIGHT,
    ))
    styles.add(ParagraphStyle(
        name="Footer",
        fontSize=8,
        leading=10,
        textColor=MID_GRAY,
        fontName="Helvetica",
        alignment=TA_CENTER,
        spaceBefore=30,
    ))
    return styles


def build_quote_pdf(filename, version="v1"):
    """Build a professional quote/invoice PDF."""
    filepath = os.path.join(OUTPUT_DIR, filename)
    doc = SimpleDocTemplate(
        filepath,
        pagesize=letter,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )
    styles = build_styles()
    story = []

    # ── Header ──
    story.append(Paragraph("Acme Solutions Inc.", styles["CompanyName"]))

    if version == "v1":
        story.append(Paragraph("QUOTATION", styles["DocTitle"]))
        story.append(Paragraph("Quote #QT-2026-0042  ·  Issued: February 15, 2026", styles["Subtitle"]))
    else:
        story.append(Paragraph("REVISED QUOTATION", styles["DocTitle"]))
        story.append(Paragraph("Quote #QT-2026-0042-R1  ·  Issued: March 1, 2026", styles["Subtitle"]))

    story.append(HRFlowable(width="100%", color=LIGHT_GRAY, thickness=1))
    story.append(Spacer(1, 12))

    # ── Client Info ──
    story.append(Paragraph("Prepared For", styles["SectionHeader"]))
    story.append(Paragraph("TechVentures Global Ltd.", styles["BodyText2"]))
    story.append(Paragraph("Attn: Sarah Chen, VP of Engineering", styles["BodyText2"]))
    story.append(Paragraph("450 Innovation Drive, Suite 800", styles["SmallGray"]))

    if version == "v1":
        story.append(Paragraph("San Francisco, CA 94105", styles["SmallGray"]))
    else:
        story.append(Paragraph("San Francisco, CA 94107", styles["SmallGray"]))

    story.append(Spacer(1, 12))

    # ── Scope ──
    story.append(Paragraph("Scope of Work", styles["SectionHeader"]))

    if version == "v1":
        story.append(Paragraph(
            "Acme Solutions will provide end-to-end cloud migration services for "
            "TechVentures' existing on-premise infrastructure. This includes assessment, "
            "planning, migration execution, and 30 days of post-migration support.",
            styles["BodyText2"]
        ))
    else:
        story.append(Paragraph(
            "Acme Solutions will provide end-to-end cloud migration services for "
            "TechVentures' existing on-premise infrastructure. This includes assessment, "
            "planning, migration execution, testing and validation, and 60 days of "
            "post-migration support with 24/7 incident response.",
            styles["BodyText2"]
        ))

    story.append(Spacer(1, 6))

    # ── Deliverables ──
    story.append(Paragraph("Key Deliverables", styles["SectionHeader"]))

    if version == "v1":
        bullets = [
            "• Infrastructure audit and cloud readiness assessment report",
            "• Migration roadmap with phased timeline",
            "• AWS environment setup and configuration",
            "• Data migration with zero-downtime cutover strategy",
            "• Security hardening and compliance review",
            "• Knowledge transfer sessions (3 sessions, 2 hours each)",
        ]
    else:
        bullets = [
            "• Infrastructure audit and cloud readiness assessment report",
            "• Migration roadmap with phased timeline and risk matrix",
            "• AWS + Azure multi-cloud environment setup and configuration",
            "• Data migration with zero-downtime cutover strategy",
            "• Security hardening, penetration testing, and compliance review",
            "• Knowledge transfer sessions (5 sessions, 2 hours each)",
            "• Disaster recovery plan and automated failover setup",
        ]

    for b in bullets:
        story.append(Paragraph(b, styles["BodyText2"]))

    story.append(Spacer(1, 12))

    # ── Pricing Table ──
    story.append(Paragraph("Pricing Breakdown", styles["SectionHeader"]))

    if version == "v1":
        table_data = [
            ["Item", "Description", "Qty", "Unit Price", "Total"],
            ["1", "Cloud Readiness Assessment", "1", "$8,500", "$8,500"],
            ["2", "Migration Planning & Architecture", "1", "$12,000", "$12,000"],
            ["3", "Migration Execution (per server)", "15", "$2,200", "$33,000"],
            ["4", "Data Migration (per TB)", "8", "$1,500", "$12,000"],
            ["5", "Security & Compliance Review", "1", "$6,500", "$6,500"],
            ["6", "Knowledge Transfer", "3", "$1,200", "$3,600"],
            ["", "", "", "Subtotal", "$75,600"],
            ["", "", "", "Discount (10%)", "-$7,560"],
            ["", "", "", "TOTAL", "$68,040"],
        ]
    else:
        table_data = [
            ["Item", "Description", "Qty", "Unit Price", "Total"],
            ["1", "Cloud Readiness Assessment", "1", "$8,500", "$8,500"],
            ["2", "Migration Planning & Architecture", "1", "$15,000", "$15,000"],
            ["3", "Migration Execution (per server)", "18", "$2,200", "$39,600"],
            ["4", "Data Migration (per TB)", "12", "$1,500", "$18,000"],
            ["5", "Security, Pen Testing & Compliance", "1", "$9,500", "$9,500"],
            ["6", "Knowledge Transfer", "5", "$1,200", "$6,000"],
            ["7", "Disaster Recovery Setup", "1", "$7,500", "$7,500"],
            ["", "", "", "Subtotal", "$104,100"],
            ["", "", "", "Discount (15%)", "-$15,615"],
            ["", "", "", "TOTAL", "$88,485"],
        ]

    t = Table(table_data, colWidths=[0.5 * inch, 2.8 * inch, 0.6 * inch, 1.1 * inch, 1.1 * inch])
    t.setStyle(TableStyle([
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),

        # Body rows
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("TEXTCOLOR", (0, 1), (-1, -1), BRAND_DARK),

        # Alternating row colors
        ("BACKGROUND", (0, 1), (-1, -4), LIGHT_GRAY),
        ("BACKGROUND", (0, 2), (-1, 2), WHITE),
        ("BACKGROUND", (0, 4), (-1, 4), WHITE),
        ("BACKGROUND", (0, 6), (-1, 6), WHITE),

        # Total row
        ("FONTNAME", (3, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (3, -1), (-1, -1), 11),
        ("TEXTCOLOR", (4, -1), (4, -1), BRAND_BLUE),

        # Grid
        ("GRID", (0, 0), (-1, -4), 0.5, HexColor("#e5e7eb")),
        ("LINEABOVE", (3, -3), (-1, -3), 0.5, HexColor("#e5e7eb")),
        ("LINEABOVE", (3, -1), (-1, -1), 1, BRAND_DARK),

        # Alignment
        ("ALIGN", (2, 0), (2, -1), "CENTER"),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
    ]))

    story.append(t)
    story.append(Spacer(1, 20))

    # ── Terms ──
    story.append(Paragraph("Terms & Conditions", styles["SectionHeader"]))

    if version == "v1":
        terms = [
            "• This quote is valid for 30 days from the date of issue.",
            "• Payment terms: 50% upfront, 50% upon project completion.",
            "• Estimated project timeline: 8-10 weeks from kickoff.",
            "• Travel expenses are billed separately at cost.",
            "• All prices are in USD and exclude applicable taxes.",
        ]
    else:
        terms = [
            "• This quote is valid for 45 days from the date of issue.",
            "• Payment terms: 30% upfront, 40% at midpoint, 30% upon completion.",
            "• Estimated project timeline: 10-12 weeks from kickoff.",
            "• Travel expenses are included up to $5,000.",
            "• All prices are in USD and exclude applicable taxes.",
            "• Includes 60-day warranty period for all deliverables.",
        ]

    for t_text in terms:
        story.append(Paragraph(t_text, styles["BodyText2"]))

    story.append(Spacer(1, 20))

    # ── Signature ──
    story.append(HRFlowable(width="100%", color=LIGHT_GRAY, thickness=1))
    story.append(Spacer(1, 12))

    if version == "v1":
        story.append(Paragraph("Prepared by: James Rodriguez, Senior Solutions Architect", styles["BodyText2"]))
        story.append(Paragraph("Email: j.rodriguez@acmesolutions.com  ·  Phone: (415) 555-0142", styles["SmallGray"]))
    else:
        story.append(Paragraph("Prepared by: James Rodriguez, Director of Cloud Services", styles["BodyText2"]))
        story.append(Paragraph("Email: j.rodriguez@acmesolutions.com  ·  Phone: (415) 555-0142", styles["SmallGray"]))
        story.append(Paragraph("Reviewed by: Maria Gonzalez, VP of Professional Services", styles["SmallGray"]))

    story.append(Spacer(1, 30))

    # ── Footer ──
    story.append(HRFlowable(width="100%", color=LIGHT_GRAY, thickness=0.5))
    story.append(Paragraph(
        "Acme Solutions Inc.  ·  123 Tech Boulevard, Austin, TX 78701  ·  www.acmesolutions.com",
        styles["Footer"]
    ))
    story.append(Paragraph(
        "Confidential — This document is intended solely for the use of TechVentures Global Ltd.",
        styles["Footer"]
    ))

    doc.build(story)
    print(f"✅ Generated: {filepath}")
    return filepath


def main():
    print("Generating sample PDFs for PDF Compare AI...\n")
    f1 = build_quote_pdf("Quote_Original.pdf", version="v1")
    f2 = build_quote_pdf("Quote_Revised.pdf", version="v2")
    print(f"\n📄 Original: {f1}")
    print(f"📄 Revised:  {f2}")
    print("\n🚀 Upload both to http://localhost:3000 to test the comparison!")


if __name__ == "__main__":
    main()
