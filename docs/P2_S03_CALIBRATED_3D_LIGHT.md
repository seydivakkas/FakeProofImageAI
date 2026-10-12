# P2-S03 — Calibrated 3D Light Geometry (Physics First)

## Scope

**Inputs:** camera intrinsics `K`, full extrinsics `R_world_to_camera`, `t_world_to_camera`, receiver plane, matched object/shadow pixels, *independently known* point heights over that plane. Camera `K` alone is **insufficient** for metric 3D source positions. G02 may help with `K` and rotation estimates, but absolute translation/world scale must come from an independent geometric reference.

**Outputs:** 3D **conditional estimate** of a finite source, or a direction for approximately parallel 3D light rays. Reports contain model observability, confidence-weighted support, rejected measurements, raw physical residuals and explicit ambiguity status. No AI-origin, source-count or photo-authenticity claim.

### Camera and plane conventions

- `x_camera = R_world_to_camera @ X_world + t_world_to_camera`.
- `C_world = -R_world_to_camera.T @ t_world_to_camera`.
- Receiver plane `n.T @ X + d = 0`. The code normalizes `(n,d)` to a unit `n`.
- `height_above_plane > 0` means the Euclidean distance **along +n** of an elevated object's sampled 3D point; it is not necessarily the full height of the visible object.
- World coordinates and heights must use the same length unit, declared by `world_units` (e.g. `m`).
- The receiver must be planar, the camera rectilinear/undistorted, and object/shadow positions correspond to the same physical feature.

### Geometric derivation

For pixel `p̃=(u,v,1)`, world ray is:

`X(α) = C + α R^T K^-1 p̃`.

Ray intersecting an offset parallel to the receiver plane at height `h` is:

`α = (h - d - n.T C) / (n.T R^T K^-1 p̃)`.

For shadow pixels, `h=0`; their reconstructed world positions are `Q_i`. For corresponding elevated object pixels, known heights `h_i>0` give world positions `P_i`. The oriented 3D ray *toward* the source is:

`u_i = (P_i - Q_i) / ||P_i - Q_i||`.

For a finite point source `S` the collinear 3D ray family is `S = Q_i + τ_i u_i`, with `τ_i > ||P_i - Q_i||`, so that the physical source lies past the corresponding object point. Its least-squares estimate minimizes:

`sum_i w_i || (I - u_i u_i^T)(S - Q_i) ||^2`

with normal matrix `A = sum_i w_i (I - u_i u_i^T)`. This solver includes RANSAC, a positive-source-side constraint, a minimum unique-solution eigenvalue ratio, and a relative source distance/scene-extent guard against pathological long-range intersection fits.

For parallel rays, `u_i ≈ u`. We robustly estimate `u` from weighted directions, reporting `DIRECTIONAL_OR_DISTANT_LIGHT`; source distance is not observable and is deliberately **not** returned. When finite and parallel models both fit within chosen tolerances, result is `INDETERMINATE` rather than inventing a source distance.

**Thresholds are engineering defaults on synthetic data, not calibrated statistical significance.** `point_tolerance_world` is expressed in world units, so it must be adjusted for a change of coordinate scale. Pixel error, calibration uncertainty, object height uncertainty and plane uncertainty are not yet fully propagated into an absolute statistical confidence interval.

### JSON input

```json
{
  "image_shape_hw": [720, 1280],
  "world_units": "m",
  "camera": {
    "K": [[850, 0, 640], [0, 850, 360], [0, 0, 1]],
    "R_world_to_camera": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    "t_world_to_camera": [0, 0, 0]
  },
  "ground_plane": {"normal_world": [0, 0, 1], "offset_world": 0},
  "correspondences": [
    {"id": "pair_00", "family_id": "light_candidate_A", "object_xy": [640, 340], "shadow_xy": [620, 400], "height_above_plane": 1.2, "confidence": 1.0}
  ]
}
```

This is a **schema illustration**, not a physical working calibration or sufficient number of pairs. Generate consistent sample data with `demo-light-3d`.

### Commands

```powershell
python -m aiforensics demo-light-3d --out outputs/p2_s03_demo
python -m aiforensics analyze-light-3d --input outputs/p2_s03_demo/p2_s03_fixture.json --image outputs/p2_s03_demo/p2_s03_fixture.png --out outputs/p2_s03_analysis
python scripts/p2_shadow_3d_benchmark.py --trials 60 --out outputs/p2_s03_benchmark.json
```

### Optional S02 integration

If the same correspondences were analyzed by S02, pass `--s02-report outputs/p2_s02_report.json`. The bridge assigns S02-proposed `model_id` values as candidate `family_id`, excluding S02 ambiguous or unassigned pairs. It requires a `MEASURED` S02 report and matching image dimensions, but does **not** independently verify the image-to-annotation source. Operators must ensure both manifests refer to exactly the same pairs/pixels; corresponding IDs alone do not prove data identity. S02 families do not prove distinct physical lights.

### Validation and failure policy

- Exact point-source source reconstruction and oriented ray-plane intersections: controlled synthetic tests.
- Parallel directional rays: source **direction only**, distance not inferred.
- Mixed multi-source fixture: external correct family annotations required, or optional S02 assignments as hypotheses.
- Outlier pairs, insufficient support, identical/parallel rays, wrong camera/plane and invalid source direction: negative tests.
- Coordinates incompatible with positive forward ray-plane intersection are rejected before fitting and counted against global reconstruction coverage.
- 3D plane tilts + changes in coordinate frame: tested under rigid transforms.
- Measured real-photo source error and actual physical false-positive rate: **DEFERRED** to final validation phase.

### Scientific limits

A physically consistent CGI or AI image can satisfy all the above constraints. A real camera photo with invalid annotations, lens warping, transparent/uneven receiver, multiple bounce illumination, non-point sources, or erroneous metric calibration may fail. Do not infer `AI_GENERATED` from the solver output.
