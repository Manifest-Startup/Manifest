# Sub-processors

Last updated: 2026-04-19. Customers will be notified at least 30 days
before any addition takes effect (DPA §6).

| Sub-processor | Purpose | Personal data processed | Region | Safeguards |
|---|---|---|---|---|
| Replit, Inc. (US) | Application hosting & secrets management | All categories at rest in container memory, transient | US | DPA + SCCs (Module 3); SOC 2 Type II |
| Supabase (US/EU) | Managed Postgres, object storage | All persisted data | EU primary, US DR | DPA + SCCs; SOC 2 Type II; encryption at rest |
| OpenAI (US) | LLM inference for product features | Prompt content (transient, no training opt-in) | US | DPA + SCCs; zero data retention via API tier |
| Google (Gemini) | LLM inference for product features | Prompt content (transient, no training opt-in) | US/EU | DPA + SCCs; enterprise no-training tier |
| Stripe (US) | Payment processing | Cardholder data (handled by Stripe), email, name | US | PCI DSS Level 1; DPA + SCCs |
| SMTP provider (TBD) | Transactional email | Email, name, message body | EU/US | DPA + SCCs |
| Sentry / SIEM (self-hosted) | Error & security telemetry | Stack traces, user_id, IP hash | EU | Self-hosted, no third party |

Customer notification list: subscribe at trust@manifest.example to be
informed of changes at least 30 days in advance.
