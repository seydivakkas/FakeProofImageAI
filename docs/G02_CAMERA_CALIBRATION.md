# P1–G02: Three orthogonal finite vanishing points → camera calibration

## Scope and provenance

This is an independent NumPy implementation of standard **Image of the Absolute Conic (IAC)** geometry. The relevant comparison is EyeLib's [`computeKviaIAC.m`](https://github.com/carlosbeltran/EyeLib/blob/master/matlab/computeKviaIAC.m) and [`computeRviaVanishingPointsandK.m`](https://github.com/carlosbeltran/EyeLib/blob/master/matlab/computeRviaVanishingPointsandK.m). **EyeLib source code has not been copied into this project.** The numerical formulation, validity checks, tests and CLI are original implementations.

### Camera assumptions

1. Single pinhole camera, central projection, negligible/rectified distortion.
2. The three **independently labeled** line families represent mutually orthogonal 3D world directions. Their perpendicularity **cannot generally be proved from an arbitrary single image**.
3. Their vanishing points are finite and numerically distinguishable (VP at infinity is not implemented).
4. Zero sensor-axis skew, square pixels: `fx = fy = f`.
5. Principal point `(cx,cy)` may differ from image center; it is not hard-coded.

## Equations

For three homogeneous vanishing points `v_i`, and orthogonal 3D direction pairs `(i,j)`:

`v_i.T @ omega @ v_j = 0`, with `omega = inv(K).T @ inv(K)`.

`K = [[f,0,cx],[0,f,cy],[0,0,1]]`.

In normalized image coordinates `u=(x-w/2)/diag`, `v=(y-h/2)/diag`, define `D = cx_n^2 + cy_n^2 + f_n^2`. The three pairwise constraints are

`(ui+uj)*cx_n + (vi+vj)*cy_n - D = ui*uj + vi*vj`.

Solve a 3×3 linear system for `(cx_n,cy_n,D)`, then require `f_n^2 = D - cx_n^2 - cy_n^2 > 0`. Convert units back to pixels.

Get camera rays as `q_i = inv(K) @ [x_i,y_i,1]`. Normalize the three columns; choose a right-handed representative of their sign-ambiguous basis and orthogonalize by SVD, returning `R ∈ SO(3)`.

A successful calibration requires `K` finite and `f>0`, `R.T @ R≈I`, `det(R)≈+1`, plus explicit numerical condition limits. These are **mathematical** acceptance tests, not image authenticity tests.

## Why “low residual” is not proof

The three orthogonal VP pairs provide *exactly three* scalar equations for *three* camera unknowns under this model. Thus the fitted pairwise orthogonality residuals on the same input points are **zero by construction** (within floating-point precision). The residuals cannot independently establish that the scene had orthogonal line families, that an image is real, or that a calibration is correct.

True physical verification requires independently grounded scene assumptions, additional known geometry, independent views / known camera parameters, or separately captured measurements. G01 fitting residuals show how well 2D line segments support a **particular VP family**, not how likely a photo is AI-generated.

## Numerical failure cases and `INDETERMINATE`

- Less than three labeled families or G01 unable to find any finite VP.
- Singular / ill-conditioned linear system from badly arranged finite VPs.
- Computed `f² <= 0` or unrealistic numerical result under configured limits.
- Infinite vanishing points / severe lens distortion / curved structures / non-Manhattan scene.
- Even with `MEASURED`, ambiguous world-axis signs remain and optical properties may be unidentified.

## Local offline workflows

```powershell
# Existing image: descriptive G01 only; G02 does not assume candidate directions are orthogonal
python -m aiforensics analyze "corridor.jpg" --out outputs/real_image

# Reproducible end-to-end G01 → G02 using externally labeled directions
python -m aiforensics calibrate-segments --input examples/synthetic_orthogonal_line_groups.json --out outputs/g01_g02

# Direct G02 if three actual orthogonal vanishing points are known
python -m aiforensics calibrate --width 1280 --height 720 --vp=-554.1,-642.0 --vp=84.0,1830.9 --vp=1505.8,136.6 --out outputs/g02_direct

# Repeatable synthetic benchmark
python -m aiforensics benchmark-g02 --trials 50 --out outputs/g02_benchmark
```

Input JSON format:

```json
{
  "image_shape_hw": [720, 1280],
  "orthogonal_groups": [
    [[x1,y1,x2,y2], [x1,y1,x2,y2]],
    [[x1,y1,x2,y2], [x1,y1,x2,y2]],
    [[x1,y1,x2,y2], [x1,y1,x2,y2]]
  ]
}
```

Each group needs sufficient non-degenerate line segments; at least five by default. Their correspondence to three **orthogonal physical directions** must be established outside the estimator. The included example JSON is controlled synthetic data, not a real image.

## Integration contracts

- `calibrate_three_orthogonal_vps(vps_xy, image_shape) -> CalibrationResult` or `CalibrationError`
- `calibrate_from_g01_groups(groups, image_shape) -> {state, g01_models, g02_calibration}`
- `analyze` intentionally returns `g02.state=INDETERMINATE` when VP groups are unlabelled.
- Outputs preserve `decision=NO_AI_ORIGIN_CONCLUSION`.

## External references

- EyeLib (algorithm reference only): https://github.com/carlosbeltran/EyeLib
- Hartley & Zisserman, *Multiple View Geometry in Computer Vision*, 2nd edition, Chapter 8.
- OpenCV calibration documentation: https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html
