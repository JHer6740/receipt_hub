# Orica Field Design System (ODS)

A Material-UI–based design system for **Orica's field applications** — the on-site tools blast engineers, drillers and shot-firers use to plan, drill, dip, charge and fire blast patterns across mine sites. The system spans web (Angular/MUI) and mobile (Flutter) surfaces; this project is the branded, token-driven recreation used to design and prototype ODS interfaces.

> **Product domain.** Orica is an explosives/blasting technology company. The apps here manage the **blast-hole lifecycle** — a hole is *planned → drilled → dipped → (wet) → charged → tied-in → fired*, with QA at each step. Two products are represented: a **Field Web App** (job directory, benches, patterns) and **BIQM** — Blast-hole Integrity & Quality Management, the dark on-bench mobile app.

## Sources
- **Figma:** `ODS Field Apps Library (MUI_Angular_Flutter).fig` (attached, mounted read-only). 151 component sets + ~733 standalone symbols, 293 Figma Variables across 7 collections (palette, typography, spacing, shape, breakpoints, material colors, ungrouped). Token values, type scale and component metrics were extracted from this file — it is the source of truth.
- **Fonts:** Noto Sans (uploaded, `uploads/Noto_Sans/`), the brand typeface. Bundled TTFs in `assets/fonts/`.
- No logo mark ships in the source, so the brand is set as an **ORICA type wordmark** (Noto Sans, spaced). Replace with the official mark when provided.

## Index (manifest of this project)
- **`styles.css`** — global entry (imports only). Consumers link this.
- **`tokens/`** — `fig-tokens.css` (Figma Variables incl. light/dark theme scopes), `fonts.css` (@font-face), `typography.css` (type scale + `.ods-*` classes), `spacing.css` (spacing/radii/elevation), `base.css` (document + link defaults).
- **`components/`** — reusable React primitives, grouped: `inputs/`, `feedback/`, `surfaces/`, `data-display/`, `navigation/`, `layout/`, `ods/` (field-specific).
- **`assets/`** — `fonts/`, `icons/` (bundled ODS glyphs + `Icon` component).
- **`guidelines/`** — foundation specimen cards (Colors, Type, Spacing, Brand).
- **`ui_kits/field-web/`** — Job Directory + Login web app recreation.
- **`ui_kits/biqm/`** — BIQM dark field app (hole list + map view).
- **`SKILL.md`** — Agent-Skill entry point.

## Components
Mount from `window.OricaFieldDesignSystemODS_44c53b` (run `check_design_system` for the current namespace).

- **Inputs:** `Button`, `ButtonGroup`, `IconButton`, `Fab`, `Checkbox`, `Radio`, `Switch`, `Slider`, `TextField`, `Select`, `Autocomplete`, `Rating`, `ToggleButton`, `ToggleButtonGroup`, `TransferList`
- **Forms:** `FormControlLabel`, `FormGroup`, `RadioGroup`, `FormLabel`, `FormHelperText`, `InputLabel`
- **Feedback:** `Alert`, `LinearProgress`, `CircularProgress`, `Skeleton`, `Snackbar`, `Dialog`, `Tooltip`, `Backdrop`
- **Surfaces:** `Paper`, `Card` (`CardHeader`, `CardContent`, `CardActions`, `CardMedia`), `Accordion`, `AppBar`, `Toolbar`
- **Data display:** `Typography`, `Avatar`, `AvatarGroup`, `Badge`, `Chip`, `Divider`, `List`, `ListItem`, `Table` (`TableHead`, `TableBody`, `TableRow`, `TableCell`), `DataGrid`, `TreeView`, `TreeItem`, `Timeline`, `TimelineItem`, `Icon`
- **Date & time:** `DatePicker`, `DateField`, `TimePicker`
- **Charts:** `BarChart`, `LineChart`, `PieChart`, `ScatterChart`
- **Navigation:** `Tabs`, `Tab`, `Breadcrumbs`, `Link`, `Pagination`, `Stepper`, `Step`, `MobileStepper`, `Menu`, `MenuItem`, `BottomNavigation`, `BottomNavigationAction`, `Drawer`, `SpeedDial`
- **Layout:** `Container`, `Stack`
- **Field (ODS-specific):** `HoleStatus`, `Sidenav`, `PageHeading`, `SectionHeading`, `ExpandableNavItem`, `ActionsSlot`, `SubheaderSlot`, `PasswordlessForm`, `PlanItem`, `Uploader`, `UploaderItem`, `ProfileMenu`, `TableToolbar`, `IconButtonGroup`, `Flags`

### Intentional additions
- `Icon` — a wrapper over bundled ODS glyphs (the source uses icon *instances*, not a coded icon component). Needed so designs can render glyphs.
- `HoleStatus`, `Sidenav`, `PageHeading` — the source defines `Hole Status`, `_Custom / Sidenav` and `_Custom / Page Heading`; these are their coded equivalents.
- **Templates** — `templates/field-web-page/` and `templates/biqm-screen/` are consumer-ready starting pages (Design Components) composing the bundle.

### Coverage note
The Figma file enumerates its components as **variant sets** (e.g. `?Button?` = 100 variants; `?Checkbox?` = 124) plus hundreds of standalone symbols and internal sub-parts. Those variants are implemented here as **props** on one component, not as separate files — ~95 built exports cover the whole standard MUI surface, charts (Bar/Line/Pie/Scatter), date & time, and the ODS custom families (`Sidenav`, `Page Heading`, `Section Headings`, `Expandable Nav Item`, `Actions Slot`, `Subheader Slot`, `Forms / Passwordless`, `Settings / Plan Item`, `Uploader`, `Profile Menu`, `Table / Toolbar`, `Icon button group`, `Hole Status`). **Intentionally not built as separate components**, and why:
- **Internal sub-parts** — `_SliderThumb`·`Track`·`Rail`·`Mark`·`Label`, `_SwitchThumb`·`Track`, `_Elements / Day Cell`, `Star`, chart `Elements / Bars`·`Lines`·`Axis`·`Legend`·`Tooltip`·`Series Bar`: render-internals of `Slider`, `Switch`, `DatePicker`, `Rating` and the chart components — not public API.
- **DataGrid/Table sub-cells** — `?DataGrid? | Cell`·`Header`·`Header Rows`·`Column Group`, `?TableCellRow?` (288/144 variants), `_?GridToolbarQuickFilter? / *` menus: folded into `DataGrid`, `Table` and `TableToolbar`.
- **Composite picker shells** — `?MobileDateTimePicker?`, `?StaticDateTimePicker?`, `_Pickers / Date Time`·`Range Date`, `Native / Date Time Picker`: compositions of the built `DatePicker`/`TimePicker`/`DateField`.
- **Library scaffolding** — `_Library / *` (Component Heading/Information/Properties, Instance Slot, Color Code, Placeholder Image, MUI Logos), `_Native Browser Scroll`, `_hidden`, `Spacing | Horizontal`·`Vertical`, `Lo-fi-Wireframe/*`: Figma documentation tooling, not product UI.
- **`_Custom / Flags`** — built as `Flags` (`assets/flags/`): all 9 country-flag variants extracted verbatim from the source vectors.
- **One-off composed screens** — `_Custom / Settings / Basic`·`Billing plan`·`Change password`·`Logged Devices`·`Notifications`·`Payment`, `_Custom / Users Management Table`, `_Custom / Blog Post`, `_Custom / Text Editor`, `_Custom / My Detail Panel Content`, `BIQM / *` shells: full screens, represented by the UI kits and templates rather than single components.
- **Icon glyphs (~324)** — bundled selectively in `assets/icons/`; see ICONOGRAPHY.

## CONTENT FUNDAMENTALS
- **Voice:** plain, operational, task-first. Labels are nouns/short verb phrases ("New job", "Sign in", "Open job", "Save hole"). No marketing tone.
- **Casing:** Sentence case for headings and body ("Latest jobs", "Charging progress"). Button labels are Title/Sentence case, not ALL-CAPS (MUI default uppercase is **disabled** in ODS — `text-transform: none`). Overlines/eyebrows are the one uppercase role.
- **Person:** neutral/imperative — the UI addresses the operator directly ("Search jobs, benches, sites…"). No first person.
- **Domain vocabulary:** bench, pattern, hole, dip, charge, tie-in, fire, emulsion, deck, diameter, water, loading. Measurements carry units (m, mm, ºC) and show `--` when unmeasured.
- **Emoji:** none. Status is communicated with color + text, never emoji.
- **Numbers:** compact and paired ("28/42 holes", "5 | 0" loading, "11.6 m").

## VISUAL FOUNDATIONS
- **Color:** brand primary is **Orica Blue** (`--primary-main` = #0076A6, oricablue-800). **Orica Navy** (#004C99) carries info/indeterminate. Semantic set: success = light green (#9DCC66/#8BC34A), warning = orange (#FF8A1D), error = red (#D12100/#DE350B). Neutrals are **cool greys** (900 = #191C20, the dark-app canvas). Surfaces are near-white (`--odsgrey-50` #F4F4F4) in light, cool-grey 900/800 in dark. Full light + dark theme scopes ship in `fig-tokens.css` (`:root[data-theme="dark"]`).
- **Type:** Noto Sans throughout. Scale is Display (96/60/48, Light 300) → Headline (34/24/20) → Title (16/14/12, 500) → Body (16/14/12) → Label (14, 500). Button label is 15px/500 with 0.46px tracking. See `tokens/typography.css`.
- **Spacing:** 8px base unit (MUI). Radii are tight — **4px** (sm) and **8px** (md/lg); pills for chips/badges/switches; circles for avatars/FABs/icon buttons.
- **Elevation:** the standard MUI black-alpha shadow ramp (`--shadow-1…24`, triple-layer `rgba(0,0,0,0.2/0.14/0.12)`). Cards sit at elevation 1; menus/dialogs at 8/24. Outlined variants swap shadow for a `--divider` hairline.
- **Backgrounds:** flat fills — **no gradients, no photographic hero imagery, no textures**. The dark BIQM app uses a subtle grid pattern only for the map plan view. Light app = flat #F4F4F4.
- **Cards:** flat surface, 8px radius, elevation-1 shadow (or 1px outline), no colored left-border accents.
- **Borders:** hairline `--divider` = `rgba(0,0,0,0.12)` light / `rgba(255,255,255,0.12)` dark. Inputs use `rgba(0,0,0,0.23)` outlined borders, thickening to 2px + accent on focus.
- **Motion:** functional and quick — 0.15–0.2s ease on background/border/elevation; determinate progress transitions width; indeterminate spinners rotate. No bounces, no decorative loops.
- **States:** hover = tint overlay (`--*-states-hover`, ~4–8% alpha) or shift to `-dark`; selected = `--*-states-selected`; disabled = `--action-disabled` text on `--action-disabledbackground`. Press is a darker fill (no scale).
- **Transparency/blur:** alpha overlays for hover/selected/focus rings and the modal backdrop (`rgba(0,0,0,0.5)`); no backdrop-blur.
- **Layout:** MUI breakpoints (xs 444 / sm 600 / md 900 / lg 1200 / xl 1536). Content centers in a `Container` (max 1200) with 24px gutters; app shells use a fixed `Sidenav` (256px) + `AppBar` (64px).

## ICONOGRAPHY
- The ODS apps are **Material UI** apps — iconography is the **Material Icons / Material Symbols** family. In the Figma file icons appear as component *instances* (e.g. `AddFilled`, `CancelFilled`, `EventFilled`, `MailOutlineFilled`, chevrons, stars) rather than a coded icon set.
- **Bundled glyphs:** real SVG path data for the icons the file actually uses was extracted into `assets/icons/icon-data.js` and is rendered by the `Icon` component: `AddFilled`, `CancelFilled`, `EventFilled`, `MailOutlineFilled`, `ChevronLeftFilled`, `ChevronRightFilled`, `ArrowDropDownFilled`, `FormatAlignLeftFilled`, `Info`, `StarSharp`, `StarOutlineFilled`, `StarHalfFilled`, plus the custom `ODSChevronLeft2`/`ODSChevronRight3`.
- **Supplemented utility glyphs (flagged):** common UI glyphs the file references but doesn't name individually (search, menu, more-vert, settings, notifications, arrow-back, person, check, delete, logout, location, layers, add) are provided as **standard Material Icons geometry** so the UI kits are complete. These are geometric utility icons, not brand marks. For production, pull the full set from **Material Symbols** (Google Fonts) — `<span class="material-symbols-outlined">`.
- **Emoji / unicode:** never used as icons. Usage: 24px default, 18–22px inline, 36px prominent; all currentColor-driven so they inherit text color.

## Usage
```jsx
const { Button, HoleStatus, Card, CardHeader } = window.OricaFieldDesignSystemODS_44c53b;
<Button color="primary" variant="contained">New job</Button>
<HoleStatus status="charged" />
```
Cards, UI kits and slides load the compiled bundle via `<script src=".../_ds_bundle.js">` and link `styles.css`.

## CAVEATS
- **Coverage.** ~95 component exports cover the full standard MUI surface, charts, date & time, and all the reusable ODS custom families. Everything intentionally not built as a separate component is itemized with reasons under *Coverage note* above — chiefly render-internals, doc scaffolding, composed one-off screens, and the flag bitmaps (which need real assets).
- **Icons.** Only the glyphs the file directly uses were extracted; the broader Material set is documented as a CDN fallback rather than bundled (324 scattered instances were not individually enumerable). Say the word if you want a specific set materialized.
- **Fonts.** `Noto Sans ` (trailing space), `Redacted Script` (wireframe font) and a `semibold italic` weight are referenced by tokens but have no font file — the compiler flags these for upload. Noto Sans itself is fully bundled.
- **Metrics.** Component paddings/radii follow the exact Button spec read from the file (56px xl button, 8px radius, 0.46px tracking) and MUI standard metrics elsewhere; a few were not read node-by-node.

