# Website design consistency

Reviewed September 10, 2026. Extends [the Notes-style workspace](NOTES_WORKSPACE.md).

## Shared rules

- Use the existing sans-serif family, restrained weight, and sentence-case labels. Page headings use `manifest-page-title` (24–32px); document headings keep a readable hierarchy.
- Secondary pages use a 1200px maximum shell with one 20px desktop / 16px mobile horizontal inset. Reading content is narrower where useful. The note workspace and messaging panes remain full width with adjoining surfaces.
- Use neutral backgrounds and subtle separators. Reserve shadows for floating UI, color for status and selection, and brand colors for integration icons.
- Use `Button` for actions and `manifest-control` plus the corresponding variant for navigation links. Inputs use `manifest-field`; labels and errors must stay associated with the field. Shared touch controls are at least 44px high.
- Use `PageHeader` for simple page introductions. Avoid oversized heroes and repeated summaries on utility pages.
- Use 8px control radii and 10–12px panel/dialog radii. Avatars, status dots, and the floating voice launcher may stay circular.
- Keep keyboard focus visible and respect reduced-motion preferences. Selected controls expose their state accessibly.
- Code samples scroll within their containers. Grid children and long account text must not force the page wider than the viewport.

## Surfaces covered

| Surface | Changes |
| --- | --- |
| Landing and About | Shared typography, quiet backgrounds, simpler preview and action links; demo disclosure retained |
| Documentation, user guide, API, terms and privacy | Compact shared headers, lighter navigation, readable document surfaces, contained code blocks |
| Sign-in, sign-up and password recovery | One focused form column, consistent inputs and actions, visible labels and errors |
| Account, integrations and security | Compact profile and theme controls, consistent tabs, dark-mode integration cards and search |
| Billing, admin costs and idea qualification | Shared heading sizes, neutral surfaces and labels, compact card radii |
| Messaging | Adjoining inbox/thread panes, compact conversation rows, quiet composer and shared actions |
| Surveys and privacy/feedback UI | Single inset, flatter surfaces, wrapping banner actions |
| Collaboration and history dialogs | Shared neutral dialog surface, compact corners and controls |
| iOS-style React pages | Same form and surface rules, compact account header, existing mobile navigation retained |
| Pitch Reels and voice | Consistent control/panel geometry; immersive media and state-driven voice orb retained |

## Verification

- Production frontend build and changed-file lint pass.
- The final focused run passed 159 tests across 24 suites, covering documentation, controls, workspace, navigation, account integrations, privacy, messaging, collaboration, voice, Pitch Reels and project analytics.
- Browser checks used actual public React routes and temporary synthetic-data fixtures for authenticated screens. The fixture is excluded from production and is not committed.
- Reviewed mobile (390px), tablet (768px), and desktop (1440px) layouts. Checked public routes, workspace, account, billing, admin and qualification; reviewed mobile messaging, iOS-style forms, integration search and the inactive voice surface.
- Corrected API authentication cards that overflowed on phones: code samples now scroll internally. Checked both light and dark appearance, theme selection, integration filtering, form mode switching and the sharing dialog.
- Authentication, payments, invitations, publishing, remote persistence and live microphone sessions were not exercised. Synthetic empty/error states do not verify production data access. Build output retains its existing large-chunk advisory.
