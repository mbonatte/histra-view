# HiStrA Workbench — design direction

**Status:** pilot implemented on the 3D model workspace. Material properties and
results are intentionally still on the previous visual layer, pending review of
this direction.

## 1. What the audit found

The current interface works, but its visual language is not specific to
engineering software. Measured on the 3D screen before the pilot:

- **82 distinct text colours, 61 background colours and 12 corner radii** in a
  single screen. Colour is being used for emphasis everywhere, so nothing is
  emphasised.
- **23 font sizes**, with 8, 9, 10, 11, 12 and 13px all used for similar
  secondary information.
- Primary actions, active tabs, selected rows, status dots and scientific
  overlays all share the same saturated teal. Interface accent and data colour
  collapse into one signal.
- Cards-within-panels and 6–12px radii make the shell compete with the model.
- A 66px app bar, 46px panel headers and 58px entity rows spend vertical space
  that belongs to the viewport.
- The 3D scene is framed by equally strong chrome on both sides. Settings are a
  flat list without grouping.

## 2. Direction: Modern Engineering Workbench

**Graphite workbench, one quiet accent, data stays data.**

- The 3D viewport is the document. Panels are tools, not cards.
- Structure comes from alignment, spacing and 1px hairlines. No decorative
  gradients, glows, large shadows or nested cards.
- One desaturated steel-blue accent is used for selection, focus and the single
  primary action.
- Scientific colours (material swatches, load amber, restraint teal, stress and
  displacement ramps, chart series) live in a separate token group and are never
  reused as UI states.
- Typography is Inter, with a 9/10/11/12/14px scale. Technical labels are
  uppercase, tracked, and smaller than values. Numeric columns use tabular
  figures; keys and coordinates use a restrained mono stack.
- Density is preserved: controls are 28px high, entity rows 42px, main app bar
  48px, footer 26px.

## 3. Tokens

Defined in `static/workbench.css` (`:root`).

### Surface

| Token | Value | Use |
| --- | --- | --- |
| `--wb-canvas` | `#0a0c0f` | 3D viewport |
| `--wb-bg` | `#0e1114` | application background |
| `--wb-surface` | `#121519` | header, panels, footer |
| `--wb-surface-raised` | `#171b20` | menus, messages |
| `--wb-inset` | `#0d1013` | inputs, select fields |
| `--wb-hover` | `#1a1f25` | hover state |
| `--wb-active` | `#20262d` | pressed/selected control |
| `--wb-line` | `#242a31` | hairline |
| `--wb-line-strong` | `#343c45` | control border, floating tool |

### Text and interface accent

| Token | Value | Use |
| --- | --- | --- |
| `--wb-text` | `#dfe4e9` | primary text |
| `--wb-text-2` | `#9da7b1` | secondary text |
| `--wb-text-3` | `#747f89` | labels, metadata |
| `--wb-text-4` | `#5a646d` | disabled, hints |
| `--wb-accent` | `#8fb3c7` | focus, active underline |
| `--wb-accent-strong` | `#a9c9da` | active text |
| `--wb-accent-soft` | `rgba(143,179,199,.11)` | selected row tint |
| `--wb-accent-fill` | `#9bbacb` | one primary action |

Semantic colours are deliberately sparse: `--wb-success`, `--wb-warning`,
`--wb-danger`.

### Scientific / data palette

| Token | Value | Reserved for |
| --- | --- | --- |
| `--data-material` | `#93a7b8` | neutral mesh legend |
| `--data-load` | `#ffbc66` | applied loads |
| `--data-restraint` | `#60d9c5` | restraints |
| `--data-compression` | `#335cd1` | compression contours |
| `--data-tension` | `#e64033` | tension contours |
| `--data-hinge` | `#ef4444` | plastic hinges |
| `--data-thrust` | `#38bdf8` | thrust line |
| `--data-chart-1/2/3` | `#69d8c2` / `#f5b86e` / `#91a9ff` | response-curve series |

Material colours embedded in HRX files are preserved exactly. The current
displacement and stress ramps are not touched.

### Typography

| Role | Size / line | Weight | Notes |
| --- | --- | --- | --- |
| Panel label / eyebrow | 9px / 1.2 | 600 | uppercase, 0.1em tracking |
| Metadata / field label | 10px / 1.4 | 400 | secondary text |
| Control / body | 11px / 1.45 | 400–500 | Inter |
| Document title | 14px / 1.3 | 600 | model / panel title |
| Section title | 14–16px / 1.3 | 600 | later phases |
| Numeric values | 9.5–11px | 400 | mono, tabular |

Spacing follows a 4px grid: 2, 4, 6, 8, 12, 16, 20, 24, 32. Radii are 2px for
small controls, 3px for controls, 4px for floating surfaces; no pills or large
cards.

## 4. Components

- **Buttons:** 28px high, 3px radius. Default is transparent with a hairline;
  hover is neutral; primary is the accent fill. Secondary import is a ghost
  button. Only one filled action per screen.
- **Navigation:** header tabs use a 2px accent underline. No pill background.
- **Tabs:** same underline language; inactive tabs are secondary text.
- **Selects and inputs:** 28px, inset graphite, hairline border; hover raises the
  border, focus uses a 1px accent outline.
- **Toggles:** 26×14, neutral track, accent track when on, 10px knob.
- **Ranges:** 2px track with an accent thumb; values use tabular figures.
- **Lists:** flat rows separated by hairlines. Selection uses a 2px inset accent
  bar plus an accent-soft surface, not an outlined card.
- **Properties:** two-column key/value rows, 5px vertical padding, hairline
  separators, mono tabular values.
- **Floating toolbar:** 3px radius, hairline strong border, no shadow; active
  camera mode uses the neutral raised surface with accent text.
- **Focus view:** `Focus` in the camera toolbar hides both side panels and gives
  the model the full width. `\` toggles it; the same control restores the panels.

## 5. Pilot scope

Implemented now:

- shared app bar, page navigation, primary/secondary actions, footer;
- model explorer, entity list, tabs, search and visibility controls;
- display settings with grouped sections, toggles and ranges;
- inspector empty/selected states, DOF grid and properties;
- viewport chrome, camera toolbar, legend and navigation hint;
- focus mode.

Not yet applied (next phase, after review): material-properties document and
tables, hysteresis figure, results sidebar, deformation transport, response
curves, stress-contour workspace. They currently inherit only the shared app bar,
footer and design tokens.

## 6. Review

```sh
cd model-view
npm start
# http://127.0.0.1:8765
```

Pilot evidence lives outside the repository at
`/tmp/opencode/histra-redesign/` (`before/` and `after/` PNGs at 1240×986).

Automated checks: `npm test` → 30 Python tests + 33 Node tests passing, with the
two pre-existing bridge tests skipped because the bridge bundle is not installed.
