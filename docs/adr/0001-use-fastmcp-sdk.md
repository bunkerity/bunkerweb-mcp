# 1. Use FastMCP SDK for MCP Protocol Implementation

## Context

The project requires an implementation of the MCP (Model Context Protocol) to expose BunkerWeb tools to LLMs (Large Language Models) like Claude. MCP is a standardized protocol that allows applications to expose contexts, tools, and resources to AI models.

Three main approaches were possible to implement this protocol:

1. Implement the MCP protocol from scratch
2. Use the minimal Python reference SDK
3. Use the official FastMCP SDK from Anthropic

The implementation choice directly impacts:
- Project maintainability
- Compatibility with future MCP protocol versions
- Amount of boilerplate code to write
- Available features (WebSocket, SSE, etc.)

## Options Considered

### Option 1: Custom Implementation

**Description**: Implement the MCP protocol by following the official specification.

**Advantages**:
- Full control over the implementation
- No external dependencies
- Possible optimization for our specific needs

**Disadvantages**:
- Significant development effort (estimate: 2-3 weeks)
- Risk of bugs and incompatibilities with the protocol
- Ongoing maintenance required to follow protocol evolution
- Reinventing the wheel for standard features

### Option 2: Python Reference Implementation SDK

**Description**: Use the minimal reference implementation provided by the MCP team.

**Advantages**:
- Official reference implementation
- Minimalist with few dependencies
- Protocol-compliant

**Disadvantages**:
- Limited features
- Requires a lot of boilerplate code
- Fewer abstractions to facilitate development
- No advanced support (WebSocket, SSE, etc.)

### Option 3: FastMCP SDK (Chosen)

**Description**: Use the official FastMCP SDK developed and maintained by Anthropic.

**Advantages**:
- Maintained by Anthropic (protocol creators)
- Automatic protocol updates
- High-level API facilitating development
- Integrated WebSocket and SSE support
- Built-in DNS rebinding protection
- Automatic JSON schema generation for tools
- Comprehensive documentation and examples
- Active community

**Disadvantages**:
- External dependency (but official and maintained)
- Less flexibility on certain implementation aspects
- Slightly larger package size

## Decision

**We chose to use the FastMCP SDK (Option 3)**.

### Main reasons:

1. **Productivity**: The SDK allows rapid startup and focus on business logic rather than protocol implementation.

2. **Maintenance**: By using the official SDK, we automatically benefit from MCP protocol updates and bug fixes.

3. **Advanced features**: WebSocket/SSE support, DNS rebinding protection, and other ready-to-use features.

4. **Compliance**: Guaranteed compatibility with the official MCP protocol.

5. **Community support**: Documentation, examples, and support from Anthropic and the community.

## Consequences

### Positive

- **Development speed**: The MCP server was implemented in ~2 days instead of 2-3 weeks
- **Robustness**: Using a proven and tested implementation
- **Scalability**: Automatic support for new MCP features
- **Reduced maintenance**: No need to maintain the protocol implementation
- **Cleaner code**: High-level API enabling more readable and maintainable code

### Negative

- **External dependency**: The project depends on a third-party package
  - **Mitigation**: The SDK is official and maintained by Anthropic
- **Learning curve**: Requires understanding the SDK API
  - **Mitigation**: Comprehensive documentation and examples provided
- **Package size**: ~200KB additional
  - **Negligible impact**: Acceptable for a backend server

### Neutral

- **Python compatibility**: Requires Python 3.10+ (already our target)
- **Transitive dependencies**: Pydantic, httpx, etc. (already used in the project)

## Notes

### References

- SDK Repository: https://github.com/modelcontextprotocol/python-sdk
- FastMCP Documentation: https://modelcontextprotocol.io/docs
- MCP Specification: https://spec.modelcontextprotocol.io/

### Current Implementation

The SDK is used in `src/bunkerweb_mcp/main.py` for:
- Registering tools via `@mcp.tool()` decorators
- Exposing resources via `@mcp.resource()`
- Exposing prompts via `@mcp.prompt()`
- Managing server lifecycle (WebSocket, stdio)

### Performance

Initial benchmarks show:
- Average latency: <5ms for SDK overhead
- Throughput: >1000 requests/second
- Memory footprint: ~50MB (including Python runtime)

These metrics are more than sufficient for our use case (human interactions with an LLM).

### Future Alternatives

If FastMCP SDK presents major limitations in the future, migration to a custom implementation remains possible because:
- Tool interface is decoupled from the SDK (see `src/bunkerweb_mcp/tools/`)
- MCP protocol is well documented
- Business logic does not directly depend on the SDK

This decision can be reviewed in ADR-XXXX if necessary.

### SDK 2.1.1 migration (2026-09-09)

The official SDK now calls its high-level server `MCPServer`. The adapter uses
`mcp.server.MCPServer` and the prompt/resource modules under `mcp.server.mcpserver`.
HTTP settings belong to `streamable_http_app`: JSON responses, stateless sessions,
`streamable_http_path="/"`, and the existing `TransportSecuritySettings` policy.
The FastAPI application retains its `/mcp` mount, configured log-access token
wrapper, and session-manager lifespan; the CLI continues to run stdio.

Registry tools retain text JSON results with `structured_output=False`; search
retains its structured result. Resource URIs are strings. Intentional tool and
resource failures use SDK exceptions so their messages remain visible; unexpected
exception details are withheld from protocol responses. Unknown log sources retain
their intentional error message. The shared registry also redacts unexpected errors
before exposing them through resources or legacy endpoints.

The `/tools` and `/rpc` search integration retains the existing SDK tool-manager
access. Successful payloads remain unchanged. Unexpected search exceptions now
produce an MCP tool error (or an HTTP 500 through `/rpc`) instead of a successful
response containing the exception text. `tests/test_mcp_protocol.py` exercises the
installed SDK through HTTP and stdio, including authentication, host/origin checks,
prompts, resources, wire result shapes, and shutdown.

Reference: [SDK 2.1.1 migration guide](https://github.com/modelcontextprotocol/python-sdk/blob/v2.1.1/docs/migration.md).
