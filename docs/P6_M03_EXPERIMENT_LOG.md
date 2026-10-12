# P6-M03 — Controlled synthetic experiment log (v0.23.0)

## Experimental contract

This is **not** a measured image-forensics accuracy study. Every scene is created using the same simplified Lambert + Smith-GGX single-scattering mixture that the estimator is designed to evaluate. Known material parameters, known light irradiance/directions, synthetic RGB radiance and geometry-provenance flags are provided by the generator. No real-camera sensor/tone-mapping or camera-material interactions are tested.

Code: `scripts/p6_combined_benchmark.py`, `src/aiforensics/combined_material_synthetic.py`.

## Deterministic scenarios

- 80 seeds beginning with `285000`.
- 40 known-material and 40 training-only fitted diffuse-albedo scenarios.
- Each case has 30 training observations and 24 independent holdout observations from two declared surface groups (`panel_A`, `panel_B`), distinct from training `reference_coupon`.
- 3 / 24 holdout measurements in every case are deliberately perturbed by about +0.35 absolute linear-radiance units in each RGB channel.
- 60 scenarios assumed negligible unmodeled multiple scattering and 20 used an independently declared phenomenological diffuse-lobe proxy; **neither simulates true microfacet multi-bounce transport**.
- RGB noise standard deviation: `0.007` per channel.
- Classification thresholds: `z<=2.5`: consistent; `z>=4.5`: conditional inconsistency; otherwise uncertain.

## Observed results

| Measurement | Value |
|---|---:|
| Trials | 80 |
| Holdout measurements | 1,920 |
| Deliberately corrupted | 240 |
| Detected corrupted | 240 |
| Clean | 1,680 |
| Clean, falsely flagged as certain violation | 0 |
| Clean, uncertain | 58 |
| Clean, consistent | 1,622 |
| Median fitted diffuse RGB albedo L2 error (40 fitted cases) | 0.0016368 |
| 90th percentile fitted RGB albedo L2 error | 0.0029893 |

Independent synthetic negative controls `unknown_light`, `unknown_multiscattering` and `unverified_proxy` each returned `INDETERMINATE`. A second held-out surface with shifted radiance is flagged, and modification of holdout observations does not change train-fitted diffuse albedo.

Reports: `outputs/p6_m03_benchmark.json`, `outputs/p6_m03_demo/p6_m03_report.json`, `outputs/p6_m03_energy_audit.json`, `outputs/p6_m03_demo/p6_m03_holdout.png`.

## Physical inference limitations

The experiment does not validate a true multi-bounce GGX BRDF, inference of illumination from an uncontrolled image, global energy conservation of every physical material, or AI-content detection. The combined BRDF is an *energy-bounded convex mixture*: this is a safe simplified phenomenological material, not evidence that it accurately reproduces real metals, glass, fabric or paint.

The P6-M03 report explicitly outputs `NO_AI_ORIGIN_CONCLUSION`. Final independent measured material, radiance/camera calibration, uncertainty-calibration, real-image false-positive experiments and Windows acceptance are deliberately deferred to the final project stage.
