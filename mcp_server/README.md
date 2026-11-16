# Manifest MCP Server

A professional Model Context Protocol (MCP) server that exposes the Manifest platform's functionality to AI agents. Transform ideas into investor-ready startups through natural language interactions.

## Overview

Manifest MCP Server enables AI agents (like Claude, GPT, and others) to interact with the Manifest platform programmatically. It provides tools for:

- **Idea Management**: Create, read, update, and delete startup ideas
- **AI Document Generation**: Generate Business Model Canvas, Pitch Decks, PRDs, and Patents
- **Marketplace Discovery**: Browse and discover public ideas
- **Social Interactions**: Follow users and upvote ideas
- **Investment Management**: Create investments, view portfolios, and analyze cap tables
- **Internal Quality Loop**: Audit public Manifest pages, summarize survey signals, emit deduped production signals, and create GitHub issues directly for the team

The consumer web app now also exposes a deterministic voice command catalog at `GET /api/voice-agent/capabilities`, so UI voice sessions and external agents can reason about the same app-control surface when documenting or mirroring behavior.

Session-scoped product features (pitch reel feed, publishing ideas, founder messaging, unread counts) are exposed primarily through **`POST /graphql`** with user JWT or cookies—not through the API-key REST surface. Agents that need those flows should use GraphQL or an authenticated browser context; see the repo root `docs/API.md` and `docs/public/api/index.html`. Publishing syncs `pitch_reels` and may schedule server-side video generation (configurable via env in `docs/API.md`). Founder messaging and pitch-reel likes/comments run on the user's linked Open Media account (`openMediaLink`).

This package targets a running Manifest deployment and mirrors the contracts documented
in the repo's `docs/API.md`. If a tool returns a 401, 403, or 404, first verify
`MANIFEST_API_URL`, `MANIFEST_API_TOKEN`, and any optional `MANIFEST_API_KEY` or
`MANIFEST_AGENT_LOOP_SECRET` values.

## Installation

### Using pip

```bash
pip install manifest-mcp
```

### Using uv (recommended)

```bash
uv add manifest-mcp
```

### From source

```bash
git clone https://github.com/manifest-startup/manifest.git
cd manifest/mcp_server
pip install -e .
```

## Quick Start

### 1. Set Environment Variables

```bash
# Required: API endpoint
export MANIFEST_API_URL="https://api.manifest.app"

# Required for authenticated operations
export MANIFEST_API_TOKEN="your-api-token"

# Required for the internal website, survey, and production-signal routes
export MANIFEST_AGENT_LOOP_SECRET="shared-internal-secret"
```

### 2. Run the Server

```bash
# STDIO transport (default, for local use)
manifest-mcp

# HTTP/SSE transport (for remote/web use)
manifest-mcp --transport sse --port 8080
```

### 3. Connect from AI Client

#### Claude Desktop

Add to your Claude Desktop configuration (`~/.claude/config.json`):

```json
{
  "mcpServers": {
    "manifest": {
      "command": "manifest-mcp",
      "env": {
        "MANIFEST_API_URL": "https://api.manifest.app",
        "MANIFEST_API_TOKEN": "your-token",
        "MANIFEST_AGENT_LOOP_SECRET": "shared-internal-secret"
      }
    }
  }
}
```

#### OpenAI Agents SDK

```python
from agents import Agent, Runner
from agents.mcp import MCPServerStdio

async with MCPServerStdio(
    name="Manifest",
    params={
        "command": "manifest-mcp",
        "env": {
          "MANIFEST_API_URL": "https://api.manifest.app",
          "MANIFEST_API_TOKEN": "your-token",
          "MANIFEST_AGENT_LOOP_SECRET": "shared-internal-secret"
        }
    }
) as server:
    agent = Agent(name="Startup Assistant", mcp_servers=[server])
    result = await Runner.run(agent, "Create a new idea for an AI-powered tutoring platform")
```

## Available Tools

### Idea Management

| Tool | Description |
|------|-------------|
| `list_ideas` | List all ideas owned by the current user |
| `get_idea` | Get detailed information about a specific idea |
| `create_idea` | Create a new startup idea |
| `update_idea` | Update an existing idea's title or description |
| `delete_idea` | Permanently delete an idea |

### AI Document Generation

| Tool | Description |
|------|-------------|
| `generate_business_model` | Generate a comprehensive Business Model Canvas |
| `generate_pitch_deck` | Generate an investor-ready pitch deck |
| `generate_prd` | Generate a Product Requirements Document |
| `generate_patent` | Generate a provisional patent draft |

### Marketplace & Discovery

| Tool | Description |
|------|-------------|
| `discover_ideas` | Browse the public ideas marketplace |
| `find_similar_ideas` | Find ideas similar to a given description |
| `audit_website_and_create_github_issues` | Run Manifest's internal website feedback loop and sync findings into GitHub Issues |
| `summarize_survey_feedback` | Summarize discovery and product-feedback signals for marketability / PMF review |
| `create_survey_feedback_github_issues` | Turn repeated survey themes into GitHub Issues |
| `emit_production_signal` | Ingest a deduped production anomaly signal (optional GitHub issue) |

### Social Interactions

| Tool | Description |
|------|-------------|
| `upvote_idea` | Upvote an idea to show support |
| `toggle_upvote` | Toggle your upvote on an idea |
| `follow_user` | Follow a user to see their ideas |
| `unfollow_user` | Unfollow a user |

### Investment Management

| Tool | Description |
|------|-------------|
| `get_portfolio` | View your investment portfolio |
| `invest_in_idea` | Create an investment in an idea (same `ideaId` as GraphQL `pitchReelsFeed` / `createInvestment`) |
| `get_cap_table` | View the capitalization table for an idea |

## Example Conversations

### Creating and Developing an Idea

```
User: Create a new startup idea for an AI-powered personal finance manager

Agent: [Uses create_idea tool]
Successfully created idea: AI Finance Manager
ID: abc-123

User: Generate a business model canvas for it

Agent: [Uses generate_business_model tool]
Here's your Business Model Canvas:

## Value Propositions
- Automated expense categorization
- Personalized savings recommendations
...
```

### Market Research

```
User: Find similar ideas to "sustainable food delivery"

Agent: [Uses find_similar_ideas tool]
Found 3 similar ideas:
1. EcoEats (85% similar) - Zero-waste meal delivery
2. GreenBite (72% similar) - Plant-based subscription boxes
3. LocalHarvest (68% similar) - Farm-to-table delivery
```

### Internal Website Feedback Loop

```
User: Audit https://manifeststartup.com and create GitHub issues for the biggest onboarding problems

Agent: [Uses audit_website_and_create_github_issues tool]
Website audit completed for https://manifeststartup.com.
Pages scanned: 6
Issue candidates: 4
GitHub issue creation: 3 created, 1 skipped as existing
```

### Internal Survey Feedback Loop

```
User: Summarize the last 90 days of Manifest survey feedback and tell me the strongest marketability signals

Agent: [Uses summarize_survey_feedback tool]
Survey feedback summary for the last 90 days.
Total responses: 42
Research responses: 26
Product feedback responses: 16
Top signals:
- Strongest value prop: Investor- or share-ready outputs without starting from scratch
- Biggest blocker: Doing market research or finding comparable companies
```

### Investment Analysis

```
User: Show me the cap table for idea xyz-456

Agent: [Uses get_cap_table tool]
Cap Table for Idea xyz-456:

| Holder      | Equity % | Type        |
|-------------|----------|-------------|
| Founder     | 70.00%   | founder     |
| Angel A     | 15.00%   | cash        |
| Advisor B   | 5.00%    | sweat_equity|

Total Allocated: 90.00%
Remaining: 10.00%
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MANIFEST_API_URL` | No | `http://localhost:8000` | Manifest API endpoint |
| `MANIFEST_API_TOKEN` | Yes* | - | Authentication token for API access |
| `MANIFEST_AGENT_LOOP_SECRET` | For internal feedback loops | - | Shared secret for `/api/internal/website-testing/*`, `/api/internal/survey-ops/*`, and `/api/internal/production-signals/*` |

*Required for authenticated operations (creating ideas, investments, etc.)

### Security Considerations

- **Never commit API tokens** to version control
- **Never commit internal loop secrets** to version control
- Use environment variables or a secrets manager
- For production deployments, use HTTPS endpoints
- Rotate tokens regularly

## Development

### Running Tests

```bash
cd mcp_server
pip install -e ".[dev]"
pytest tests/ -v
```

### Project Structure

```
mcp_server/
├── src/
│   └── manifest_mcp/
│       ├── __init__.py      # Package exports
│       ├── server.py        # MCP server and tools
│       └── client.py        # Manifest API client
├── tests/
│   ├── test_client.py       # API client tests
│   └── test_server.py       # MCP tools tests
├── pyproject.toml           # Package configuration
└── README.md                # This file
```

## API Reference

### Resources

#### `manifest://status`

Returns server status and configuration information.

```
# Manifest MCP Server Status

Version: 1.0.0
API Endpoint: https://api.manifest.app
Authenticated: Yes

## Available Tools
...
```

## Troubleshooting

### Common Issues

**Connection refused**
- Verify `MANIFEST_API_URL` is correct
- Check if the Manifest API server is running

**Authentication failed**
- Verify `MANIFEST_API_TOKEN` is set correctly
- Check if the token has expired

**Tool execution timeout**
- AI document generation can take 30-60 seconds
- Consider increasing timeout settings in your client

### Debug Mode

Enable debug logging:

```bash
export LOG_LEVEL=DEBUG
manifest-mcp
```

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Support

- **Documentation**: https://docs.manifest.app/mcp
- **Issues**: https://github.com/manifest/mcp-server/issues
- **Discord**: https://discord.gg/manifest
