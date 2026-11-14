# Reference: formats, QA, links

## Vector vs raster (logos)

| Role | Typical formats | Notes |
|------|-----------------|--------|
| Master (edit) | `.fig` (Figma), `.ai`, sometimes `.eps` | Client should retain editable source. |
| Print exchange | PDF (vector), EPS (legacy vendors) | Confirm CMYK/Pantone workflow with printer. |
| Web | SVG (preferred), PNG @2×/3× fallback | SVG: crisp on retina, small weight; avoid huge path counts. |
| Office / casual | PNG transparent, high-res | Not for large-format print. |

**Rule**: Never ship only JPG for a logo master. JPG has no transparency and compresses poorly for flat graphics.

## Figma SVG export settings (official)

From Figma Help ([Export formats and settings](https://help.figma.com/hc/en-us/articles/13402894554519-Export-formats-and-settings)):

- SVG supports: Ignore overlapping layers, Include bounding box, Include `id`, Outline text, Simplify stroke.
- **Outline text**: default-on when text selected—text becomes glyphs (not editable in SVG).
- **Simplify stroke**: helps non-center strokes map to SVG stroke model.
- SVG export is **1×**; scale in code/CSS or edit SVG dimensions.

## SVG QA checklist (post-export)

- [ ] Renders in **Chrome, Safari, Firefox** (gradient/clip differences happen).
- [ ] No stray **white rectangle** “background” in the SVG.
- [ ] **viewBox** includes full artwork; nothing clipped unintentionally.
- [ ] No **duplicate ids** if multiple instances on a page.
- [ ] **Hidden layers** from Figma not exported as `display:none` clutter (delete in source).
- [ ] **Gradients**: prefer simple linear/radial; exotic gradients may break.
- [ ] **File size** sane for web; run team SVGO preset if agreed.
- [ ] **Accessibility**: decorative vs informative; title/desc if meaningful.

## Professional process sources (external)

- Industry writeups on **brief → research → sketch → vector → black/white test → guidelines** align across practitioners; keep the sequence even when tools change.
- **File format guides** (vector vs raster, SVG for web, print PDF) are consistent: own the vector master.

## Naming pattern for assets (example)

`logos/<brand>/<variant>` e.g. `logos/acme/primary`, `logos/acme/mark-only` — supports slash-based export folders in Figma and clean repos.

## What not to do

- Logo from unlicensed stock “as the brand” without assignment.
- Over-complex marks (fine hairlines) that disappear when small.
- Designs that **only** work with a specific background color.
