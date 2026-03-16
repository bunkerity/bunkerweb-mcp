"""Lightweight HTTP client for BunkerWeb search service."""

from __future__ import annotations

import logging
import os
from enum import StrEnum
from typing import Any

import httpx
from pydantic import BaseModel

LOGGER = logging.getLogger(__name__)


class SearchMode(StrEnum):
    """Search mode configuration."""

    REMOTE = "remote"  # Use remote search API
    DISABLED = "disabled"  # Disable search feature


class SearchResult(BaseModel):
    """Represents a search result from the API."""

    text: str
    title: str
    url: str
    category: str
    score: float
    chunk_id: int
    doc_id: str


class SearchClient:
    """Lightweight HTTP client for remote search service."""

    def __init__(
        self,
        api_url: str,
        timeout: float = 10.0,
        enabled: bool = True,
    ):
        """
        Initialize search client.

        Args:
            api_url: Base URL of the search API (e.g., http://search-service:8000)
            timeout: Request timeout in seconds
            enabled: Whether search is enabled
        """
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        self.enabled = enabled
        self._http_client: httpx.AsyncClient | None = None

    @classmethod
    def from_env(cls) -> SearchClient:
        """Create client from environment variables."""
        mode = os.getenv("SEARCH_MODE", "remote")
        api_url = os.getenv("SEARCH_API_URL", "http://localhost:8000")
        timeout = float(os.getenv("SEARCH_TIMEOUT", "10.0"))

        enabled = mode == SearchMode.REMOTE

        if not enabled:
            LOGGER.info("Search is disabled (SEARCH_MODE=%s)", mode)

        return cls(
            api_url=api_url,
            timeout=timeout,
            enabled=enabled,
        )

    async def __aenter__(self) -> SearchClient:
        """Async context manager entry."""
        if self.enabled:
            self._http_client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def search(
        self,
        query: str,
        limit: int = 5,
        category: str | None = None,
        min_score: float = 0.2,
        max_content_length: int = 500,
    ) -> list[SearchResult]:
        """
        Search BunkerWeb documentation.

        Args:
            query: Search query
            limit: Maximum number of results (1-50)
            category: Optional category filter
            min_score: Minimum relevance score (0.0-1.0)
            max_content_length: Max characters per result (0=unlimited)

        Returns:
            List of search results

        Raises:
            RuntimeError: If search is disabled
            httpx.HTTPError: If API request fails
        """
        if not self.enabled:
            LOGGER.warning("Search is disabled - returning empty results")
            return []

        # Ensure client is created
        if not self._http_client:
            self._http_client = httpx.AsyncClient(timeout=self.timeout)

        try:
            response = await self._http_client.post(
                f"{self.api_url}/search",
                json={
                    "query": query,
                    "limit": limit,
                    "category": category,
                    "min_score": min_score,
                    "max_content_length": max_content_length,
                },
            )
            response.raise_for_status()

            data = response.json()
            results = data.get("results", [])

            return [SearchResult(**r) for r in results]

        except httpx.HTTPError as e:
            LOGGER.error(f"Search API request failed: {e}")
            # Return empty results instead of raising
            # This makes search failures graceful
            return []

    async def health_check(self) -> dict[str, Any]:
        """
        Check search service health.

        Returns:
            Health status dict

        Raises:
            httpx.HTTPError: If health check fails
        """
        if not self.enabled:
            return {"status": "disabled"}

        if not self._http_client:
            self._http_client = httpx.AsyncClient(timeout=self.timeout)

        response = await self._http_client.get(f"{self.api_url}/health")
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def list_categories(self) -> list[str]:
        """
        List available documentation categories.

        Returns:
            List of category names

        Raises:
            httpx.HTTPError: If request fails
        """
        if not self.enabled:
            return []

        if not self._http_client:
            self._http_client = httpx.AsyncClient(timeout=self.timeout)

        response = await self._http_client.get(f"{self.api_url}/categories")
        response.raise_for_status()

        data = response.json()
        return data.get("categories", [])  # type: ignore[no-any-return]


__all__ = ["SearchClient", "SearchMode", "SearchResult"]
