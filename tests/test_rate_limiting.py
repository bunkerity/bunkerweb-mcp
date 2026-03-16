"""Tests for rate limiting functionality."""

import pytest
from httpx import ASGITransport, AsyncClient

from bunkerweb_mcp.main import create_app


@pytest.fixture
def app_with_rate_limiting(monkeypatch):
    """Create app with rate limiting enabled."""
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_TOOLS", "5/minute")
    monkeypatch.setenv("RATE_LIMIT_RPC", "10/minute")
    return create_app()


@pytest.mark.asyncio
async def test_tools_endpoint_with_rate_limiting_enabled(app_with_rate_limiting):
    """Test that rate limiting is configured when enabled."""
    # Verify that the app has rate limiting configured
    assert hasattr(app_with_rate_limiting.state, "limiter")
    assert app_with_rate_limiting.state.limiter is not None

    # Basic smoke test - endpoint should still work
    transport = ASGITransport(app=app_with_rate_limiting)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/tools")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_rpc_endpoint_with_rate_limiting_enabled(app_with_rate_limiting):
    """Test that RPC endpoint works with rate limiting enabled."""
    # Basic smoke test - endpoint should still work (may return 404 without valid tool)
    transport = ASGITransport(app=app_with_rate_limiting)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"tool": "mcp__bunkerweb__ping", "params": {}, "id": 1}
        response = await client.post("/rpc", json=payload)
        # Should not be rate limited initially (404 is expected without backend)
        assert response.status_code in [200, 404, 502]  # Various valid responses


@pytest.mark.asyncio
async def test_rate_limiting_disabled_by_default():
    """Test that rate limiting is disabled by default."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Make many requests - should not be rate limited
        for _ in range(50):
            response = await client.get("/tools")
            assert response.status_code == 200


@pytest.mark.asyncio
async def test_websocket_rate_limiter():
    """Test WebSocket rate limiter class."""
    from bunkerweb_mcp.rate_limiter import WebSocketRateLimiter

    limiter = WebSocketRateLimiter(max_messages=5, window_seconds=60)
    connection_id = "test-connection"

    # First 5 messages should be allowed
    for _ in range(5):
        assert not limiter.check_rate_limit(connection_id)

    # 6th message should be rate limited
    assert limiter.check_rate_limit(connection_id)

    # Cleanup should remove tracking data
    limiter.cleanup_connection(connection_id)
    assert connection_id not in limiter._message_times
