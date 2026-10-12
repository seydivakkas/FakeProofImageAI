# P2-S02 — Multiple Projected Shadow-Ray Families

## Scope

Extract up to `max_models` geometrically distinct image-plane convergence families from **independently annotated** object-point / cast-shadow-point correspondences. Models do **not** prove source count, source type, height, physical inconsistency or AI authorship. It is possible for light sources at different 3D positions to produce almost indistinguishable image-plane intersections.

## Mathematical model

For observed image points `p_i=(x,y,1)` and `q_i=(u,v,1)` let `l_i=p_i × q_i`. For source-family `k`, candidate homogeneous point `s_k` should satisfy `l_i^T s_k≈0`, under rectilinear central perspective geometry. A projected directional-light family may have a finite VP or a point at infinity.

The S01 angular residual is used (in degrees). With ray midpoint `m_i` and unit ray direction `d_i`, finite `s_k` gives:

`r_ik = asin(|det(normalize(s_k-m_i), d_i)|)`.

For a VP at infinity, substitute its unit homogeneous projected direction. **Ray orientation is intentionally unsigned** in the image-plane test; a 2D convergence alone cannot establish causality or the direction of illumination.

P2-S02 uses:

1. Image normalization to improve numeric conditioning; same validated JSON `image_shape_hw`, `correspondences`, `confidence` contract as S01.
2. Randomized pair-line intersection proposals (plus weighted global nullspace estimate).
3. Conservative per-model minimum count and weight support; reject degenerate rank-one line families.
4. Greedy removal of supported pairs to propose distinct candidate families, with median angular separation guard.
5. Exclusive iterative reassignment to nearest surviving family; ambiguous near-ties are left unassigned.
6. Weighted homogeneous SVD re-estimation and independent per-family angular residual reports.
7. Global weight coverage floor; state `INDETERMINATE` if too few observations explained.
8. Optional bootstrap coordinate dispersion from within-family resamples. **Not** a calibrated confidence interval.

Greedy RANSAC is not a guarantee of globally optimal model selection; alternate initialization, weakly separated sources, coincident ray lines, and wrong pairings may change the result. It can underfit when sources are close and overfit patterned outliers. The cutoffs are exploratory and **not calibrated false-positive rates**.

## Inputs

See `outputs/p2_s02_demo/p2_s02_fixture.json` for a **generated known-truth fixture** (ids, object and shadow pixel coordinates). Never infer that two arbitrary dark spots are a genuine point and its cast shadow. Independently establish the physical correspondences, surface geometry and any camera rectification outside S02.

## CLI

```powershell
python -m aiforensics demo-multilight --out outputs/p2_s02_demo
python -m aiforensics analyze-multilight --input pairs.json --image frame.png --out outputs/custom_multilight --angle-threshold 2.0 --max-models 3
python scripts/p2_multilight_benchmark.py --trials 60 --out outputs/p2_s02_benchmark.json
pytest -q tests/test_shadow_multilight.py
```

Report: `p2_s02_report.json`. Overlay with `--image`: `p2_s02_overlay.png`.

- `model_id` is a **projected-ray family** label, not independently verified physical source.
- `member_ids` are exclusive; `ambiguous_ids` identify borderline near-ties; `unassigned_ids` identify uncovered correspondence candidates.
- `overall_weight_support_fraction` describes sample-fitting support, **not** AI probability or image authenticity.
- `state=MEASURED` means geometrically supported family/families with sufficient in-sample support only.
- `state=INDETERMINATE` means no adequately constrained result under declared thresholds.
- `decision=NO_AI_ORIGIN_CONCLUSION` is always enforced.

## Tests

Known-truth 3D scene generation, 1/2/3 projected point-light sources, distant directional illumination, noise, spurious pairings, source proximity, degeneracy, malformed annotations, weight support, reproducible RANSAC, image-size mismatch and CLI round-trip. Controlled randomized stress benchmark includes 60 repeated 2-source cases with different noise, wrong pairs and 3D object placements, but the camera geometry and base light positions are fixed. Generalization to independently captured scenes is **not** established.

## Deferred final validation (not a development blocker)

- Independently annotated real object/shadow point pairs, measured/calibrated cameras and light direction/source placement.
- Contact/shadow association and multi-light source-labelling ground truth.
- Source-count precision/recall, assignment F1, false-positive rate, calibrated thresholds, inter-rater label uncertainty, camera-distortion failure modes.
- Windows user acceptance. All this remains **FINAL-VALIDATION BACKLOG** by product policy.

## Next engineering phase

P2-S03: ground-plane constraints, reference geometry, and 3D light inversion **only when the camera and 3D geometry supply enough independent constraints**. General single-image 3D light depth remains unidentifiable without additional assumptions.
