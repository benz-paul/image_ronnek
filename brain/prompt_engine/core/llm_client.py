"""
LLM Client wrapper for the prompt engine.
Provides a unified interface for LLM calls.
"""

import os
from typing import Optional, Any
from langchain_openai import ChatOpenAI


class LLMClient:
    """
    Wrapper for LLM calls with consistent interface.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_retries: int = 3,
        timeout: int = 120,
    ):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")

        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            max_retries=max_retries,
            timeout=timeout,
        )

    def call(self, prompt: str, attachments: Optional[list] = None) -> str:
        """
        Call the LLM with a prompt.

        Args:
            prompt: The user prompt
            attachments: Optional list of file paths

        Returns:
            LLM response as string
        """
        from langchain_core.messages import HumanMessage

        messages = [HumanMessage(content=prompt)]
        response = self.llm.invoke(messages)
        return response.content

    def call_with_json_output(self, prompt: str) -> dict:
        """
        Call the LLM and parse JSON response.

        Args:
            prompt: The user prompt

        Returns:
            Parsed JSON response
        """
        from core.utils.llm_json_parser import parse_llm_json

        response = self.call(prompt)
        return parse_llm_json(response)


def create_llm_client(
    model: str = "gpt-4o-mini",
    temperature: float = 0.7,
    max_retries: int = 3,
    timeout: int = 120,
) -> LLMClient:
    """
    Create and return an LLM client instance.

    Args:
        model: Model name to use
        temperature: Sampling temperature
        max_retries: Maximum number of retries for failed calls
        timeout: Timeout in seconds

    Returns:
        LLMClient instance
    """
    return LLMClient(
        model=model,
        temperature=temperature,
        max_retries=max_retries,
        timeout=timeout,
    )
