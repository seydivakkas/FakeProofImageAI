# P5-D01 — Calibration-conditioned 3D depth, contact and support geometry

**Scope:** engineering/model test, not real-image verification and not proof of AI-generated content. v0.18.0.

## The epistemic limit of a single photograph

A pinhole pixel defines a **ray** rather than a unique 3D point. To compute a 3D coordinate from one image, this module **assumes** an independently known metric support plane, camera `K/R/t`, gravity direction, and a *finite*, convex, independently measured support polygon. Ray-plane intersection is a **conditional ground point candidate**. It is circular to assert physical contact merely because the ray was intersected with a plane. No physical contact verdict is inferred from that intersection alone.

The core camera convention is shared with P2-S03/P4-O03:

\[
\tilde p\sim K(RX+t),\qquad C=-R^Tt,\qquad
r=\frac{R^TK^{-1}\tilde p}{\|R^TK^{-1}\tilde p\|}.
\]

With the independent support plane `n dot X + d = 0`:

\[
\lambda=-\frac{n\cdot C+d}{n\cdot r},\qquad X_\mathrm{support}=C+\lambda r,\quad \lambda>0.
\]

A ray parallel to the plane, intersecting behind the camera or excessively far away produces `INDETERMINATE`. The finite polygon is checked separately; an intersection outside this polygon is only an unsupported **candidate**, not conclusive evidence that an object is floating.

## The independent physical checks

1. **Independent 3D anchor:** `independent_base_world_xyz`, with `base_world_provenance: independent_metric`, must lie on the support plane **and** inside its finite polygon. This independent anchor must also reproject to its annotated image pixel. An anchor derived from the *same assumed plane* is disallowed as independent evidence.
2. **Independent known height:** for a known rigid and gravity-aligned object, with `height_provenance: independent_metric` and `upright_gravity_aligned: true`, the top is `X_top = X_support - h g`, where `g` is the unit **downward** gravity direction. The projected top must agree with the observed top pixel. This check is conditional on the base-ground assumption, and **does not independently prove contact**.
3. **Static support:** for externally supplied metric center-of-mass and explicitly declared `static_unanchored: true`, project the COM **along gravity** onto the support plane. If it lies outside the polygon, the *simplified unanchored static equilibrium hypothesis* fails. External braces, momentum, contact forces, friction and articulated footprints are out of scope; it is not a general physics impossibility claim. A support normal not facing upward against gravity yields `INDETERMINATE` for this check.
4. **P4-O01 optional lens model:** Brown–Conrady `[k1,k2,p1,p2,(k3)]` distortion is inverted before ray back-projection and applied to forward projections. Uninvertible inputs fail safely.
5. **Pixel uncertainty:** optional `base_pixel_sigma_px` and `top_pixel_sigma_px` provide an approximate noise guard. Finite-difference Jacobians propagate base pixel covariance into **conditional ground XYZ uncertainty**, with exact camera and plane assumed. Borderline residuals yield `INDETERMINATE` rather than an unsupported hard contradiction. This is **not** a calibrated confidence interval.

## Manifest schema (minimal)

```json
{
  "image_shape_hw": [720, 1280],
  "camera": {
    "K": [[920,0,640],[0,915,360],[0,0,1]],
    "R_world_to_camera": [[1,0,0],[0,1,0],[0,0,1]],
    "t_world_to_camera": [0,0,0]
  },
  "gravity_world": [0,0,-1],
  "support_surfaces": [{
    "id": "floor",
    "normal_world": [0,0,1],
    "offset_world": 0,
    "polygon_world_xyz": [[-3,-2,0],[3,-2,0],[3,5,0],[-3,5,0]]
  }],
  "observations": [{
    "id": "obj_1",
    "support_id": "floor",
    "base_pixel_xy": [620,400],
    "top_pixel_xy": [620,280],
    "upright_gravity_aligned": true,
    "known_height_world": 1.5,
    "height_provenance": "independent_metric",
    "base_pixel_sigma_px": 0.4,
    "top_pixel_sigma_px": 0.4
  }]
}
```

**Note:** The above is a schema illustration, not a physically consistent camera fixture. Generate and use the **actual valid** geometry from `python -m aiforensics demo-depth-contact` to see real sample values.

The support polygon must be convex, coplanar and nondegenerate. World distances, heights and contact tolerances must share a metric reference scale. Default contact tolerance is `0.03` world units and pixel reprojection tolerance is `3.0` pixels. Not calibrated for independent real hardware.

## CLI and outputs

```powershell
python -m aiforensics demo-depth-contact --out outputs/p5_d01_demo
python -m aiforensics analyze-depth-contact --input outputs/p5_d01_demo/p5_d01_fixture.json --out outputs/p5_d01_analysis
python scripts/p5_depth_contact_benchmark.py --trials 80
```

Optionally pass `--image photo.png` to the analysis CLI for a source-image overlay. The exact width/height must match the manifest; image SHA-256 and pixel evidence are written to JSON. The analytic evaluation does not require or classify a photograph.

`p5_d01_report.json` contains row-level states, conditional 3D coordinates/depth, support-polygon hits, independent reprojection and contact residuals, optional COM result, and assumptions. **No AI origin verdict** is ever issued.

## Scientific boundaries and final acceptance

- P5-D01 does not estimate camera extrinsics, floor segmentation, depth maps, gravity, object scale or object 3D point anchors automatically from image appearance. These inputs must be independently supplied. There is no monocular metric-depth recovery for arbitrary unsupported objects.
- The optional height check is for *upright rigid landmarks only*; articulated poses or tilted objects need a different forward model.
- A single provided pixel set can inherit annotation error, occlusion, imprecise object geometry or wrong scene assumptions. Conditional errors can arise in authentic photographs and physically perfect renders.
- For genuine floating-object detection one needs an independent depth or placement constraint, not just a presumed floor pixel.
- Synthetic fixtures share a forward camera model with the inverse engine. Negative controls and noise are engineering checks, **not independent physical validation**.
- No training/field photo calibration, real camera external metrology, detection FPR, ground truth depth precision, or real Windows acceptance has yet been carried out. Those remain intentionally deferred to the final end-to-end acceptance phase.
