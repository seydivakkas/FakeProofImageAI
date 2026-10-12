# P1 v0.5 independent-source photographic experiment audit

## Reproducibility

- Environment: Linux container, Python 3.13, NumPy 2.3.5, OpenCV 4.13.0, SciPy 1.17.0, scikit-image 0.26.0 (runtime measurements).
- Regression: `PYTHONPATH=src pytest -q`, **58 passed**.
- Run `PYTHONPATH=src python scripts/real_photo_experiments.py outputs/real_photo_experiments` to independently recreate derived photographs and reports. Actual camera photos are provided by a *local installation* of scikit-image, not distributed in the ZIP.
- Neither Windows installation nor original York Urban `.mat` camera reference datasets were exercised here.

## Real source photographic content (G03b)

| Photo source | Rectangle candidates | Appearance-matched groups | Status |
| --- | ---: | ---: | --- |
| `skimage.data.brick` | 53 | 1 | CANDIDATE_ONLY, no semantic or world-spacing GT |
| `skimage.data.rocket` | 1 | 0 | CANDIDATE_ONLY, no semantic or world-spacing GT |

Labels in these trials are *not independently verified floor or facade ground truth*. Candidate detection is not detection precision/recall.

## G04: controlled warp of real photographed pixels

- Source: `skimage.data.rocket`; second image is digitally projectively transformed. This is **not** a second camera capture.
- Ratio test: 180 matches; 106 training matches; 46 held-out matches.
- Raw holdout RMSE: 47.12696 px (dominated by 3 mismatches).
- Holdout median error: 0.12205 px; 90th percentile error: 0.40482 px.
- 43/46 test correspondences have errors at most 3 px (93.478%); corresponding inlier RMSE 0.25849 px.
- Known programmed homography versus matched test points: median 0.10465 px. This is a *transform control* not an external physical scene ground truth.

## G04: two separately captured stereo images

- Source: `skimage.data.stereo_motorcycle` photographs. This is intentionally outside architectural domain and contains multiple scene depths.
- 935 ratio-test matches; 252 held-out correspondences.
- Holdout median error 3.41960 px; 123/252 within 3 px; 129 correspondences outside 3 px.
- The scene is **not one planar surface**. Its global homography mismatch is not grounds for declaring image manipulation or AI generation.

## Unmeasured / hold

- G02 independent physical camera K calibration: **0 original camera cases evaluated**, as independent photographic `.mat` / labels are unavailable.
- G03b floor/facade segmentation accuracy and repeated architectural element precision/recall: **not measured**.
- G04 independently photographed planar architecture with independently annotated H and heldout points: **not measured**.
- P2 shadow/lighting physics: **not started**.

**Conclusion:** 58/58 functional regression tests pass; empirical true-ground-truth field acceptance remains HOLD for G02, G03 semantic segmentation and G04 two-camera planar photogrammetry.
