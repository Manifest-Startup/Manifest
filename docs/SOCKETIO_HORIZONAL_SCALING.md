# Socket.IO horizontal scaling

Last updated **May 3, 2026**.

The backend mounts a **python-socketio** `AsyncServer` in `backend/app/main.py` with CORS aligned to the FastAPI allowlist. That works for **a single API process**. Running **multiple replicas** behind a load balancer requires extra coordination so broadcasts and room membership work across instances.

## Problem

- In-memory room and session state lives in each process.
- Sticky sessions alone do not fix **cross-replica emits** (user A on pod 1, user B on pod 2).

## Recommended approach: Redis message manager

1. **Add Redis** reachable from all API replicas (managed Redis on your host is fine).
2. Configure Socket.IO with a **Redis adapter** so Engine.IO / Socket.IO messages fan out across processes.

At implementation time, follow the official `python-socketio` documentation for your installed version (Redis manager / `socketio.AsyncRedisManager` patterns). Typical steps:

- Install the extra dependency required for Redis (package name varies by version).
- Instantiate the manager with the Redis URL from environment (e.g. `SOCKETIO_REDIS_URL`).
- Pass the manager into `socketio.AsyncServer(...)`.

## Load balancer

- **Sticky sessions** (cookie or IP affinity) remain useful so a given browser’s Engine.IO polling / upgrade hits the same pod when possible, reducing reconnect churn.
- Sticky sessions are **not sufficient** without Redis; they are **complementary**.

## Environment variables (proposed)

- `SOCKETIO_REDIS_URL` — when unset, keep current single-process behavior.
- Document any TLS requirements for managed Redis.

## Security

- Redis should require auth; network isolate from the public internet.
- Do not log full Redis URLs with passwords.

## Testing

- Local docker-compose with two API containers + Redis; verify a broadcast from client connected to pod 1 reaches client on pod 2.

## References

- `backend/app/main.py` — `socketio.AsyncServer` setup.
- [docs/ARCHITECTURE_REFERENCE.md](ARCHITECTURE_REFERENCE.md) — Socket.IO in topology diagram.
