# P1–G02 v0.2 delivery checklist

- [x] Original P0/G01 unpacked and preserved; 10 original unit tests continue to pass.
- [x] Independent Python G02 camera calibration (`K`, `R`, `omega`).
- [x] Finite VP checks; numeric degeneracy / negative f-squared guards.
- [x] G01 estimated VP families wired to G02 with external orthogonality labeling.
- [x] CLI paths for direct VP calibration, G01→G02 and synthetic benchmark.
- [x] `pytest`: 22/22 pass (10 prior + 12 new tests).
- [x] Deterministic 50-trial, labeled 3-family G01→G02 synthetic benchmark.
- [x] G01 demo and synthetic corridor regression re-run.
- [x] AI provenance inference intentionally absent.
- [ ] Independent camera/intrinsics ground truth on real photographs.
- [ ] Cross-platform Windows execution independently verified.
- [ ] External lens distortion/fisheye support.
- [ ] Infinite vanishing-point support.
- [ ] True statistical confidence intervals / calibrated decision rules.

No GitHub push has been performed in this delivery.


## v0.23.0 — P6-M03 material-model integration

- [x] P6-M01 + M02 retained; P6-M03 combined Lambert + GGX code with convex lobe weights.
- [x] Separate unknown multiple-scattering abstention versus independently characterized phenomenological proxy.
- [x] Independent material/light/geometry/radiometry provenance, train-vs-holdout split, two-surface tests.
- [x] Sampled GGX directional-hemispherical energy audit with P6-M02 numerical abstention for sharp lobes.
- [x] Controlled benchmark and negative control output in JSON, no AI-origin verdict.
- [ ] Actual microfacet multiple-scattering solver (out of current P6-M03 simplified model).
- [ ] Real photographs/RAW measurements, independent color/radiance reference and actual Windows acceptance (final project phase).

## v0.24.0 — P7-S01 checklist

- [x] P7-S01 RAW Poisson–Gaussian physical model, separate ADU conversion, full-well and ADC clipping simulation
- [x] Train/holdout gain/read/dark calibration with independent photon means
- [x] Conditional mean/variance residuals, SNR, safe uncertainty classification
- [x] Negative tests: JPEG/gamma, missing independent photon flux, PRNU/FPN, saturation, temperature, wrong gain
- [x] `.npy` temporal per-pixel ROI extractor without spatial FPN leakage
- [x] 80 seeded synthetic trials, 240 deliberate holdout corruptions, report
- [x] All existing P1–P6 regression tests retained
- [ ] Real camera/calibrated RAW measurement/PRNU acceptance — **last phase**
- [ ] Windows native execution acceptance and GitHub publishing — **not performed**
