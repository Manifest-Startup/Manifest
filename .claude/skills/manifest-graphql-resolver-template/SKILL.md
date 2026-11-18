---
name: manifest-graphql-resolver-template
description: Scaffold a Strawberry GraphQL resolver, its service-layer pair, and a focused test in one shot. Use when adding a new query or mutation to the Manifest GraphQL surface, so the resolver, service, types, and test all land together and follow project conventions.
---

# Manifest GraphQL Resolver Template

Manifest uses Strawberry GraphQL on FastAPI. Resolvers are thin; the work happens in the
service layer. New endpoints frequently miss one of: the type definition, the service
function, the auth gate, or the test — leading to broken contracts at PR review time.

## When to apply

Apply this skill whenever the task is "add a GraphQL query/mutation for X" or any change
that adds a new resolver to `backend/app/graphql/`.

## What to produce, in this order

1. **Type** — add or extend the relevant Strawberry type in `backend/app/graphql/types/<domain>.py`.
   Include only fields the client actually needs.
2. **Service function** — add a function in the matching domain package, `backend/app/services/<domain>/<module>.py`, that does
   the work. Pure-Python, no Strawberry imports. Async if it touches I/O.
3. **Resolver** — add the resolver to the `<Domain>Query` or `<Domain>Mutation` mixin in
   `backend/app/graphql/resolvers/<domain>.py` (a new mixin must be listed in `schema.py`). The resolver must:
   - validate input
   - check auth (anonymous, guest, authenticated, owner) — pick the strictest level the
     surface allows
   - call the service function
   - return the type defined in step 1
4. **Auth gate test** — write a test that asserts the auth gate rejects below-threshold
   callers. This is the single most-skipped step.
5. **Happy-path test** — write one test that asserts the resolver returns the expected
   shape for a valid input.
6. **Schema export** — if the project exports a `schema.graphql` artifact, regenerate it
   so the diff is in the same PR.
7. **Docs** — if this is a new public-facing query/mutation, update `docs/API.md` with a
   one-paragraph description and an example.

## Why this matters

A resolver that ships without an auth-gate test has only been tested on the happy path.
Manifest's marketplace surface mixes anonymous, guest, authenticated, owner, and investor
visibility — auth bugs are the highest-risk failure mode for the product. The template
keeps every new resolver consistent with the rest.
