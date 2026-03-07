import os
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from services.comparator import Comparator  # noqa: E402
from services.gemini_service import GeminiService  # noqa: E402
from services.pdf_extractor import PDFExtractor  # noqa: E402


def _load_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()


class PDFExtractorSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.workdir = Path(self.tmpdir.name)
        self.extractor = PDFExtractor()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _build_image_asset(self, name: str = "placed.png") -> Path:
        img_path = self.workdir / name
        img = Image.new("RGB", (140, 90), "white")
        draw = ImageDraw.Draw(img)
        draw.rectangle((12, 12, 128, 78), fill="red")
        draw.text((28, 30), "IMG", fill="black", font=_load_font(22))
        img.save(img_path)
        return img_path

    def _build_pdf_with_image(self, name: str, x: int, y: int) -> Path:
        pdf_path = self.workdir / name
        image_path = self._build_image_asset()
        c = canvas.Canvas(str(pdf_path), pagesize=letter)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, 740, "Image Placement Test")
        c.drawImage(ImageReader(str(image_path)), x, y, width=180, height=120)
        c.save()
        return pdf_path

    def _build_scanned_pdf(self, name: str = "scan.pdf") -> Path:
        scan_png = self.workdir / "scan.png"
        scan_pdf = self.workdir / name

        scan = Image.new("RGB", (1654, 2339), "white")
        draw = ImageDraw.Draw(scan)
        font_title = _load_font(72)
        font_body = _load_font(54)
        draw.text((180, 220), "SCANNED NOTICE", fill="black", font=font_title)
        draw.text((180, 420), "This page should go through OCR extraction.", fill="black", font=font_body)
        draw.text((180, 620), "- Bullet item one", fill="black", font=font_body)
        draw.text((180, 800), "- Bullet item two", fill="black", font=font_body)
        scan.save(scan_png)

        c = canvas.Canvas(str(scan_pdf), pagesize=letter)
        c.drawImage(ImageReader(str(scan_png)), 0, 0, width=letter[0], height=letter[1])
        c.save()
        return scan_pdf

    def test_extract_images_includes_bbox(self) -> None:
        pdf_path = self._build_pdf_with_image("image.pdf", x=90, y=500)
        data = self.extractor.extract_all(str(pdf_path))

        self.assertEqual(len(data["images"]), 1)
        image = data["images"][0]
        self.assertGreater(image["x1"], image["x0"])
        self.assertGreater(image["bottom"], image["top"])
        self.assertEqual(image["page_width"], 612.0)
        self.assertEqual(image["page_height"], 792.0)

    def test_compare_emits_image_viewer_region(self) -> None:
        pdf_a = self._build_pdf_with_image("image_a.pdf", x=90, y=500)
        pdf_b = self._build_pdf_with_image("image_b.pdf", x=260, y=420)

        data_a = self.extractor.extract_all(str(pdf_a))
        data_b = self.extractor.extract_all(str(pdf_b))
        renders_a = self.extractor.get_page_renders(str(pdf_a), dpi=120)
        renders_b = self.extractor.get_page_renders(str(pdf_b), dpi=120)

        result = Comparator(GeminiService(api_key=None)).compare(
            data_a,
            data_b,
            "image_a.pdf",
            "image_b.pdf",
            renders_a,
            renders_b,
        )

        image_regions = [region for region in (result.viewer_regions or []) if region.source == "image"]
        self.assertEqual(len(image_regions), 1)
        self.assertIsNotNone(image_regions[0].bbox_a)
        self.assertIsNotNone(image_regions[0].bbox_b)

    def test_scanned_pdf_ocr_produces_geometry(self) -> None:
        if not self.extractor.ocr_available:
            self.skipTest("Tesseract is not installed in this environment")

        pdf_path = self._build_scanned_pdf()
        data = self.extractor.extract_all(str(pdf_path))

        self.assertTrue(data["is_scanned"])
        extracted_blocks = data["headings"] + data["paragraphs"] + data["bullets"]
        self.assertGreater(len(extracted_blocks), 0)

        first = extracted_blocks[0]
        self.assertGreater(first["x1"], first["x0"])
        self.assertGreater(first["bottom"], first["top"])
        self.assertGreater(first["page_width"], 0)
        self.assertGreater(first["page_height"], 0)


if __name__ == "__main__":
    unittest.main()
