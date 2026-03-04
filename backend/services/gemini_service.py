from google import genai
from google.genai.types import Part
import base64
import logging
from typing import List, Optional, Dict, Any
import os

logger = logging.getLogger(__name__)


class GeminiService:
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model_name or os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")

        if key:
            self.client = genai.Client(api_key=key)
            self.enabled = True
            logger.info(f"Gemini enabled — model: {self.model}")
        else:
            self.client = None
            self.enabled = False
            logger.warning("No Gemini API key provided — AI features disabled.")

    def _b64_to_part(self, b64_data: str, mime: str = "image/png") -> Part:
        """Convert base64 image data to a genai Part."""
        return Part.from_bytes(data=base64.b64decode(b64_data), mime_type=mime)

    def compare_text_semantically(self, text_a: str, text_b: str) -> Dict[str, Any]:
        """Use Gemini to compare two text blocks for semantic differences."""
        if not self.enabled or not text_a.strip() or not text_b.strip():
            return {
                "summary": "AI analysis not available.",
                "key_differences": [],
                "similarity_score": 0.5,
            }

        prompt = f"""Compare these two document text sections and identify differences.

TEXT A:
{text_a[:3000]}

TEXT B:
{text_b[:3000]}

Respond in JSON format with:
{{
  "summary": "Brief overall comparison summary",
  "key_differences": ["difference 1", "difference 2", ...],
  "similarity_score": 0.0-1.0
}}"""

        try:
            resp = self.client.models.generate_content(
                model=self.model, contents=prompt
            )
            import json, re
            json_match = re.search(r"\{.*\}", resp.text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.error(f"Gemini text comparison failed: {e}")

        return {"summary": "Unable to analyze.", "key_differences": [], "similarity_score": 0.5}

    def describe_image(self, b64_image: str, context: str = "") -> str:
        """Use Gemini Vision to describe an extracted image."""
        if not self.enabled:
            return "Image description unavailable (no API key)."
        try:
            text_part = (
                f"Describe this image from a document{(' — context: ' + context) if context else ''}. "
                "Be specific about: content, text in the image, charts/graphs, diagrams, photos."
            )
            resp = self.client.models.generate_content(
                model=self.model,
                contents=[text_part, self._b64_to_part(b64_image)],
            )
            return resp.text.strip()
        except Exception as e:
            logger.error(f"Gemini image description failed: {e}")
            return "Could not analyze image."

    def compare_images(self, b64_a: str, b64_b: str) -> Dict[str, Any]:
        """Use Gemini Vision to compare two images."""
        if not self.enabled:
            return {
                "summary": "Image comparison unavailable (no API key).",
                "differences": [],
                "are_same": False,
            }
        try:
            text_part = (
                "Compare these two document images side by side. Identify visual differences including: "
                "layout changes, text changes, data changes in charts/tables, added/removed elements. "
                "Respond in JSON: {\"summary\": \"...\", \"differences\": [\"...\"], \"are_same\": bool}"
            )
            resp = self.client.models.generate_content(
                model=self.model,
                contents=[text_part, self._b64_to_part(b64_a), self._b64_to_part(b64_b)],
            )
            import json, re
            json_match = re.search(r"\{.*\}", resp.text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.error(f"Gemini image compare failed: {e}")

        return {"summary": "Could not compare images.", "differences": [], "are_same": False}

    def generate_overall_summary(
        self,
        file1_name: str,
        file2_name: str,
        page_renders_a: List[str],
        page_renders_b: List[str],
        text_a: str,
        text_b: str,
    ) -> str:
        """Generate a comprehensive overall comparison summary."""
        if not self.enabled:
            return (
                f"Comparing '{file1_name}' vs '{file2_name}'. "
                "Enable Gemini API for AI-powered summary."
            )

        try:
            parts: list = [
                f"You are comparing two PDF documents: '{file1_name}' (Document A) and '{file2_name}' (Document B).\n\n"
                f"Document A text excerpt:\n{text_a[:2000]}\n\n"
                f"Document B text excerpt:\n{text_b[:2000]}\n\n"
                "Also review these page renders from each document (Document A pages first, then Document B pages).\n"
                "Provide a comprehensive executive summary of the differences between these two documents, covering:\n"
                "1. Overall purpose/content differences\n"
                "2. Key structural changes (added/removed sections)\n"
                "3. Data or fact changes\n"
                "4. Formatting/style differences\n"
                "Keep the summary under 300 words, professional tone."
            ]

            # Add up to 2 pages from each
            for b64 in page_renders_a[:2]:
                parts.append(self._b64_to_part(b64))
            for b64 in page_renders_b[:2]:
                parts.append(self._b64_to_part(b64))

            resp = self.client.models.generate_content(
                model=self.model, contents=parts
            )
            return resp.text.strip()
        except Exception as e:
            logger.error(f"Gemini overall summary failed: {e}")
            return f"Comparing '{file1_name}' vs '{file2_name}'. AI summary generation failed."

    def compare_table_semantically(self, table_a: List[List], table_b: List[List]) -> str:
        """Use Gemini to summarize table differences."""
        if not self.enabled:
            return "Table AI analysis unavailable."
        try:
            prompt = (
                f"Compare these two tables from a document:\n\nTable A:\n{table_a}\n\nTable B:\n{table_b}\n\n"
                "Summarize key differences in 2-3 sentences: what data changed, rows added/removed, etc."
            )
            resp = self.client.models.generate_content(
                model=self.model, contents=prompt
            )
            return resp.text.strip()
        except Exception as e:
            logger.error(f"Gemini table compare failed: {e}")
            return "Could not analyze table differences."
