# v0.15.0 — P4-O02 mathematical/synthetic release

## Code additions

- `src/aiforensics/defocus.py`: distance validation, thin-lens equation, geometric CoC sensor/native pixel conversions, near/far depth of field, hyperfocal, normalized circular PSF, conditional calibrated-CoC report, holdout-only verification and Monte Carlo depth/focus uncertainty.
- `src/aiforensics/defocus_synthetic.py`: deterministic known-ground-truth depths and isolated defocus illustration; not a physically complete image renderer.
- `tests/test_p4_o02_defocus.py`: 48 tests including regressions, infinity limits, data leakage, invalid values, calibrated measurement guard, normalized PSF, CLI.
- `scripts/p4_defocus_benchmark.py`: controlled 80-scenario reproducible stress benchmark with 40 focus-fitting and 40 externally known-focus scenarios.
- `docs/P4_O02_THIN_LENS_DEPTH_OF_FIELD.md`: mathematics, accepted input schema, uncertainty and explicit limitations.

## Scope

- Previous P1/G01–G04, P2/S01–S05, P3/R01–R03, P4/O01 are included unchanged except shared CLI version and new command wiring.
- `CONSISTENT`, `INCONSISTENT_UNDER_ASSUMPTIONS`, `INDETERMINATE` are conditional optical statements, never AI provenance decisions.
- Never treat generic blurred JPEG edges as independently calibrated circle-of-confusion measurements.
- These are synthetic model regressions. Independent real-camera field validation and real Windows acceptance were intentionally deferred.
