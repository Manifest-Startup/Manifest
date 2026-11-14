# Saved-ideas loading improvements

Verified locally on September 12, 2026, against main `ee5a8dc6` with its locked frontend dependencies. This report distinguishes local build and synthetic browser evidence from production deployment.

## Causes and changes

- Session and account synchronization depended on `useQuery` callbacks removed in Apollo Client 4. The shared `useSafeQuery` wrapper now delivers completion and error callbacks from settled results after render. Stable results do not redeliver callbacks just because an inline callback changes. Refetches can deliver completion again. The regression tests use the real Apollo client; all three failed before the fix.
- Both desktop and mobile ideas lists imported the rich-text editor and document components before rendering the list. The editor now loads when an idea is opened, within its own loading boundary.
- PowerPoint export code was loaded through the document renderer even when merely opening a note. It now loads on Download PowerPoint.
- The idle voice assistant requested the entire idea, including generated documents, just to obtain its description. Voice and the editor now share `GetIdeaCore`; an integration test confirms that simultaneous consumers produce one request.
- The backend idea resolver selected large document columns even for `GetIdeaCore`. Its database projection now includes only requested text columns plus small identity metadata. Named fragments, inline fragments, and aliases are supported through Strawberry's parsed selections and a fixed column allowlist. Owner filtering and authentication remain enforced.
- The profile resolver's synchronous database read now runs in a worker thread and selects only the three fields needed for session initialization.
- Lazy editor mounting now waits until commit and ignores disposed editor instances. Enabling editing after a read does not emit a user edit, and idea-switch cleanup runs before cached-content hydration so it cannot erase the note. Regression tests cover cached note switching, delayed text arrival, and enabling editing without an unintended save.
- Mobile list loading and failed reads no longer display “No ideas yet” prematurely; failed reads offer a retry.

Apollo's migration documentation confirms the callback removal: https://www.apollographql.com/docs/react/migrating/apollo-client-4-migration.

## Measurement

Build the baseline and modified source with the same package lock. Starting at the emitted `IdeasPage` chunk, walk static module imports recursively, count each chunk once, and sum file sizes and individual gzip sizes. Dynamic imports are excluded. Shared application/runtime dependencies are included in both totals.

| Desktop ideas route static JavaScript | Baseline | Modified |
| --- | ---: | ---: |
| Uncompressed bytes | 1,687,977 | 801,125 |
| Sum of gzip bytes | 527,212 | 243,842 |

The compressed dependency graph is approximately 54% smaller. This measures downloadable code, not a claim of 54% faster end-to-end production response time. Server latency, caching, account size, and connection quality still affect actual timing.

## Verification

- Full backend suite: 1,029 passed, 21 skipped (Python 3.12 local environment).
- Full frontend suite: 412 passed across 69 suites. Production build and boot-chunk guard passed against the current main dependency lock.
- Standalone TypeScript checking is blocked by the same existing missing jest-dom type and TypeScript 6 configuration errors on both baseline and modified source; it is not reported as passing.
- Real-Apollo regression coverage checks session callback delivery, network error delivery, unchanged-data refetch completion, and voice/editor request deduplication.
- GraphQL integration coverage checks note-only column selection, fragments/aliases, and authentication/owner filters.
- Browser verification uses the compiled production build with a localhost fixture providing 80 synthetic ideas. No customer notes or production credentials are used. The baseline session gate stayed on Loading after a valid response; the fixed list displayed all 80 ideas. Opening, switching, and returning to cached notes displayed their saved text at desktop and 390-pixel viewport widths. Fixture logs showed core-note reads and no save mutations or full-document fetches during these reads. This is responsive-browser evidence, not a physical iOS test.
- The Jest transformer now uses the automatic JSX runtime, matching the app Babel configuration and allowing the real Tiptap dependencies to run in regression tests.
- Four pre-existing panel-button tests expected a removed `border` utility class. Their assertions now target the shared secondary-button style while retaining icon and target-size checks.

The changes do not require a database migration. Publishing a Git commit or GitHub Release is separate from deploying the hosting provider. Recheck authenticated production list loading after deployment before reporting real-account timing improvements.
