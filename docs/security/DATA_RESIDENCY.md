# Data Residency

_Last reviewed: 2026-04-19 (Task #12)._

## Pinning model

Each user (and SSO tenant) carries a `data_region` column. Supported
regions today: `us`, `eu`, `uk`, `apac`, `ca` (`SUPPORTED_REGIONS` in
`app.security.data_residency`).

The application worker advertises its own region via the
`MANIFEST_DATA_REGION` environment variable (defaults to `us`).

## Enforcement

`app.security.data_residency.assert_region_match(tenant_region)` is the
write-path gate. It raises `RegionMismatchError` when the tenant's pinned
region differs from the worker's region, blocking the write before any
data hits storage.

Read-path defence-in-depth is provided by
`filter_to_current_region(rows)`, which drops cross-region rows that
should never have been served by this worker.

## Today vs roadmap

- **Today** — Single primary database in `us`. All tenants default to
  `data_region='us'` so no writes are blocked. The infrastructure is in
  place to refuse cross-region writes the moment a second region's
  database is provisioned.
- **Roadmap** — When EU launch lands, the `eu` region will run its own
  Postgres + application workers with `MANIFEST_DATA_REGION=eu`. Tenants
  whose `data_region='eu'` will be routed there exclusively, and
  `assert_region_match` will block any worker in another region from
  inserting their data.

## Tenant onboarding

When an Enterprise customer chooses a region:
1. Their SSO tenant config is written with `data_region` set during
   provisioning (`sso_tenant_configs.data_region`).
2. Newly-provisioned users inherit that region. Existing users' regions
   are updated by an explicit migration agreed with the customer.
3. Their backups are pinned to the same region (see
   `BACKUP_AND_RESTORE.md`).

Changing a tenant's region after data has been written requires a
documented migration window — there is no automatic in-place region
change because it would violate the residency commitment in the contract.
