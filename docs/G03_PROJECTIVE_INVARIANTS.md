# G03: 1D projective invariants for floor tiles and architectural repeats

For four world points on **one** 3D line with affine scalar coordinates `s_i`, their cross-ratio is projectively invariant:

\[
CR(s_0,s_1,s_2,s_3) = \frac{(s_2-s_0)(s_3-s_1)}{(s_3-s_0)(s_2-s_1)}
\]

With `s=[0,1,2,3]`, `CR=4/3`. For a perspective-projected line, the measured pixel coordinates `t_i` along the fitted image line satisfy the same cross-ratio (within pixel localization noise, distortion, and model error). Equal intervals in the **image** are **not** expected, and this is not a test of arbitrary rows/tiles whose true spacing is unknown.

## Algorithm

1. Input 4+ corresponding pixel locations and their known world lattice indices (default `0,1,...` only if independently justified).
2. Fit a one-dimensional image line with total least squares via SVD; check perpendicular deviations and world-order monotonicity.
3. Compute `CR(image first four)` and `CR(world first four)`, report signed/absolute deviation.
4. Propagate user-specified `pixel_sigma` through 2D Gaussian landmark perturbations to obtain **exploratory** 95% Monte Carlo interval. This interval is conditional on the correctness of error assumptions; it is **not** a calibrated AI-detection probability.
5. If supplied `training_indices` include at least three points and disjoint holdout remains, solve fractional-linear map `t(s)=(a*s+b)/(c*s+d)` by normalized DLT on **training points only**; project held-out landmarks to the estimated image line; report pixel residual RMSE and per-point errors. The image line is fitted using training points only.
6. Return `MEASURED`, `INDETERMINATE` or `INCONSISTENT_UNDER_ASSUMPTIONS`; never a binary AI verdict.

## Limitations and controls

- A 1D projectivity can fit **three** 1D correspondences exactly; three fitting points do not provide any independent validation. Hold out at least one, preferably several.
- Same physical line, physically known repeat interval, point ordering, correct correspondences and negligible/rectified lens distortion are prerequisites.
- A physically inconsistent input can be a human labeling error, uneven craftsmanship, non-planar material or lens-distortion effect. Detection is **conditional on assumptions**, not proof of synthetic origin.
- Five or more marks allow 3-point training and independent holdout; with only four you may report cross-ratio but should avoid overconfident statistical conclusions.
- Multiple possible lines/quadruples need multiple-testing control and nonoverlapping test datasets; not yet implemented.
- Automatic tile joint/pattern detection is NOT present; user supplies landmark coordinates or a separate vision front-end.

## Demonstration

`python scripts/g03_demo.py` renders a controlled corridor with floor landmarks at 5, 7, 9, 11, 13, 15 meters; the physical steps are 2m and their image projections share a 1D projectivity. The output includes `g03_marked_corridor.png`, `g03_input.json`, and `g03_report.json`.
