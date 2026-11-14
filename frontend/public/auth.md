# Manifest API authentication

The Manifest REST and MCP APIs use account-created API keys with Bearer authentication. This is an API-key scheme, not OAuth 2.0.

## Create a key

Sign in at [Manifest](https://manifeststartup.com/auth), open account settings, and create an API key under API access. Choose the minimum scopes required:

- `ideas.read` allows listing and reading your ideas.
- `ideas.write` allows creating, updating, deleting, and generating documents for your ideas.

Keep the key in your agent's secure credential store. Do not paste it into ordinary chat, commit it to source control, or share it with another user.

## Send the key

For REST requests, send:

```http
Authorization: Bearer manifest_sk_...
```

The same header authenticates to the Streamable HTTP server at `https://manifeststartup.com/mcp`. Except for `GET /api/v1/`, API operations require a valid key. A key can access only the owner's data, and the backend checks its scopes on each operation.

See the [API reference](https://manifeststartup.com/docs/api) and [OpenAPI specification](https://manifeststartup.com/openapi.json) for request details. A `401` indicates a missing or invalid key; a `403` indicates insufficient scope or ownership; a `429` indicates a rate or monthly limit.
