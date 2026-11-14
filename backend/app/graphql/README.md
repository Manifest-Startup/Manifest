# GraphQL package layout

The main schema remains [`schema.py`](schema.py) (Strawberry `Query` / `Mutation` entrypoints).

Domain-specific **types and mappers** can live alongside it to keep `schema.py` maintainable—for example pitch reel GraphQL types in [`pitch_reel_types.py`](pitch_reel_types.py). Resolvers stay in `schema.py` until a larger split (e.g. merged `Query` classes) is justified.

See [docs/ARCHITECTURE_REFERENCE.md](../../../docs/ARCHITECTURE_REFERENCE.md) and [docs/ASYNC_JOB_QUEUE_DESIGN.md](../../../docs/ASYNC_JOB_QUEUE_DESIGN.md) for broader backend design notes.
