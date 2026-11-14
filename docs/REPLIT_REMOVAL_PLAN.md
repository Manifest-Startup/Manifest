# Replit removal plan

Replit is the rollback environment during the Cloudflare migration. Do not delete the deployment, database, secrets, generated files, or domain configuration merely because Cloudflare staging is healthy.

Replit may be retired only after all of these are true:

- Production database backup, restore, and table-level reconciliation are complete.
- Generated PDFs/videos have been copied to durable storage and checksum-verified.
- Existing and newly generated file URLs work after Cloudflare container recreation.
- Login, sessions, signup, guest merge, GraphQL, REST, Socket.IO, email, OAuth, AI generation, and background work pass on the production route.
- Apex and `www` DNS, TLS, callback URLs, and non-web DNS records are verified.
- Cloudflare logs/costs are stable through the agreed observation window.
- A rollback to the preserved Replit deployment has been exercised or documented with exact current deployment identifiers.
- The owner explicitly authorizes retirement after reviewing the evidence.

If a gate fails after cutover, route traffic back to the preserved Replit origin, stop writes to the failed target, and reconcile any writes made during the Cloudflare window before retrying.
