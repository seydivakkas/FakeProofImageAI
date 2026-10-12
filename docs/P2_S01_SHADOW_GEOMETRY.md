# P2-S01 — Projected Light Convergence from Cast Shadows

## Objective and boundary

The **first P2 development module** tests the single-convergence constraint of a set of annotated pairs: a world-space object point and the shadow it casts. It **does not locate a light in 3D**, nor infer physical source distance, distinguish sunlight from a point source, automatically detect shadows, or classify an image's origin as AI.

### Basic physical geometry

For a world-space point `P`, a point-light `S`, and its cast-shadow ground point `Q`, the three points are collinear:

`Q = S + t(P-S)`.

For a receiving plane `n·X + d = 0`, `t = -(n·S + d) / (n·(P-S))`, provided the denominator is nonzero. Perspective projection preserves collinearity. The image points `p`, `q`, and apparent light projection `s` therefore satisfy:

- `l_i = p_i × q_i`;
- `l_i · s = 0`.

Under perspective projection, parallel **3D directional-light** rays may have a **finite image vanishing point**, so a 2D convergence cannot establish that the source is a point light. Exactly parallel **2D** image lines have a vanishing point at image infinity. Both cases are accepted as descriptive projected-convergence patterns.

Reference background: Eric Kee, James F. O'Brien, and Hany Farid, *Exposing Photo Manipulation with Inconsistent Shadows*, ACM TOG 2013, https://doi.org/10.1145/2487228.2487236. Our implementation is a narrower annotated-correspondence estimator, **not** a reproduction of that paper's full constraint programming formulation.

### Computational model

1. Validate `image_shape_hw`, coordinate bounds, nonzero pair lengths, IDs, and confidence weights.
2. Shift/scale image coordinates to reduce numerical condition number.
3. Form homogeneous lines from object/shadow point pairs.
4. Propose intersections with deterministic RANSAC (two independent lines); allow intersections at infinity.
5. Score observations by unoriented angular deviation, in degrees:

   `r_i = asin(|det( normalize(s - m_i), normalize(q_i - p_i) )|)` for a finite projection, where `m_i=(p_i+q_i)/2`.

   For a projected direction at infinity, replace `normalize(s-m_i)` with the common image direction.
6. Refit the best consensus by weighted homogeneous SVD. Reject coincident-ray rank degeneracy.
7. Report inlier/outlier IDs, angular residuals, support fraction, finite projected pixel coordinates or a direction at infinity, and *exploratory* bootstrap spread when finite.

**A single RANSAC-inlier result is not independent evidence:** the lines both construct and fit the model. The current `MEASURED` state means a supported *image-plane convergence* was found, not a validated physical light, an AI score, or a tampering verdict. Outlier rays can originate from more than one legitimate light, incorrect correspondence, reflections, or curved optics.

### Data contract

```json
{
  "image_shape_hw": [720, 1280],
  "correspondences": [
    {"id":"shadow_01", "object_xy":[400,250], "shadow_xy":[430,390], "confidence":1.0},
    {"id":"shadow_02", "object_xy":[650,270], "shadow_xy":[720,415], "confidence":0.9},
    {"id":"shadow_03", "object_xy":[810,280], "shadow_xy":[940,460], "confidence":1.0}
  ]
}
```

The above is **schema illustration**, not a coherent light geometry example. Generate a valid physical example with `python -m aiforensics demo-shadows`.

### Commands

```powershell
python -m aiforensics demo-shadows --out outputs/p2_s01_demo
python -m aiforensics analyze-shadows --input path/to/pairs.json --image path/to/photo.png --out outputs/p2_s01
python scripts/p2_shadow_benchmark.py --trials 60 --out outputs/p2_s01_benchmark.json
pytest -q tests/test_shadow_geometry.py
```

`--image` is optional; dimensions must match the manifest. Output includes `p2_s01_report.json` and, with an image, `p2_s01_shadow_overlay.png`.

### Tests and limitations

- 3D object → point light → planar cast shadow → pinhole camera known-truth fixtures.
- Parallel world illumination vectors that converge to a *finite* image point.
- Exactly parallel image lines with a source at infinity.
- Gaussian annotation noise, deliberate wrong pairings, competing light sources, non-consensus data.
- Degenerate coincident lines, nonfinite annotations, invalid weights, out-of-bounds coordinates, too-short pairs, duplicate IDs, reproducible seeds.
- Model fitting assumes genuine object–shadow **point** correspondences supplied externally. It does not assume that segmenting a dark region automatically identifies its generating object.
- Real-world external validation, camera distortion, automatic correspondence extraction and real false-alarm calibration are intentionally deferred to the final validation phase **after product development**.

### Next implementation scope (not yet built)

- **P2-S02:** constrain projected light source with shadow wedge / uncertain correspondence ranges, then multiple dominant illuminants.
- **P2-S03:** shadow plane homography, object height, and (when known) 3D light position inference.
- **P2-S04:** sun direction plus vertical-object/ground geometric checks.
- **P2-S05:** photometric shading, penumbra and environmental light consistency.
