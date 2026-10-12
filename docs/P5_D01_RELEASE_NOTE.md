# AI Image Forensics v0.18.0 — P5-D01 release note

## Source development

Built on the *actual* v0.17.0 source package, carrying forward P1, P2, P3 and P4 source, tests and outputs. Added:

- `src/aiforensics/depth_contact.py` — metric ray-plane reconstruction, finite convex support polygons, independently known 3D anchor contact and reprojection, upright-height projection, simplified statics/COM projection, optional Brown-Conrady lens distortion, conditional pixel-depth uncertainty propagation, fail-closed status handling.
- `src/aiforensics/depth_contact_synthetic.py` — controlled 3D camera/ground/height fixture and analysis overlay.
- `tests/test_p5_d01_depth_contact.py` — positive/negative/degen and provenance tests, including inclined support, noise ambiguity and lens round-trip.
- `scripts/p5_depth_contact_benchmark.py` — controlled multi-seed conditional verification; no field-data inference.
- `docs/P5_D01_DEPTH_CONTACT_SUPPORT.md` — equations, JSON input schema, independence contract and limitations.
- CLI commands `demo-depth-contact` and `analyze-depth-contact` with optional dimension-checked source image and image hash.

## Test results in current Linux environment

- Prior v0.17.0: **431/431 PASS** before modifying the code.
- v0.18.0 full test suite: **462/462 PASS** (31 new tests).
- 80 synthetic trials, 9 measurements each: **720 observations**. Expected classes: 320 physically consistent, 240 deliberately altered inconsistent, 160 no independent measurement/indeterminate.
- 315 physically consistent accepted; 5 additional `INDETERMINATE` under higher pixel noise, **0 physically consistent samples falsely marked inconsistent**. All 240 altered measurements identified as `INCONSISTENT_UNDER_ASSUMPTIONS`; all 160 insufficient-evidence samples abstained.
- 715/720 exact labels; **5 safe additional abstentions**, **0 false definitive physical verdicts** within the controlled generator conditions.
- UPRIGHT top-point synthetic median pixel reprojection error over positive samples: ~0.730 px.

These statistics use the same synthetic forward model family and do not establish real-world detection accuracy, AI-generated-image attribution accuracy, or independent depth recovery.

## Acceptance limitations

- Actual Windows machine install/test not executed in this environment.
- Independently measured real camera pose, scene support surfaces, object heights and depth-ground-truth acceptance deferred until all physical modules are built.
- No user GitHub repository modified or pushed.
- Rigidity, static equilibrium, unobstructed sightline, camera/plane measurements, support geometry and provenance remain input assumptions.
