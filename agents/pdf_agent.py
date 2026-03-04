"""
PDF Agent module for downloading NCERT chapter PDFs.
"""

import re
import json
import requests
from pathlib import Path
from typing import Optional, Dict, Any

from core.logger import logger
from core.llm_client import create_llm_client
from core.prompt_loader import get_prompt_loader
from core.state_manager import get_state_manager


class PDFAgent:
    """Agent for retrieving NCERT chapter PDFs."""

    def __init__(self):
        """Initialize PDF agent."""
        self.llm_client = create_llm_client()
        self.prompt_loader = get_prompt_loader()

    def run(self) -> str:
        """
        Run the PDF retrieval process.

        Returns:
            Path to downloaded PDF file

        Raises:
            RuntimeError: If PDF retrieval fails
        """
        logger.section("PDF Retrieval")

        state = get_state_manager().get_current()
        if not state:
            raise RuntimeError("No chapter state found")

        pdf_prompt = self.prompt_loader.format_pdf_prompt(
            class_level=state.class_level,
            subject=state.subject,
            chapter_number=state.chapter_number,
            chapter_title=state.chapter_title,
            medium=state.medium,
            chapter_name=state.get_chapter_name(),
        )

        logger.info(f"Fetching PDF for: {state.get_chapter_name()}")

        state.save_prompt("pdf", pdf_prompt)

        pdf_output_path = state.pdf_path
        if not pdf_output_path:
            raise RuntimeError("PDF path not initialized")

        try:
            response = self.llm_client.call(pdf_prompt)
            state.save_raw_response("pdf", response)

            pdf_info = self._parse_pdf_response(response)
            pdf_url = pdf_info.get("pdf_url")

            if not pdf_url:
                raise ValueError("No PDF URL found in response")

            logger.info(f"PDF URL: {pdf_url}")

            pdf_path = self._download_pdf(pdf_url, pdf_output_path)

            state.update("pdf_url", pdf_url)
            state.update("pdf_path", str(pdf_path))

            logger.info(f"PDF downloaded successfully: {pdf_path}")

            return str(pdf_path)

        except Exception as e:
            logger.error(f"PDF retrieval failed: {e}", exc_info=True)
            raise RuntimeError(f"PDF retrieval failed: {e}") from e

    def _parse_pdf_response(self, response: str) -> Dict[str, Any]:
        """
        Parse the LLM response to extract PDF URL.

        Args:
            response: Raw LLM response

        Returns:
            Dictionary with chapter_name and pdf_url

        Raises:
            ValueError: If parsing fails
        """
        try:
            if "{" in response and "}" in response:
                json_match = re.search(r"\{[^}]+\}", response, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                    return {
                        "chapter_name": data.get("Chapter Name", ""),
                        "pdf_url": data.get("Official NCERT PDF Link", ""),
                    }

            lines = response.strip().split("\n")
            chapter_name = ""
            pdf_url = ""

            for line in lines:
                if "chapter name" in line.lower():
                    chapter_name = line.split(":", 1)[-1].strip()
                elif "pdf link" in line.lower() or "ncert" in line.lower():
                    if "http" in line.lower():
                        url_match = re.search(r"https?://[^\s]+", line)
                        if url_match:
                            pdf_url = url_match.group()

            if not pdf_url:
                url_match = re.search(r"https?://[^\s]+", response)
                if url_match:
                    pdf_url = url_match.group()

            if not pdf_url:
                raise ValueError("Could not extract PDF URL from response")

            return {"chapter_name": chapter_name, "pdf_url": pdf_url}

        except Exception as e:
            logger.error(f"Failed to parse PDF response: {e}")
            raise ValueError(f"Invalid PDF response format: {e}") from e

    def _download_pdf(self, url: str, output_path: Path) -> Path:
        """
        Download PDF from URL.

        Args:
            url: PDF URL
            output_path: Where to save the PDF

        Returns:
            Path to downloaded PDF

        Raises:
            RuntimeError: If download fails
        """
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }

            response = requests.get(
                url, headers=headers, timeout=60, allow_redirects=True
            )
            response.raise_for_status()

            with open(output_path, "wb") as f:
                f.write(response.content)

            logger.info(f"PDF saved: {output_path} ({len(response.content)} bytes)")

            return output_path

        except requests.RequestException as e:
            raise RuntimeError(f"Failed to download PDF: {e}") from e


def create_pdf_agent() -> PDFAgent:
    """
    Factory function to create PDF agent.

    Returns:
        PDFAgent instance
    """
    return PDFAgent()
