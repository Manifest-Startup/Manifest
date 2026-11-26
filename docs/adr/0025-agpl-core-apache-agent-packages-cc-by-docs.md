# 0025. AGPL-3.0 core, Apache-2.0 agent packages, CC BY 4.0 docs

- Status: accepted
- Date: 2026-11-26

## Context

Manifest has been MIT since the public repository opened on 2026-11-14. MIT lets anyone take the whole app, rename it and run it as a closed hosted service without crediting the project or sharing changes. At the same time we want three things MIT gives us:

- agents, registries and package indexes treat Manifest as plain open source (an OSI-approved license they recognise)
- people can embed the MCP server, agent plugin, skills and extensions anywhere, including in closed products
- researchers and writers can reuse and cite the docs and papers

The owner also distributes the iOS app through the App Store, whose terms conflict with the AGPL, so contributions must be relicensable by the maintainer.

## Decision

1. **Past releases stay MIT.** Every release up to and including v2.51.2 remains under the MIT License. The new terms apply from the commit that adds `NOTICE`.
2. **Core app and server: AGPL-3.0-only.** Root `LICENSE` is the unmodified GNU AGPL v3 text, so GitHub and scanners detect it. Network use counts as distribution, so hosted forks must share their source.
3. **Two section 7 additional terms in `NOTICE`:**
   - 7(b): keep the plain-text line `Based on Manifest (https://github.com/Manifest-Startup/Manifest) by Mihir Kavishwar.` in every interactive interface (About, credits or footer) and in documentation. The web footer models this.
   - 7(e): no trademark rights beyond [`TRADEMARKS.md`](../../TRADEMARKS.md); forks and hosted versions use their own name and logo.
4. **Agent-facing packages: Apache-2.0**, each with its own `LICENSE` and `NOTICE` (Apache section 4(d)): `mcp_server/` (MCP server and CLI, thin clients of the hosted API), `agent-plugin/` (plugin manifests, skills, commands, registry metadata), `extensions/manifest-dev/`, `skills/manifest-api/`, and the root marketplace manifests that install the plugin.
5. **Prose docs and research writing: CC-BY-4.0** ([`docs/LICENSE.md`](../LICENSE.md)). Code samples follow the license of the code they belong to.
6. **Contributions:** DCO sign-off (`git commit -s`) plus the grant in [`CLA.md`](../../CLA.md): the license of the directory, and a perpetual, irrevocable right for the maintainer to relicense.
7. **Citation:** `CITATION.cff` (license `AGPL-3.0-only`) and a "Cite Manifest" README section. No `.zenodo.json`, so Zenodo reads `CITATION.cff` once the owner enables the GitHub integration.

## Alternatives considered

- **Keep MIT.** Most reach, but allows closed, rebranded clones with no credit.
- **FSL-1.1-ALv2 (Functional Source License, converts to Apache-2.0 after two years).** Rejected: it is not OSI-approved, so agents, MCP registries and package indexes flag it as "source available", and it blocks competing uses that we are happy to allow under copyleft.
- **AGPL for everything.** Rejected: it would stop people from embedding the MCP server, plugin and skills in their own agents, which is the main way Manifest spreads.

## Consequences

- Using the hosted service, the API or the MCP endpoint creates no obligations for anyone.
- Self-hosters and forks must publish their changes, keep the attribution line and pick a new name.
- Every `license` field (pyproject, package.json, plugin manifests, Docker label) matches the map; a new package needs its own `LICENSE` when it is Apache-2.0.
- The dependency license scan skips Manifest's own private packages; copyleft dependencies stay disallowed so the Apache packages and App Store build remain distributable.
- `NOTICE` wording has not had legal review yet; trademark registration and Zenodo DOIs are owner actions.
