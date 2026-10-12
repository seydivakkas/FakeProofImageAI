# P1-G03a and P1-G04: algorithm contract

## G03a — automatic repetition candidates

Pipeline: color image -> LSD and Hough line segments -> select sufficiently long visible support segments -> intersect transverse line segments -> cluster nearby pixel intersections -> order 2D marks on each support -> propose candidate lattice with **unverified** unit world spacing -> optional exploratory G03 holdout fit -> draw marks.

No learned semantic segmentation is present. The algorithm detects repeated transverse intersections, **not verified parquet/floor tile/window/column objects**. It cannot decide whether detected marks are physically equally spaced. False repeats, missing lines, perspective changes and reflections are expected failure conditions. Outputs are `CANDIDATE_ONLY_UNVERIFIED_WORLD_SPACING` and never assert AI generation.

The automatic unit-lattice fit is descriptive and potentially circular: marks were *selected* because they look repetitive. No hypothesis-test p-value or AI-origin evidence can be inferred. A physical contradiction needs independently measured or documented 3D spacing and correspondences.

**Controlled fixture**: `python scripts/g03_auto_demo.py` generates a designed geometric grid, runs actual OpenCV line detection and records an annotated PNG plus JSON. No genuine photo is used in this experiment.

## G04 — planar world-to-image homography with holdout

Planar perspective model (assume known 2D world-plane coordinates):

\[\lambda \mathbf{x} = H\mathbf{X}, \quad H\in \mathbb{R}^{3\times3}\]

At least four non-collinear training point pairs fit a plane homography, with additional independent point pairs for testing. For five or more training points, OpenCV RANSAC is used to reject candidate correspondence outliers; the holdout is NEVER part of the fit. The reported holdout error is

\[E_{\mathrm{test}}=\sqrt{\frac1N\sum_i\|\pi(H \tilde X_i)-x_i\|_2^2}.\]

Train/holdout leakage is prevented by disjoint indices. Degenerate 1D configurations are reported as `INDETERMINATE`. The user-specified holdout threshold is an **engineering threshold, not a calibrated statistical significance test**. A mismatch may indicate bad annotations, curved geometry, lens distortion, a bad plane assumption, image editing, or model failure; it **does not establish AI generation**.

The output also reports inverse-world error but it depends on the chosen world-plane units, so it must not be compared as pixels.

**Controlled fixture**: `python scripts/g04_demo.py`. JSON schema: `world_points_xy`, `image_points_xy`, `training_indices`, optional `ransac_threshold_px` and `holdout_threshold_px`.

## Real image prerequisites

Independent physical evidence requires 2D landmarks, externally known 3D planarity and repeated-spacing premises, independently calibrated camera or matched metric world plane, and a holdout not used in model construction. At least 20 independently held-out photographic frames with fixed pre-registered acceptance thresholds are the next experimental acceptance milestone, not an accomplished result.
