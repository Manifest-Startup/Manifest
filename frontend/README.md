# Manifest frontend

React single-page app for Manifest: **Vite**, **TypeScript**, **Tailwind CSS**, **Apollo Client** (GraphQL), and **Redux Toolkit**. Real-time updates use **Socket.IO** where enabled.

## Prerequisites

- Node.js 18+ and npm
- Backend running (default GraphQL at `http://localhost:8000/graphql`) or `REACT_APP_GRAPHQL_URL` pointing at your API

## Scripts

| Command | Purpose |
|---------|---------|
| `npm start` | Dev server on port 3000 (`vite --host 0.0.0.0`) |
| `npm run build` | Production build to `build/` |
| `npm test` | Jest |
| `npm run lint` | ESLint on `src/` |
| `npm run sync:docs` | Copy root `docs/` legal/API markdown into `public/docs/` for in-app pages |

## Documentation

- Repository root [`README.md`](../README.md) — full stack overview and routes
- [`docs/QUICKSTART.md`](../docs/QUICKSTART.md) — local setup
- [`docs/API.md`](../docs/API.md) — API reference

This project was originally bootstrapped with Create React App and **now uses Vite**; ignore legacy CRA-only docs elsewhere.
