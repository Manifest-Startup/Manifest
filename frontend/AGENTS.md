# Frontend — agent guide (child of [`../AGENTS.md`](../AGENTS.md))

Vite + React + TypeScript single-page app talking to the backend through Apollo Client (`/graphql`) and a few REST endpoints. Entry `src/index.tsx` → `src/App.tsx` (routes, lazy-loaded pages); `src/features/ios/AppIOS.tsx` is the iOS shell.

## Layout (parent → child)

- `src/features/<feature>/` — one folder per product area (`ideas`, `voice`, `pitchshorts`, `auth`, `account`, `messaging`, …), each with `components/`, optional `hooks/`, `utils/`, `__tests__/`.
- `src/features/core/` — shared infrastructure: `apollo/client.ts` (client, auth/CSRF headers), `apollo/queries.ts` (**every** GraphQL document lives here), `apollo/localState.ts`, error handling.
- `src/features/common-ui/` — shared primitives (`Button`, `Input`, `TextArea`, `PageHeader`, icons). Reuse before creating a new primitive.
- Imports use `baseUrl: src` (`import x from "features/core/logError"`) or relative paths; there are no `@alias/*` paths.

## Working here

- Find a component and everything that uses it before changing props: `python3 ../scripts/codegraph/query.py find <Name>` then `impact <file>`.
- New GraphQL operation: add the document to `core/apollo/queries.ts` and type the hook (`useQuery<Result, Vars>`) instead of reading untyped `data`.
- Pages are lazy-loaded in `App.tsx`; keep boot chunks small (`npm run size` enforces the budget via `scripts/check-boot-chunks.mjs`).
- Styling is Tailwind plus `src/index.css`; delete CSS together with the component that used it.
- Storybook (`npm run storybook`) only picks up `*.stories.tsx` next to real components; keep stories compiling or delete them.

## Checks

```bash
npx jest --silent            # unit tests (jsdom); run alone, parallel runs time out
npx tsc --noEmit -p .        # type check (Vite does not type-check during build)
npm run lint && npm run build
```

Or from the repo root: `python3 scripts/check.py --only frontend` (related tests only).
