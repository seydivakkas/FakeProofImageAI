# P5-D02 — Multiple Planes, Occlusion, Metric Depth Ordering

**Release:** v0.19.0 — development + synthetic tests only. No real-camera / Windows-device acceptance. No AI-origin verdict.

## Physical contract

All geometry uses P5-D01's **world frame and known calibration**. Camera: `X_camera = R_world_to_camera @ X_world + t_world_to_camera`. A detected image pixel `p` defines a *ray*, not a metric 3D point:

\[
 C=-R^Tt, \quad r(p)=\frac{R^TK^{-1}[p_x,p_y,1]^T}{\|R^TK^{-1}[p_x,p_y,1]^T\|}, \quad X(\lambda)=C+\lambda r.
\]

For a declared planar polygon `i` with unit normal `n_i` and plane offset `d_i`:

\[
 \lambda_i=-\frac{n_i\cdot C+d_i}{n_i\cdot r(p)}.
\]

Keep the intersection **only if** (1) ray is not parallel to plane, (2) `0 < lambda <= max_ray_distance_world`, (3) point lies within the finite convex polygon, and (4) the declared face direction is visible for single-sided objects.

An opaque surface with the smallest positive ray depth is the modeled front layer. Translucent/transparent geometry **must** be marked `opaque:false`, and is never treated as a definite occluder. Near-equal layers within `min_depth_gap_world` are **unresolvable** and reported `INDETERMINATE`.

### Independent evidence

Geometric consistency requires **externally measured** surface polygons (`geometry_provenance:"independent_metric"`) and **independent visibility observations** (`visibility_provenance:"independent_annotation"`). A geometry prediction alone cannot be its own validation. If an independently visible far layer is physically behind an independently measured nearer opaque polygon *at the same ray*, the annotation and physical model are **inconsistent under the stated assumptions**. This does not establish an AI-generated image.

For a claimed visible independent 3D anchor, check 3D distance to its designated plane and containment, reprojection to its annotated pixel, and whether a nearer opaque polygon obstructs it. If any condition is ambiguous near a boundary, **abstain**.

A missing intersection is not treated as a conclusive error unless `declared_scene_complete:true`; this is an explicit and strong assumption that the declared scene accounts for relevant visible surfaces.

### Pixel noise and limits

To avoid harsh decisions at polygon edges, repeat intersection ordering at eight perturbation points around each pixel (at least 0.5 px displacement, or 3× supplied uncertainty). If the front layer changes, return `INDETERMINATE`. This guard is deterministic and **not** a calibrated probability or numerical proof against errors. Camera/plane calibration errors are not propagated through the current stage; they require separate uncertainty budgeting.

## JSON input

The executable demo produces the complete schema:

```powershell
python -m aiforensics demo-occlusion --out outputs/p5_d02_demo
python -m aiforensics analyze-occlusion --input outputs/p5_d02_demo/p5_d02_fixture.json --out outputs/p5_d02_check
```

A shortened structure:

```json
{
  "image_shape_hw": [720, 1280],
  "camera": {
    "K": [[920,0,640],[0,915,360],[0,0,1]],
    "R_world_to_camera": [[1,0,0],[0,1,0],[0,0,1]],
    "t_world_to_camera": [0,0,0]
  },
  "surfaces": [
    {
      "id": "near_panel",
      "normal_world": [0,1,0],
      "offset_world": -2,
      "polygon_world_xyz": [[-1,2,0],[1,2,0],[1,2,3],[-1,2,3]],
      "geometry_provenance": "independent_metric",
      "opaque": true,
      "double_sided": true
    }
  ],
  "visibility_probes": [
    {
      "id": "visible_1",
      "pixel_xy": [640,360],
      "pixel_sigma_px": 0.3,
      "observed_front_surface_id": "near_panel",
      "visibility_provenance": "independent_annotation"
    }
  ],
  "metric_anchors": [
    {
      "id": "anchor_1",
      "surface_id": "near_panel",
      "independent_world_xyz": [0,2,1],
      "pixel_xy": [640,360],
      "anchor_provenance": "independent_metric",
      "claimed_visible": true,
      "visibility_provenance": "independent_annotation"
    }
  ]
}
```

The schema above is illustrative; its toy camera/point fields are **not** an internally coherent acceptance fixture. For runnable data, use the generated `p5_d02_fixture.json` with all calibrated extrinsics.

Optional fields: `d01_observations` and `gravity_world` to run P5-D01 support/contact checks with the same `camera`, `image_shape_hw`, and either shared `surfaces` or separate `support_surfaces`. P5-D01 results are placed under `p5_d01_integration` and **not silently conflated with P5-D02**.

The output `p5_d02_report.json` includes ordered ray-plane hits with metric distances, predicted front opaque surface, annotation provenance gate, independent 3D anchor reprojection, reasons and limitations. `decision` is always `NO_AI_ORIGIN_CONCLUSION`.

## Test and synthetic experiment

```powershell
python -m pytest -q
python -m aiforensics demo-occlusion
python scripts/p5_occlusion_benchmark.py --trials 80 --out outputs/p5_d02_benchmark.json
```

The controlled two-layer scene exercises direct visibility, far-wall visibility outside the near-panel footprint, false front-layer claims, independently measured visible and occluded anchors, and insufficiently grounded evidence. Randomized trials vary image annotation perturbations, not actual unmeasured camera/lens physics. Synthetic labels are generated from the same model family and **do not estimate real-photo false-positive or false-negative rates**.

### Known exclusions

- No monocular free-form surface or unconstrained metric depth recovery.
- No automatic object detection/instance masks or semantic scene labeling.
- No dense z-buffer mesh rendering, complex nonplanar solids, cast shadow transparency, volumetric occlusion, rolling shutter, dynamic objects, or true scene completeness proof.
- No complete covariance propagation of K/R/t, 3D polygons and segmentation masks.
- No claim that a model-consistent image is authentic or model-inconsistent image is AI-generated.

**Next development:** P5-D03 gravity, rigid support stability and contact dynamics, then P6–P8. Independently measured real photographs and Windows end-to-end acceptance occur at the final project validation stage.
