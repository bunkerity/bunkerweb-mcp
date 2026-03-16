# Architecture Decision Records (ADR)

This directory contains the Architecture Decision Records (ADR) for the mcp-bunkerweb project. ADRs document significant architectural decisions made during project development.

## What is an ADR?

An Architecture Decision Record (ADR) is a document that captures an important architectural decision made for the project, including:
- The context of the decision
- Options considered
- The final decision and its justification
- Expected consequences (positive and negative)

## Why use ADRs?

- **Traceability**: Understand why certain decisions were made
- **Onboarding**: Help new contributors understand the project
- **Avoid repetitive debates**: Document decisions already made
- **History**: Track architecture evolution over time

## ADR Index

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [0001](0001-use-fastmcp-sdk.md) | Use FastMCP SDK for MCP Protocol Implementation | Accepted | 2024-11-15 |
| [0002](0002-externalize-search-service.md) | Externalize Search Service for Semantic Documentation | Accepted | 2024-11-20 |
| [0003](0003-pydantic-v2-validation.md) | Adopt Pydantic V2 for Data Validation | Accepted | 2024-11-25 |
| [0004](0004-async-httpx-client.md) | Use Async HTTPX Client for API Calls | Accepted | 2024-12-01 |

## ADR Creation Process

1. **Copy the template**: Use [template.md](template.md) as a starting point
2. **Number it**: Use the next sequential number (e.g., 0005)
3. **Title**: Use a short, descriptive title (e.g., "Use Redis for Caching")
4. **Fill sections**: Document context, options, decision, and consequences
5. **Propose**: Create a PR with status "Proposed"
6. **Review**: Get feedback from the team
7. **Accept**: Once approved, change status to "Accepted" and merge

## Possible Statuses

- **Proposed**: ADR under discussion
- **Accepted**: Decision accepted and implemented
- **Deprecated**: Decision replaced but kept for history
- **Superseded by ADR-XXXX**: Pointer to the replacement ADR

## Format

All ADRs follow the format defined in [template.md](template.md):
- Number and title
- Date
- Status
- Context
- Options considered
- Decision
- Consequences (positive, negative, neutral)
- Additional notes

## Best Practices

- **Be concise**: An ADR should be readable in 5-10 minutes
- **Objectivity**: Present facts and trade-offs objectively
- **Include context**: Explain the problem to solve, not just the solution
- **Document alternatives**: Show that multiple options were considered
- **Update the index**: Always add your ADR to the table above

## References

- [Documenting Architecture Decisions - Michael Nygard](http://thinkrelevance.com/blog/2011/11/15/documenting-architecture-decisions)
- [ADR GitHub Organization](https://adr.github.io/)
- [When Should I Write an Architecture Decision Record](https://engineering.atspotify.com/2020/04/when-should-i-write-an-architecture-decision-record/)
