# P6-M02 controlled engineering test log (v0.22.0)

This file documents **executed local synthetic tests**, not photographic research or commercial acceptance.

- Parent source: `AI_Image_Forensics_P1_P2_P3_P4_P5_P6_M01_v0.21.0.zip`; unpacked/current previous project folder preserved.
- Parent regression: `574 passed`.
- Current regression: `616 passed` (574 existing + 42 P6-M02), by `PYTHONPATH=src:. python -m pytest -q`.
- P6-M02 synthetic stress: 80 trials, with 40 supplied roughness cases and 40 train-only fitted roughness cases; 24 disjoint holdout measurements each, including three deliberately corrupted.
- Measured counts: 80 model parameter solutions; 240/240 deliberately corrupted holdouts detected; 0 erroneous **definitive** inconsistency decisions among 1680 synthetic clean holdouts; 65 uncertain clean holdouts.
- In the 40 fitted-roughness cases: median absolute roughness error `3.8995011167e-05` and 90th percentile `0.0001305327`, **only on same-family model-generated samples**.
- Main CLI commands: `demo-microfacet`, `analyze-microfacet`, `audit-microfacet-energy` executed; output under `outputs/p6_m02_*`.
- Numerical energy check returns `INDETERMINATE` for sharp GGX lobes below roughness 0.18, because comparison of two regular integration grids does not prove energy conservation for delta-like peaks.
- Limitations: no measured BRDF of real specimens, no physically independent light direction/irradiance, no real camera PSF or color pipeline, no machine-verified Windows execution, no GitHub push, and no inference about AI authorship.

**Note:** These synthetic statistics must never be presented as measured real-world precision, classification sensitivity or false positive rate.
