"""Simple focused load test for MCP server endpoints."""

from locust import HttpUser, between, task


class SimpleMCPUser(HttpUser):
    """Simple user testing only the /tools endpoint."""

    wait_time = between(0.5, 2)

    @task(10)
    def list_tools(self):
        """Test GET /tools endpoint - the main MCP discovery endpoint."""
        self.client.get("/tools", name="GET /tools")

    @task(1)
    def health_check(self):
        """Test health endpoint if it exists."""
        with self.client.get("/health", catch_response=True, name="GET /health") as response:
            if response.status_code == 404:
                # Health endpoint might not exist, that's ok
                response.success()
