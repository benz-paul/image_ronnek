"""
LLM Client module with retry mechanism and structured output handling.
"""

import os
import json
from typing import Any, Optional, Dict, Union
from pathlib import Path

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from core.logger import logger


class LLMClient:
    """Reusable LLM wrapper with retry mechanism and timeout handling."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_retries: int = 3,
        request_timeout: int = 120,
    ):
        """
        Initialize the LLM client.

        Args:
            model: Model name to use
            temperature: Sampling temperature
            max_retries: Maximum retry attempts for failed calls
            request_timeout: Request timeout in seconds
        """
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.request_timeout = request_timeout

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")

        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            max_retries=max_retries,
            timeout=request_timeout,
        )

        logger.info(f"LLM Client initialized: {model}")

    def call(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        attachments: Optional[list] = None,
    ) -> str:
        """
        Call the LLM with retry mechanism.

        Args:
            prompt: User prompt to send
            system_message: Optional system message
            attachments: Optional list of file paths to attach (e.g., PDF)

        Returns:
            LLM response as string

        Raises:
            Exception: If all retries fail
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = []

        if system_message:
            messages.append(SystemMessage(content=system_message))

        if attachments:
            content_parts: list[Union[str, dict]] = [{"type": "text", "text": prompt}]

            for attachment_path in attachments:
                if Path(attachment_path).exists():
                    with open(attachment_path, "rb") as f:
                        import base64

                        encoded = base64.b64encode(f.read()).decode("utf-8")
                        content_parts.append(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:application/pdf;base64,{encoded}"
                                },
                            }
                        )

            messages.append(HumanMessage(content=content_parts))
        else:
            messages.append(HumanMessage(content=prompt))

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(f"LLM call attempt {attempt}/{self.max_retries}")
                response = self.llm.invoke(messages)
                return response.content

            except Exception as e:
                logger.warning(f"LLM call failed (attempt {attempt}): {str(e)}")
                if attempt == self.max_retries:
                    logger.error(
                        f"All {self.max_retries} retries exhausted", exc_info=True
                    )
                    raise
                continue

        raise RuntimeError("LLM call failed unexpectedly")

    def call_with_json_output(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        attachments: Optional[list] = None,
        json_schema: Optional[type[BaseModel]] = None,
    ) -> Dict[str, Any]:
        """
        Call the LLM and parse JSON response.

        Args:
            prompt: User prompt
            system_message: Optional system message
            attachments: Optional file attachments
            json_schema: Optional Pydantic model for structured output

        Returns:
            Parsed JSON response as dictionary
        """
        response = self.call(prompt, system_message, attachments)

        try:
            json_response = self._extract_json(response)
            return json_response
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw response: {response[:500]}...")
            raise

    def _extract_json(self, response: str) -> Dict[str, Any]:
        """
        Extract JSON from LLM response.

        Args:
            response: Raw LLM response

        Returns:
            Parsed JSON dictionary

        Raises:
            ValueError: If no valid JSON found
        """
        response = response.strip()

        if response.startswith("```json"):
            response = response[7:]
        elif response.startswith("```"):
            response = response[3:]

        if response.endswith("```"):
            response = response[:-3]

        response = response.strip()

        return json.loads(response)

    def call_with_retry(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        attachments: Optional[list] = None,
        max_attempts: Optional[int] = None,
    ) -> str:
        """
        Explicit retry method with custom attempt count.

        Args:
            prompt: User prompt
            system_message: Optional system message
            attachments: Optional file attachments
            max_attempts: Custom max attempts (overrides default)

        Returns:
            LLM response
        """
        original_max = self.max_retries
        if max_attempts:
            self.max_retries = max_attempts

        try:
            return self.call(prompt, system_message, attachments)
        finally:
            self.max_retries = original_max


def create_llm_client() -> LLMClient:
    """
    Factory function to create LLM client.

    Returns:
        Configured LLMClient instance
    """
    return LLMClient()
