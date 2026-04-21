# Handoff — Autograph Notifier: Dispatches page

Re-skin of the existing "Signed Records" listings page onto the **Autograph Notifier** brand system (par-avion / airmail aesthetic). **Structure and behavior are unchanged** — this is a visual pass only. No new components, no new data, no layout changes.

---

## About the design files

The files in `prototype/` are **design references created in HTML** — they show the intended look. They are not production code to copy wholesale. Your job is to port this skin onto the existing template / view in your codebase.

Good news: the existing page is already server-rendered HTML (see `prototype/original-index.html` for the "before"). The HTML structure in `prototype/Dispatches.html` (the "after") is byte-for-byte identical to the original inside `<body>` — only two header text nodes and the `<style>` block + Google Fonts link were changed. So in most cases **this is a CSS-only change** to the template that generates the page.

If you're porting to a framework (React/Vue/etc.) instead of the existing server template, the class names are stable — reuse them and apply `dispatches.css` as-is.

---

## Fidelity

**High-fidelity.** Pixel values, hex colors, font stacks, letter-spacing, border weights, and hover states are all final. Reproduce exactly.

---

## What to change

Exactly three things:

### 1. Replace the Google Fonts `<link>` tags in `<head>`

Remove the existing `DM Sans / DM Mono / Bebas Neue` link. Add the contents of `patch/fonts.html`:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400;1,8..60,600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```

### 2. Replace the inline `<style>...</style>` block

Drop in the contents of `patch/dispatches.css` (either paste inline, or move to an external stylesheet and `<link rel="stylesheet" href="dispatches.css">`). Source of truth is that file.

### 3. Update two strings in the header markup

```html
<!-- Before -->
<div class="site-title">Signed<span>&nbsp;Records</span></div>
<div class="header-meta">Autographed vinyl &amp; CDs</div>

<!-- After -->
<div class="site-title">Autograph<span>&nbsp;Notifier</span></div>
<div class="header-meta">Signed · Sealed · Delivered</div>
```

Also update `<title>` to `Dispatches — Autograph Notifier`.

**That's it.** Don't touch the table markup, the `data-hash` attributes, the `format-badge` inline `style="background:#6a5acd"` / `#2e8b57` colors, the search JS, or anything else. The new CSS overrides the inline badge colors via `!important` + an attribute selector.

---

## Design tokens

### Colors (Par Avion palette)

| Token | Value | Usage |
|---|---|---|
| `--paper` | `#F2E8D5` | Primary background, "cream paper" |
| `--paper-2` | `#EADFC7` | Row hover background, alt surface |
| `--surface` | `#FAF3E1` | Search input background |
| `--ink` | `#121212` | Primary text, header border |
| `--ink-2` | `#2B2623` | Secondary text |
| `--ink-3` | `#6B6358` | Muted text, meta labels |
| `--ink-4` | `#9B9180` | Placeholder, tertiary muted |
| `--red` | `#B91C1C` | Airmail red — CTAs, LP badge, section rule, "Today" stamp |
| `--red-deep` | `#8F1414` | Reserved for hover/press (not currently used) |
| `--blue` | `#1E3A8A` | Airmail blue — CD format badge only |
| `--border` | `#C9B994` | Warm tan — thead underline, thumb border on search input |
| `--border-soft` | `#DDD0B3` | Row dividers |

**Usage rule:** red and blue are the only saturated colors. Use them sparingly. LP badges are red; CD badges are blue. Everything else is paper + ink + warm neutrals.

### Typography

| Family | Role | Google Font |
|---|---|---|
| `Oswald` (condensed sans) | Display — site title, date labels, button text, eyebrow labels | `Oswald:400,500,600,700` |
| `Source Serif 4` | Body — listing titles, search input | `Source Serif 4:0,400;0,600;1,400;1,600` (italic included) |
| `JetBrains Mono` | Metadata — meta info, shop names, thead labels | `JetBrains Mono:400,500` |

Stacks (with fallbacks):
```css
--font-display: 'Oswald', 'Arial Narrow', Impact, sans-serif;
--font-body:    'Source Serif 4', 'Iowan Old Style', Georgia, serif;
--font-mono:    'JetBrains Mono', ui-monospace, monospace;
```

### Spacing & sizing

Inherited from the original page — not changed. Max content width `1200px`, header height `64px`, page padding `32px 24px 80px`.

### Borders & radii

- All corner radii are **0** (paper doesn't round).
- Thumbnails: `1px solid var(--ink)`.
- Buy button: `1.5px solid var(--red)`.
- Header bottom: `1px solid var(--ink)` (solid black, not the old faint white).
- Section underline (date heading): `1.5px solid var(--red)`.
- Row divider: `1px solid var(--border-soft)`.

### Shadows

None. No shadows, no glow, no blur. `backdrop-filter` is explicitly removed from the header.

---

## Components — what changed, cell by cell

### Header (`.site-header`)

- Background: `var(--paper)` (was navy)
- Border-bottom: `1px solid var(--ink)` (was `rgba(255,255,255,0.07)`)
- **Removed `backdrop-filter: blur(12px)`**
- Title "Autograph Notifier": `Oswald 600, 1.7rem, letter-spacing 0.14em, uppercase`. The word "Notifier" is red (`var(--red)`).
- Subtitle "Signed · Sealed · Delivered": `JetBrains Mono, 0.68rem, letter-spacing 0.14em, uppercase, var(--ink-3)`
- Listings count (right side): `JetBrains Mono, 0.72rem, var(--ink-3)`

### Search input (`.search-input`)

- Background: `var(--surface)`, border: `1px solid var(--border)`, **radius: 0** (was pill)
- Placeholder is italic, `var(--ink-4)`
- Focus state: border darkens to `var(--ink)`

### Date heading (`.date-heading`)

- Border-bottom: `1.5px solid var(--red)` (was `2px solid coral`)
- Label `(Tue) April 21`: `Oswald 600, 1.65rem, uppercase, letter-spacing 0.05em`
- Count "75 listings": `JetBrains Mono 0.72rem, var(--ink-3)`

### "Today" badge (`.today-badge`)

Restyled as a rubber-stamp chip:
- Background: `var(--paper)` (was solid coral)
- `1.5px solid var(--red)` outline
- Text color: `var(--red)`
- `Oswald 600, 0.62rem, letter-spacing 0.18em, uppercase`
- `transform: rotate(-2deg)` — stamped-on feel
- Radius: 0

### Table (`.listings-table`)

- `thead th`: `JetBrains Mono 0.62rem, letter-spacing 0.18em, uppercase, var(--ink-3), font-weight 500`. Bottom border: `1px solid var(--border)`.
- `tbody tr`: `1px solid var(--border-soft)` divider. Hover background: `var(--paper-2)`.
- Cell padding: `10px 12px`.

### Thumbnail (`.thumb`)

- 52×52, **object-fit: cover**
- `border: 1px solid var(--ink)`
- **Radius: 0** (was `4px`)

### Title line (`.title-line`)

- `Source Serif 4 regular, 0.98rem, line-height 1.35, color var(--ink)`
- (Was DM Sans 500 / bold white)

### Format badge (`.format-badge`)

Original HTML has inline `style="background:#6a5acd"` for LP and `style="background:#2e8b57"` for CD. The CSS overrides both:

```css
.format-badge {
  background: var(--red) !important;           /* LP → airmail red */
  color: var(--paper) !important;
  font-family: var(--font-display);
  font-size: 0.6rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 0 !important;
}
.format-badge[style*="2e8b57"] {
  background: var(--blue) !important;          /* CD → airmail blue */
}
```

**Important:** keep the inline `style="background:#2e8b57"` in the server-rendered markup — the attribute selector depends on it to pick out CD rows. If you refactor to a generator that uses a class like `.format-badge--cd` instead, simplify to:

```css
.format-badge         { background: var(--red); }
.format-badge--cd     { background: var(--blue); }
```

### Shop / Artist meta (`.td-artist`, `.td-shop`)

`JetBrains Mono 0.72rem, var(--ink-3)`.

### Price (`.td-price`)

Bumped to display face for numerics:
- `Oswald 600, 0.95rem`
- `font-variant-numeric: tabular-nums`
- `letter-spacing: -0.01em`
- Color: `var(--ink)`

### Buy button (`.buy-link`)

- **"BUY" label unchanged**
- `Oswald 600, 0.68rem, letter-spacing 0.18em, uppercase`
- `1.5px solid var(--red)`, background `var(--paper)`, text `var(--red)`
- Radius: 0
- Hover: fills red, text flips to paper

### Footer (`.site-footer`)

- Border-top: `1px solid var(--border)`
- Text: `JetBrains Mono 0.65rem, letter-spacing 0.18em, uppercase, var(--ink-3)`

---

## Interactions & behavior

**No changes.** The existing JS (search input wiring, `.hidden` toggling on rows, clear button, count updates) continues to work unchanged. Class names used by the JS (`#eventSearch`, `#searchClear`, `.date-section`, `.hidden`, `#headerCount`, `.td-title`, etc.) are all preserved.

Hover states:
- Rows: `background: var(--paper-2)`, 140ms transition
- Buy button: fill flips to red, 150ms
- Search input: border darkens on focus, 180ms

No other animations. No shadows appear on hover. No scale transforms.

---

## Responsive

Unchanged breakpoint at `720px`:
- Shop / price columns hide
- Site title shrinks to 1.3rem
- Listings count hides
- Search shrinks to 170px wide

---

## Assets

No new image assets are required. Listing thumbnails are hot-linked from the source shops' CDNs (Shopify, editmysite) exactly as before. If any start blocking hot-link requests, you'll need to cache/proxy them — this is a data-pipeline concern, not a design one.

Fonts come from Google Fonts CDN. If your codebase self-hosts fonts, pull `Oswald`, `Source Serif 4`, and `JetBrains Mono` from Google Fonts or your typography provider.

---

## Files in this handoff

```
design_handoff_dispatches/
├── README.md                         ← this file
├── patch/
│   ├── dispatches.css                ← the full new stylesheet
│   └── fonts.html                    ← <link> tags for Google Fonts
├── prototype/
│   ├── Dispatches.html               ← the redesigned page (the "after")
│   └── original-index.html           ← your original page (the "before") for diff reference
└── reference/
    └── original-screenshot.png       ← screenshot of the old dark-navy version
```

---

## Sanity-check checklist

After implementing, a quick visual pass should show:

- [ ] Page background is warm cream, not dark navy
- [ ] Header border is a thin solid black line (no blur)
- [ ] Logo reads "AUTOGRAPH NOTIFIER" in condensed caps; "NOTIFIER" is red
- [ ] `(TUE) APRIL 21` is followed by a red-outlined "TODAY" stamp tilted ~-2°
- [ ] Section underline beneath the date is red (not coral pink)
- [ ] LP badges are airmail red (`#B91C1C`)
- [ ] CD badges are airmail blue (`#1E3A8A`)
- [ ] Thumbnails have a thin black square border (no rounded corners)
- [ ] Prices render in condensed Oswald, tabular
- [ ] Buy buttons are red-outlined on cream, flip to filled-red on hover
- [ ] Row hover tints the row slightly darker cream
- [ ] No gradients, no shadows, no glassmorphism anywhere
