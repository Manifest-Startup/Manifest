---
name: professional-logo-figma-design
description: Guides professional logo design, brand marks, and vector/UI design workflows in Figma and comparable tools (Illustrator, Penpot). Covers brief-to-delivery process, vector standards, SVG/PDF/PNG deliverables, Figma structure, and export QA. Use when designing or reviewing logos, wordmarks, icons, design systems, Figma files, SVG assets, brand guidelines, or handoff to developers.
disable-model-invocation: true
---

# Professional logo & Figma-class design

## Role

Act as a senior brand/identity designer: strategy first, craft second, deliverables third. A logo is a business tool, not decoration—it must read at favicon size, work in one color, and survive real media (print, embroidery, app chrome, social avatars).

## Non-negotiables (professional bar)

- **Master artwork is vector** (editable paths). Raster-only “logos” are not acceptable as source; PNG/JPG are *exports*, not masters.
- **Monochrome must work**: if the mark depends on color or gradients to be understood, it fails receipts, stamps, and single-ink printing.
- **Scalable geometry**: minimal smart anchor points; smooth curves; consistent stroke/optical weight when scaled.
- **Originality & rights**: avoid trace-stealing; note when concepts need trademark screening (agent does not provide legal advice—flag for counsel).
- **System thinking**: primary, reversed, icon-only, wordmark-only, and clear-space rules where relevant.

## Process (use in order)

1. **Brief**: audience, competitors, personality, constraints (where the mark will appear), **must-nots**.
2. **Research**: category codes, differentiation, naming if tied to wordmark.
3. **Diverge**: many sketches/thumbnails; avoid falling in love with one idea too early.
4. **Converge**: select 3–5 directions → refine; test **small** (16–24px height) and **single color**.
5. **Vector build**: precise paths; grid/snap where it helps optical balance (not mechanical symmetry for its own sake).
6. **Context tests**: app icon, favicon, header, merch mock, busy photo background.
7. **Deliver**: layered source, exports, **mini guidelines** (colors, type if any, clear space, don’ts).

## Figma workflow (design + handoff)

### File hygiene

- **Frames** per deliverable (e.g. `Logo / Primary`, `Logo / Icon`) with explicit export settings.
- **Name layers for humans and code**—layer names often become SVG `id`s; avoid `Group 47`.
- **Components & variants** for colorways (light/dark, one-color) and optional sizes *if* the team uses a design system; keep the **master vector** editable.
- **Boolean ops**: flatten when the shape is final to reduce SVG noise; remove hidden layers before export.
- **Strokes**: Figma exports SVG strokes in ways that can surprise devs—**outline stroke** (`Outline stroke`) when you need predictable fills or print alignment; know when the team wants strokes kept for CSS.
- **Text**: export “Outline text” when fidelity matters more than editable text inside SVG; otherwise uncheck and ensure fonts are available where the SVG loads.
- **Pixel grid**: enable snap for UI marks that must render crisp at 1×; half-pixel coordinates blur on some displays.

### SVG export (summary)

Align with [Figma’s SVG export notes](https://help.figma.com/hc/en-us/articles/13402894554519-Export-formats-and-settings): strokes may export as fills; “Simplify stroke” helps inside/outside strokes map to SVG’s center stroke; use **Outline text** deliberately; remove clip/mask artifacts by simplifying structure.

**Before export checklist**: outline strokes (if that’s the team rule) → flatten heavy booleans → delete hidden layers → meaningful names → export → open in browser(s) → optimize if the codebase uses SVGO (coordinate with dev preset).

### Plugins (optional; team-dependent)

Teams often use **SVG Export** / **Clean SVG Export** / **Advanced SVG Export**-style plugins for **consistent SVGO presets**—never substitute plugins for correct structure in the file.

## Other “design tool” expectations

- **Adobe Illustrator** remains common for **final logo mastery** (precision paths, print color). Figma is strong for **collaboration, variants, and dev handoff**; know which tool owns the **canonical .ai** if the client requires it.
- **Penpot**, **Affinity Designer**, **Sketch**: same vector rules—masters editable, exports purpose-specific.
- **Raster tools** (Photoshop, etc.): mood boards and textures only—not logo construction.

## When the user is in Cursor / code

- Prefer **SVG** for web headers; consider **`currentColor`** for themeable single-color marks.
- Ensure **viewBox** is correct; avoid duplicate `id`s when multiple SVGs sit on one page.
- Offer **accessible** patterns: decorative vs informative images, `aria-hidden` where appropriate.

## Output the agent should produce

- **Critique**: legibility, distinctiveness, genre clichés, scalability, monochrome, technical red flags.
- **Actionable steps**: what to simplify, rename, outline, or test next.
- **Deliverable list** tailored to use case (see [reference.md](reference.md)).

## Deep reference

Format matrix, extended SVG QA, and links: [reference.md](reference.md).
