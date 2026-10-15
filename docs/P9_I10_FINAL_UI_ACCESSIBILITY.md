# P9-I10 — Final UI readability, keyboard and graphic navigation

## Scope / release boundary

Release: v0.38.0. This is the final planned **synthetic UI refinement**, not real-image/camera or native Windows end-user acceptance. P1–P8 physics and E01–E03 math are unchanged.

## Implemented

| Surface | Behavior | Data safety |
|---|---|---|
| E03 findings | Free-text search, status filter, 40-record pages, prior/next via keyboard and buttons | Original E03 source unmodified; no synthetic claims |
| Evidence details | Readable hypothesis / measured / predicted / residual / uncertainty / provenance and E02 dependency presentation, switchable to bounded raw JSON | No recomputed p-values, no fake intervals |
| Evidence panel | User-adjustable split view, vertical details scrollbar | Original long explanations remain in immutable E03 JSON |
| Dependency graph | Zoom 0.45–3.0, arrow-key pan, Home reset, mouse pan and node selection → finding search | Only E03 reported lineage/edges, bounded displayed nodes |
| G04 holdout chart | Previous/next 300 actual holdout errors; sample counter, keyboard arrows | Source errors & threshold unchanged |
| E03 residual chart | Previous/next 24 actual values **per unit**, keyboard arrows, interval only if in source | No cross-unit aggregation, no statistics calculated |
| Report index | Horizontal and vertical scroll, adaptive columns | Indexed local source reports, SHA-256 checks retained |

## Keyboard guide

On E03 review: Ctrl+F focuses record search; F3/Shift+F3 move selection. Mouse or Tab to evidence list, arrows to navigate native Listbox. Graph: click graph canvas to focus, +/- zoom, arrow keys pan, Home reset, mouse wheel zoom, drag pan; click node to search/select its report record. Charts: click canvas to focus, Left/Right change the 300/24-item source-record window. On main app Ctrl+1..9 pages; Ctrl+N new project; Ctrl+O load image; F5 refresh; PgUp/PgDn scroll.

## Regression and UI evidence

- \`tests/test_p9_i10_usability.py\` covers 1,000-record pagination, filtering, long explanations, graph viewport guards and keyboard bindings.
- The v0.38.0 regular pytest matrix must pass Windows/Ubuntu Python 3.11 and 3.12.
- \`scripts/p9_i09_synthetic_screens.py\` now also captures three *actual* Tk evidence/graph/report pages after running controlled synthetic G02/G04/E03 CLI fixtures at 1366×768 and 1920×1080.
- Screen captures are rendered in Ubuntu/Xvfb and are neither Windows 10/11 real-device UX acceptance nor pixel-perfect proof versus generated mockups. A human visual audit is still required.

## Mockup differences / honest acceptance

Compared with the earlier image design series:
- **Improved**: resizable evidence inspector, readable evidence detail, search/paging, measurement chart browsing, graph navigation, consistent dark styling and explicit empty states.
- **Still not pixel-identical**: advanced visual component spacing, full-source mapped VP and physical uncertainty overlays within the same image, graphical inspector layout variations, complex dependency graph filters, PDF and cryptographic signatures.
- **Prohibited inference**: uploaded photograph alone does not qualify all modules; source link via user assertion is unverified; conditional hypothesis rejection does not establish AI generation.

## Next engineering gate

Open *P10-A01 Independent Validation Protocol*, deliberately separate from P9 feature development. Do not mark calibration, camera identity, Windows installer, false-positive rate or UI compliance PASS until independently executed on original images, camera metadata/RAW, authorized calibration targets, holdouts and Windows 10/11 machines. See docs/P10_INDEPENDENT_VALIDATION_GATE.md.
