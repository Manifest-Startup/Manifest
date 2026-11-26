---
title: Manifest API integration
description: Use Manifest's public REST API to manage a user's startup ideas and generate startup documents.
license: Apache-2.0
---
# Manifest API integration

Use this skill when a user asks to create, list, update, delete, or generate documents for their Manifest startup ideas.

## Authentication

The user must create an API key in their signed-in Manifest account and provide it to the agent through the agent's secure credential interface. Never ask the user to paste a key into an ordinary chat. Send the key only as `Authorization: Bearer <key>` to `https://manifeststartup.com/api/v1`. Keys are scoped; reads need `ideas.read`, writes and generation need `ideas.write` (or the coarse `read` and `write` scopes).

## Available operations

- `GET /api/v1/` returns public API information without a key.
- `GET /api/v1/ideas` lists ideas belonging to the key owner.
- `POST /api/v1/ideas` creates an idea from a title and optional description.
- `GET /api/v1/ideas/{idea_id}` reads one of the owner's ideas.
- `PATCH /api/v1/ideas/{idea_id}` updates its title or description.
- `DELETE /api/v1/ideas/{idea_id}` deletes that idea; get explicit user approval before deleting.
- `POST /api/v1/ideas/{idea_id}/generate` creates requested documents: `business_model_canvas`, `pitch_deck`, `prd`, or `patent`. Generation runs synchronously and may take time.
- `GET /api/v1/usage` reads usage information.

## References

Read [the API reference](https://manifeststartup.com/docs/api) and [OpenAPI](https://manifeststartup.com/openapi.json). Errors use JSON; on HTTP 429, back off. Generated content is a draft for the founder to review, not legal, financial, or investment advice.
