# AI Image Forensics — v0.6.0 / P2-S01 development evidence

Date: 2026-10-10

## Included

- Prior P0/P1 G01/G02/G03/G04 source and existing regression tests.
- `src/aiforensics/shadow_geometry.py`: annotated object/shadow projected convergence estimator (finite and image-infinity modes), inlier/outlier evidence, rank degeneracy rejection, deterministic bootstrap exploratory dispersion, JSON & overlay.
- `src/aiforensics/shadow_synthetic.py`: 3D object/point-light/directional-light/shadow/pinhole known-truth fixture.
- `scripts/p2_shadow_benchmark.py`: controlled regression with Gaussian endpoint noise and deliberately false correspondences.
- `tests/test_shadow_geometry.py`: shadow physics and integration tests.
- `docs/P2_S01_SHADOW_GEOMETRY.md`: equations, I/O contract, key assumptions, limitations.

## Measured during implementation (synthetic only)

- `pytest -q`: 76 passed.
- End-to-end `python -m aiforensics demo-shadows`: 12/12 corresponding rays fit; projected convergence error `3.2155493553843715e-13` px for ideal synthetic pinhole geometry.
- `python scripts/p2_shadow_benchmark.py --trials 60`: 60/60 measured fits, median projected-source pixel error `1.8417824680385837`, p90 `5.5512611847508095`; each trial included 20 pairs, 3 deliberately corrupted pairs, and Gaussian coordinate noise sigma `0.35` px.
- `python -m aiforensics analyze-shadows --input outputs/p2_s01_demo/p2_s01_synthetic_manifest.json --image outputs/p2_s01_demo/p2_s01_synthetic_scene.png --out outputs/p2_s01_cli`: `MEASURED`.

## NOT done (intentional order)

- Automatic shadow mask segmentation; automated point-to-cast-shadow association.
- 3D physical light-source location / distance determination.
- Multi-illuminant segmentation or penumbra fitting.
- Real-image ground truth / error rates / false positive rates / AI-generated-image classification.
- Real Windows acceptance and GitHub push.

Product development, synthetic math regression and adversarial/degenerate test cases take priority. Independently measured real-world validation is a final acceptance milestone, not a prerequisite to developing subsequent P2–P8 modules.
