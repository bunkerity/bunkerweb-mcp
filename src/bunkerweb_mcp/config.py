"""Application configuration powered by Pydantic settings."""

from functools import lru_cache
from pathlib import Path
from typing import cast

from pydantic import AnyHttpUrl, Field, PositiveInt, SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Runtime settings resolved from environment variables or `.env`."""

    bunkerweb_base_url: AnyHttpUrl = Field(
        default=cast(AnyHttpUrl, "http://localhost:8888"),
        description="Base URL for the BunkerWeb control-plane API.",
        alias="BUNKERWEB_BASE_URL",
    )
    bunkerweb_api_token: SecretStr | None = Field(
        default=None,
        description="Static API token used for Authorization bearer header (masked in logs).",
        alias="BUNKERWEB_API_TOKEN",
    )
    bunkerweb_basic_username: str | None = Field(
        default=None,
        description="Username for HTTP Basic authentication.",
        alias="BUNKERWEB_BASIC_USERNAME",
    )
    bunkerweb_basic_password: SecretStr | None = Field(
        default=None,
        description="Password for HTTP Basic authentication (masked in logs).",
        alias="BUNKERWEB_BASIC_PASSWORD",
    )
    request_timeout_seconds: float = Field(
        default=30.0,
        ge=1.0,
        description="HTTP request timeout in seconds.",
        alias="BUNKERWEB_REQUEST_TIMEOUT_SECONDS",
    )
    max_retries: PositiveInt = Field(
        default=3,
        description="Maximum number of retries for transient HTTP errors.",
        alias="BUNKERWEB_MAX_RETRIES",
    )
    retry_backoff_initial: float = Field(
        default=0.5,
        ge=0.0,
        description="Initial backoff delay in seconds.",
        alias="BUNKERWEB_RETRY_BACKOFF_INITIAL",
    )
    retry_backoff_max: float = Field(
        default=5.0,
        ge=0.0,
        description="Maximum backoff delay in seconds.",
        alias="BUNKERWEB_RETRY_BACKOFF_MAX",
    )
    websocket_token: SecretStr | None = Field(
        default=None,
        description="Optional shared-secret required by MCP WebSocket clients (masked in logs).",
        alias="BUNKERWEB_WEBSOCKET_TOKEN",
    )
    log_level: str = Field(
        default="INFO",
        description="Application log level.",
        alias="BUNKERWEB_LOG_LEVEL",
    )
    prompt_catalog_path: Path | None = Field(
        default=None,
        description="Optional filesystem path to the tool prompt catalog (JSON).",
        alias="BUNKERWEB_PROMPT_CATALOG",
    )

    # Search Service Settings
    search_mode: str = Field(
        default="remote",
        description="Search mode: 'remote' to use search API, 'disabled' to disable search.",
        alias="SEARCH_MODE",
    )
    search_api_url: str = Field(
        default="http://localhost:8000",
        description="URL of the remote search service API.",
        alias="SEARCH_API_URL",
    )
    search_timeout: float = Field(
        default=10.0,
        ge=1.0,
        description="Search API request timeout in seconds.",
        alias="SEARCH_TIMEOUT",
    )

    # MCP Transport Security Settings
    mcp_enable_dns_rebinding_protection: bool = Field(
        default=True,
        description="Enable DNS rebinding protection for MCP endpoints (recommended for production).",
        alias="MCP_ENABLE_DNS_REBINDING_PROTECTION",
    )
    mcp_allowed_hosts: str = Field(
        default="localhost,127.0.0.1",
        description="Comma-separated list of allowed Host header values for MCP endpoints. "
        "Include both hostname and hostname:port variants. Example: 'localhost,localhost:8080,apps,apps:8085'",
        alias="MCP_ALLOWED_HOSTS",
    )
    mcp_allowed_origins: str = Field(
        default="",
        description="Comma-separated list of allowed Origin header values for MCP endpoints (CORS).",
        alias="MCP_ALLOWED_ORIGINS",
    )

    # Performance Settings (Sprint 2)
    rate_limit_enabled: bool = Field(
        default=False,
        description="Enable rate limiting on endpoints.",
        alias="RATE_LIMIT_ENABLED",
    )
    rate_limit_tools: str = Field(
        default="30/minute",
        description="Rate limit for /tools endpoint (format: '30/minute'). Only applies if RATE_LIMIT_ENABLED=true.",
        alias="RATE_LIMIT_TOOLS",
    )
    rate_limit_rpc: str = Field(
        default="100/minute",
        description="Rate limit for /rpc endpoint (format: '100/minute'). Only applies if RATE_LIMIT_ENABLED=true.",
        alias="RATE_LIMIT_RPC",
    )
    rate_limit_ws: str = Field(
        default="500/minute",
        description="Rate limit for /ws WebSocket endpoint (format: '500/minute'). Only applies if RATE_LIMIT_ENABLED=true.",
        alias="RATE_LIMIT_WS",
    )
    cache_enabled: bool = Field(
        default=True,
        description="Enable caching layer for read-only operations.",
        alias="CACHE_ENABLED",
    )

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "populate_by_name": True,
    }

    def get_api_token(self) -> str | None:
        """Get API token value securely.

        Returns:
            The API token string, or None if not configured.

        Note:
            Use this method cautiously and never log the returned value.
        """
        if self.bunkerweb_api_token is None:
            return None
        return self.bunkerweb_api_token.get_secret_value()

    def get_basic_password(self) -> str | None:
        """Get Basic auth password securely.

        Returns:
            The password string, or None if not configured.

        Note:
            Use this method cautiously and never log the returned value.
        """
        if self.bunkerweb_basic_password is None:
            return None
        return self.bunkerweb_basic_password.get_secret_value()

    def get_websocket_token(self) -> str | None:
        """Get WebSocket token securely.

        Returns:
            The WebSocket token string, or None if not configured.

        Note:
            Use this method cautiously and never log the returned value.
        """
        if self.websocket_token is None:
            return None
        return self.websocket_token.get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached `Settings` instance."""

    return Settings()
