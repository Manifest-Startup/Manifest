# GraphQL package layout

- [`schema.py`](schema.py): composes the root `Query` / `Mutation` from the domain mixins, the default-deny auth extension (`PUBLIC_FIELDS`, `FIELD_PERMISSIONS`) and `schema`. Mixin order is the schema's field order.
- [`resolvers/<domain>.py`](resolvers/): `<Domain>Query` / `<Domain>Mutation` mixins with the resolvers (their docstrings feed the CLI catalog and agent tools); [`resolvers/shared.py`](resolvers/shared.py) holds helpers used by several domains (`_require_full_account`, AI cache, request IP / user agent).
- [`types/<domain>.py`](types/): Strawberry types, inputs and mappers. Older domain modules [`pitch_reel_types.py`](pitch_reel_types.py) and [`open_media_types.py`](open_media_types.py) follow the same idea.

To add a field, put it in the matching domain mixin (or add a mixin and list it in `schema.py`).

See [docs/ARCHITECTURE_REFERENCE.md](../../../docs/ARCHITECTURE_REFERENCE.md) and [docs/ASYNC_JOB_QUEUE_DESIGN.md](../../../docs/ASYNC_JOB_QUEUE_DESIGN.md) for broader backend design notes.
