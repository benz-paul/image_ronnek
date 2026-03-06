"""
PDF Agent module for downloading NCERT chapter PDFs.
"""

import re
import time
import requests
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urljoin
from urllib3.exceptions import ProtocolError

from bs4 import BeautifulSoup

from brain.prompt_engine.core.logger import logger
from brain.prompt_engine.core.state_manager import get_state_manager


def _sanitize_for_logging(text: str) -> str:
    """Sanitize text for logging to avoid encoding errors on Windows."""
    if not isinstance(text, str):
        text = str(text)
    return text.encode("utf-8", errors="ignore").decode("utf-8")


class PDFAgent:
    """Agent for retrieving NCERT chapter PDFs."""

    BOOK_PAGE_MAP = {
        (10, "science", "english"): "https://ncert.nic.in/textbook.php?jesc1=0-16",
    }

    def __init__(self):
        """Initialize PDF agent with session and browser headers."""
        self.base_url = "https://ncert.nic.in"
        self.textbook_index_url = f"{self.base_url}/textbook.php?ln=en"

        self.session = requests.Session()
        self.session.verify = False

        self.browser_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept": "application/pdf,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Referer": "https://ncert.nic.in/",
            "Upgrade-Insecure-Requests": "1",
        }

    def _check_knowledge_folder(
        self, class_number: int, subject: str, chapter_number: int
    ) -> Optional[Path]:
        """
        Check if PDF already exists in knowledge folder.

        Args:
            class_number: Class number (e.g., 10)
            subject: Subject name (e.g., "Science")
            chapter_number: Chapter number (e.g., 11)

        Returns:
            Path to existing PDF if found, None otherwise
        """
        knowledge_dir = Path("knowledge")
        if not knowledge_dir.exists():
            return None

        subject_clean = subject.lower().replace(" ", "_")

        possible_names = [
            f"class{class_number}_{subject_clean}_chapter{chapter_number}.pdf",
            f"class{class_number}_{subject_clean}_ch{chapter_number}.pdf",
            f"{subject_clean}_chapter{chapter_number}.pdf",
            f"ch{chapter_number}.pdf",
            f"class{class_number}_{subject_clean}.pdf",
            f"{subject_clean}.pdf",
        ]

        for pdf_file in knowledge_dir.glob("*.pdf"):
            pdf_name_lower = pdf_file.name.lower()

            if pdf_name_lower in [n.lower() for n in possible_names]:
                return pdf_file

            if (
                f"chapter{chapter_number}" in pdf_name_lower
                or f"ch{chapter_number}" in pdf_name_lower
            ):
                if (
                    f"class{class_number}" in pdf_name_lower
                    or f"_{subject_clean}" in pdf_name_lower
                    or f"{subject_clean}" in pdf_name_lower
                ):
                    return pdf_file

            chapter_patterns = [
                f"chapter {chapter_number}",
                f"chapter-{chapter_number}",
                f"chapter{chapter_number}",
                f"ch {chapter_number}",
                f"ch-{chapter_number}",
                f"ch{chapter_number}",
            ]

            for pattern in chapter_patterns:
                if pattern in pdf_name_lower:
                    return pdf_file

        return None

    def _safe_request(
        self,
        url: str,
        method: str = "GET",
        max_retries: int = 5,
        timeout: int = 20,
        **kwargs,
    ) -> requests.Response:
        """
        Make HTTP request with session, headers, retry logic, and SSL fallback.

        Args:
            url: URL to request
            method: HTTP method (GET, POST, etc.)
            max_retries: Maximum number of retry attempts
            timeout: Request timeout in seconds
            **kwargs: Additional arguments for requests

        Returns:
            Response object

        Raises:
            RuntimeError: If all retries fail
        """
        network_errors = (
            ConnectionResetError,
            ProtocolError,
            requests.Timeout,
            requests.ConnectionError,
            requests.exceptions.SSLError,
        )

        ssl_error_occurred = False

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"HTTP request attempt {attempt}")

                request_headers = self.browser_headers.copy()
                if "headers" in kwargs:
                    request_headers.update(kwargs.pop("headers"))

                response = self.session.request(
                    method=method,
                    url=url,
                    headers=request_headers,
                    timeout=timeout,
                    allow_redirects=True,
                    **kwargs,
                )

                response.raise_for_status()
                logger.info(f"Successfully retrieved: {url}")
                return response

            except (
                ConnectionResetError,
                ProtocolError,
                requests.Timeout,
                requests.ConnectionError,
                requests.exceptions.SSLError,
            ) as e:
                error_msg = str(e)

                if "ssl" in error_msg.lower() or isinstance(
                    e, requests.exceptions.SSLError
                ):
                    if not ssl_error_occurred:
                        logger.warning(
                            f"SSL error detected, enabling SSL verification fallback"
                        )
                        self.session.verify = False
                        ssl_error_occurred = True
                        continue

                if attempt < max_retries:
                    delay = 2 ** (attempt - 1)
                    logger.warning(f"Request failed: {e}")
                    logger.info(f"Retrying request in {delay} seconds...")
                    time.sleep(delay)
                else:
                    logger.error(f"All {max_retries} attempts failed for: {url}")
                    raise RuntimeError(
                        f"Request failed after {max_retries} attempts: {e}"
                    ) from e

            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    raise
                if attempt < max_retries:
                    delay = 2 ** (attempt - 1)
                    logger.warning(f"HTTP error: {e}")
                    logger.info(f"Retrying request in {delay} seconds...")
                    time.sleep(delay)
                else:
                    raise

        raise RuntimeError(f"Request failed after {max_retries} attempts")

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

        logger.info(f"Fetching PDF for: {state.get_chapter_name()}")

        class_number = int(state.class_level) if state.class_level.isdigit() else 10
        subject = state.subject
        medium = state.medium
        chapter_number = (
            int(state.chapter_number)
            if str(state.chapter_number).isdigit()
            else int("".join(filter(str.isdigit, str(state.chapter_number))) or "1")
        )

        pdf_output_path = state.pdf_path
        if not pdf_output_path:
            raise RuntimeError("PDF path not initialized")

        existing_pdf = self._check_knowledge_folder(
            class_number, subject, chapter_number
        )
        if existing_pdf:
            logger.info(f"Found PDF in knowledge folder: {existing_pdf}")
            import shutil

            shutil.copy2(existing_pdf, pdf_output_path)
            logger.info(f"Copied PDF to: {pdf_output_path}")
            state.update("pdf_url", "local://knowledge")
            state.update("pdf_path", str(pdf_output_path))
            return str(pdf_output_path)

        try:
            pdf_candidates = self._scrape_ncert_pdf_url(
                class_number, subject, medium, chapter_number
            )

            for url in pdf_candidates:
                try:
                    logger.info(f"Trying PDF URL: {url}")
                    pdf_path = self._download_pdf_with_retry(url, pdf_output_path)
                    state.update("pdf_url", url)
                    state.update("pdf_path", str(pdf_path))
                    logger.info(f"PDF downloaded successfully: {pdf_path}")
                    return str(pdf_path)
                except Exception as e:
                    logger.warning(f"Failed: {url} -> {e}")

            raise RuntimeError("All NCERT PDF URL patterns failed")

        except Exception as e:
            logger.error(f"PDF retrieval failed: {e}", exc_info=True)
            raise RuntimeError(f"PDF retrieval failed: {e}") from e

    def _scrape_ncert_pdf_url(
        self, class_number: int, subject: str, medium: str, chapter_number: int
    ) -> List[str]:
        """
        Scrape NCERT textbook page to find chapter PDF URL.

        Args:
            class_number: Class number (e.g., 10)
            subject: Subject name (e.g., "Science", "Physics")
            medium: Medium ("English" or "Hindi")
            chapter_number: Chapter number (e.g., 11)

        Returns:
            List containing the matched chapter PDF URL

        Raises:
            RuntimeError: If textbook page not found or chapter not found
        """
        subject = subject.lower().strip()
        medium = medium.lower().strip()

        key = (class_number, subject, medium)

        if key not in self.BOOK_PAGE_MAP:
            raise RuntimeError(
                f"No NCERT book page mapping found for class={class_number}, subject={subject}, medium={medium}"
            )

        textbook_page = self.BOOK_PAGE_MAP[key]

        logger.info(f"Fetching NCERT textbook page: {textbook_page}")

        response = requests.get(
            textbook_page,
            headers=self.browser_headers,
            timeout=30,
            verify=self.session.verify,
        )

        soup = BeautifulSoup(response.text, "html.parser")

        pdf_links = soup.find_all("a", href=True)

        candidates = []

        for link in pdf_links:
            href = link.get("href", "")
            if not isinstance(href, str):
                continue

            if "textbook/pdf/" in href and href.endswith(".pdf"):
                full_url = urljoin(self.base_url, href)
                candidates.append(full_url)

        logger.info(f"Found {len(candidates)} chapter PDFs")

        chapter_str = str(chapter_number)

        for url in candidates:
            if chapter_str in url:
                logger.info(f"Matched chapter {chapter_number}: {url}")
                return [url]

        raise RuntimeError(f"Chapter {chapter_number} PDF not found on textbook page")

    def _download_pdf_with_retry(
        self, url: str, output_path: Path, max_retries: int = 5
    ) -> Path:
        """
        Download PDF with retry mechanism and fallback.

        Args:
            url: PDF URL
            output_path: Where to save the PDF
            max_retries: Maximum number of retry attempts

        Returns:
            Path to downloaded PDF

        Raises:
            RuntimeError: If all retries fail
        """
        network_errors = (
            ConnectionResetError,
            ProtocolError,
            requests.Timeout,
            requests.ConnectionError,
        )

        urls_to_try = [url]
        if url.endswith("1.pdf"):
            fallback_url = url.replace("1.pdf", "2.pdf")
            urls_to_try.append(fallback_url)
            logger.info(f"Fallback URL available: {fallback_url}")

        for attempt_url in urls_to_try:
            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(
                        f"Downloading NCERT PDF (attempt {attempt}/{max_retries})..."
                    )

                    response = requests.get(
                        attempt_url,
                        headers=self.browser_headers,
                        timeout=30,
                        stream=True,
                        verify=self.session.verify,
                    )

                    if response.status_code != 200:
                        raise RuntimeError(
                            f"Failed to download PDF: HTTP {response.status_code}"
                        )

                    content = response.content
                    with open(output_path, "wb") as f:
                        f.write(content)

                    file_size = len(content)
                    logger.info(f"Downloaded {file_size} bytes")

                    if file_size < 5120:
                        output_path.unlink(missing_ok=True)
                        raise ValueError(
                            f"Downloaded file too small ({file_size} bytes), likely invalid"
                        )

                    logger.info(f"PDF downloaded successfully: {output_path}")
                    return output_path

                except network_errors as e:
                    logger.warning(f"Download attempt {attempt} failed: {e}")
                    if attempt < max_retries:
                        delay = 2 ** (attempt - 1)
                        logger.info(f"Retrying in {delay} seconds...")
                        time.sleep(delay)
                    else:
                        logger.warning(f"All attempts failed for URL: {attempt_url}")

        raise RuntimeError(f"Failed to download PDF. Tried URLs: {urls_to_try}")


def create_pdf_agent() -> PDFAgent:
    """
    Factory function to create PDF agent.

    Returns:
        PDFAgent instance
    """
    return PDFAgent()
