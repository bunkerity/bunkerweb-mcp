"""WebSocket rate limiting implementation."""

from __future__ import annotations

import time
from collections import defaultdict


class WebSocketRateLimiter:
    """Simple in-memory rate limiter for WebSocket connections."""

    def __init__(self, max_messages: int, window_seconds: int):
        """Initialize rate limiter.

        Args:
            max_messages: Maximum number of messages allowed in the window
            window_seconds: Time window in seconds
        """
        self.max_messages = max_messages
        self.window_seconds = window_seconds
        # Store timestamps of messages per connection ID
        self._message_times: dict[str, list[float]] = defaultdict(list)

    def check_rate_limit(self, connection_id: str) -> bool:
        """Check if connection has exceeded rate limit.

        Args:
            connection_id: Unique identifier for the WebSocket connection

        Returns:
            True if rate limit is exceeded, False otherwise
        """
        now = time.time()
        cutoff = now - self.window_seconds

        # Clean up old timestamps
        self._message_times[connection_id] = [
            ts for ts in self._message_times[connection_id] if ts > cutoff
        ]

        # Check if limit exceeded
        if len(self._message_times[connection_id]) >= self.max_messages:
            return True

        # Record this message
        self._message_times[connection_id].append(now)
        return False

    def cleanup_connection(self, connection_id: str) -> None:
        """Remove tracking data for disconnected connection.

        Args:
            connection_id: Unique identifier for the WebSocket connection
        """
        if connection_id in self._message_times:
            del self._message_times[connection_id]
