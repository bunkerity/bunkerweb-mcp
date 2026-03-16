"""Load testing script for MCP BunkerWeb server using Locust.

Usage:
    # Run with web UI
    locust -f locustfile.py --host http://localhost:8080

    # Run headless with specific parameters
    locust -f locustfile.py --host http://localhost:8080 \
           --users 100 --spawn-rate 10 --run-time 5m --headless

    # Generate HTML report
    locust -f locustfile.py --host http://localhost:8080 \
           --users 100 --spawn-rate 10 --run-time 5m --headless \
           --html report.html

Performance targets (Sprint 2):
    - Throughput: > 1000 req/s sustained
    - P95 latency: < 100ms
    - Error rate: 0% at 100 concurrent users
"""

from locust import HttpUser, TaskSet, between, task


class MCPUserBehavior(TaskSet):
    """User behavior simulating typical MCP client operations."""

    @task(5)
    def list_services(self):
        """List all services (most frequent operation)."""
        self.client.post(
            "/rpc",
            json={
                "tool": "mcp__bunkerweb__list_services",
                "params": {"with_drafts": True},
                "id": "list-services",
            },
            name="list_services",
        )

    @task(3)
    def list_instances(self):
        """List all instances."""
        self.client.post(
            "/rpc",
            json={
                "tool": "mcp__bunkerweb__list_instances",
                "params": {},
                "id": "list-instances",
            },
            name="list_instances",
        )

    @task(2)
    def global_config_read(self):
        """Read global configuration."""
        self.client.post(
            "/rpc",
            json={
                "tool": "mcp__bunkerweb__global_config_read",
                "params": {"full": False, "methods": False},
                "id": "global-config",
            },
            name="global_config_read",
        )

    @task(2)
    def list_bans(self):
        """List active bans."""
        self.client.post(
            "/rpc",
            json={
                "tool": "mcp__bunkerweb__list_bans",
                "params": {},
                "id": "list-bans",
            },
            name="list_bans",
        )

    @task(1)
    def list_tools(self):
        """List available tools."""
        self.client.get("/tools", name="list_tools")

    @task(1)
    def ping(self):
        """Ping BunkerWeb API."""
        self.client.post(
            "/rpc",
            json={
                "tool": "mcp__bunkerweb__ping",
                "params": {},
                "id": "ping",
            },
            name="ping",
        )


class MCPUser(HttpUser):
    """Simulated MCP client user."""

    tasks = [MCPUserBehavior]
    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks

    def on_start(self):
        """Called when a simulated user starts."""
        # Optionally authenticate or perform setup here
        pass


class CacheTestUser(HttpUser):
    """User for testing cache effectiveness (repeated identical requests)."""

    wait_time = between(0.1, 0.5)  # Very short wait to stress cache

    @task
    def repeated_list_services(self):
        """Repeatedly call the same endpoint to test cache hit rate."""
        self.client.post(
            "/rpc",
            json={
                "tool": "mcp__bunkerweb__list_services",
                "params": {"with_drafts": True},
                "id": "cache-test",
            },
            name="cached_list_services",
        )


# Example custom scenarios
class ReadOnlyUser(HttpUser):
    """User that only performs read operations (benefits from caching)."""

    wait_time = between(0.5, 2)

    @task(10)
    def list_services(self):
        self.client.post(
            "/rpc",
            json={
                "tool": "mcp__bunkerweb__list_services",
                "params": {"with_drafts": True},
                "id": "read-only",
            },
        )

    @task(5)
    def global_config(self):
        self.client.post(
            "/rpc",
            json={
                "tool": "mcp__bunkerweb__global_config_read",
                "params": {"full": False, "methods": False},
                "id": "read-only",
            },
        )


class WriteHeavyUser(HttpUser):
    """User that performs write operations (invalidates cache)."""

    wait_time = between(2, 5)

    @task(1)
    def create_service(self):
        """Note: This will fail if service already exists, but tests the endpoint."""
        self.client.post(
            "/rpc",
            json={
                "tool": "mcp__bunkerweb__create_service",
                "params": {
                    "server_name": f"test-{self.environment.runner.user_count}.example.com",
                    "is_draft": True,
                },
                "id": "write-heavy",
            },
            name="create_service (expected to fail)",
        )

    @task(5)
    def list_services(self):
        """Read after write to test cache invalidation."""
        self.client.post(
            "/rpc",
            json={
                "tool": "mcp__bunkerweb__list_services",
                "params": {"with_drafts": True},
                "id": "write-heavy",
            },
        )
