# A simpler Manifest workspace

Research and implementation review: September 10, 2026.

## Direction

Treat an idea as a note: a compact library, an editable title, and an open writing surface. The founder's words should occupy the useful space. Navigation and generated documents remain available without surrounding every element with a separate card.

The previous workspace stacked outer page padding, 12px column gaps, two collapsed rails of 76–84px each, 20–24px header padding, another title box, and about 25px of padding inside the editor. The new workspace removes the outer gutters and column gaps. Closing a panel releases its entire column. The note has one inset: 20px on desktop and 16px on phones.

## Research and decisions

| Reference | Relevant pattern | Manifest decision |
| --- | --- | --- |
| [Apple Notes: view notes on Mac](https://support.apple.com/en-gb/guide/notes/-apd8b73d28be/mac) | A notes list sits beside the selected note; list and gallery serve different browsing needs. | Use compact title rows for text ideas. Keep document links under the selected idea. |
| [Notion: page styling and width](https://www.notion.com/help/customize-and-style-your-content) | Full width reduces page margins; secondary page options are customizable. | Make the workspace full width by default. Keep comfortable internal text padding without a narrow centered app shell. |
| [Notion: sidebar navigation](https://www.notion.com/help/navigate-with-the-sidebar) | The sidebar exposes page hierarchy and can be opened or closed. | Keep the existing idea/document hierarchy and saved panel preferences. |
| [Apple: sidebars](https://developer.apple.com/design/human-interface-guidelines/sidebars) | Sidebars need substantial space; disclosure and hiding controls help, and compact screens need other navigation arrangements. | A 240px desktop library; a 280px optional context panel. On a fresh narrow-screen visit, begin with panels closed and keep labeled toggles available. |
| [Apple: layout](https://developer.apple.com/design/human-interface-guidelines/layout) | Prioritize essential information, group related controls, and let scrollable content reach screen edges. | Use adjoining surfaces with one-pixel separators, a compact toolbar, and a full-width note. |
| [NN/g: progressive disclosure](https://www.nngroup.com/articles/progressive-disclosure/) | Defer secondary options so the main task is easier to learn and perform. | Show collaborator skills in an expandable section and related ideas on demand. |
| [NN/g: aesthetic and minimalist design](https://www.nngroup.com/articles/aesthetic-minimalist-design/) | Every additional element competes with relevant information. | Remove duplicated rename labels, decorative backgrounds, heavy shadows, and nested frames. Retain focus indicators and accessible control names. |

These sources support the interaction direction. Exact widths, spacing, colors, and typography are Manifest-specific design judgments, not measurements copied from those products.

## Design rules

- One writing surface with a directly editable title. Title and body share a left edge.
- White/light neutral surfaces, existing dark mode, subtle separators, and restrained color for actions and selection.
- A single row of history, sharing, and focus controls above the title.
- New Idea remains the primary library action. Existing sort, keyboard navigation, document links, and saved layout choices remain available.
- Related ideas are loaded when their panel is opened. Hiding the library keeps its state mounted. Toggling panels or focus must not remount the note or discard a draft.
- Rich text keeps visible heading hierarchy, list markers, quotes, and code formatting.
- The iOS-style web view uses the same unboxed note and compact list rows. This is a React interface change; it does not alter a native iOS target.

## Verification boundary

The browser review uses the real React workspace components with synthetic sample content and a local API fixture. It validates visual layout and interactions, not a production login, backend persistence, document generation, or physical-device behavior. The temporary fixture is not part of the production build.

Verification results: the production frontend build, focused lint, and 63 tests in eight suites passed. Browser checks at 390px, 768px, and 1440px showed no horizontal document overflow. Light/dark appearance, panel toggles, focus/Escape, title editing, and the existing iOS-style web layout were reviewed. A full TypeScript check remains blocked by account/API typing errors outside this design change; it is not reported as passing.

Publication validation on latest main also identified and repaired two pre-existing build blockers in separate commits: unavailable integration icon exports and mismatched Tiptap packages. The editor packages are aligned to 3.31.3, and server content synchronization uses the supported `emitUpdate: false` option. The release checkout passed its build and lint, the workspace browser smoke (including title editing), and 78 focused tests across nine suites.
