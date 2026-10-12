# P4-O03 — Focal length, field of view and perspective consistency

**Status:** code + mathematical + synthetic unit/integration tests. **Not** independent real-camera verification.

## 1. Model and coordinate conventions

- Input image coordinate origin is top-left; camera coordinates have positive camera-forward `Z`.
- Known independent extrinsics: `X_camera = R_world_to_camera @ X_world + t_world_to_camera`.
- Zero-skew intrinsic matrix `K = [[fx, 0, cx],[0,fy,cy],[0,0,1]]`.
- Ideal pinhole projection: `u = fx * X_camera/Z_camera + cx`; `v = fy * Y_camera/Z_camera + cy`.
- Points behind the camera, points outside the actual displayed frame and unverified correspondences never become physical violation evidence.
- Nonzero Brown–Conrady distortion from **P4-O01** is supported **only when K and the distortion coefficients are independently known**; observed holdout VPs with distortion are abstained (straight-line vanishing points no longer obey the ideal pinhole model).

## 2. FoV: principal point may be off center

For image width `W` and horizontal focal length `fx` in pixels, **when** `0 <= cx <= W`:

`HFOV = atan(cx / fx) + atan((W-cx) / fx)`

Similarly `VFOV = atan(cy/fy) + atan((H-cy)/fy)` for the vertical axis.

The common `2*atan(W/(2*fx))` is only equivalent if `cx=W/2`. Both image diagonal angular spans are computed directly from the unit rays through opposite image corners, not with a square-pixel approximation. Aspect ratio alone cannot determine FoV without focal calibration.

## 3. Native physical sensor versus current image

For **native** sensor pixel pitch `px,py` in micrometres:

`focal_mm_from_x = native_fx * px / 1000`

`focal_mm_from_y = native_fy * py / 1000`

The difference between these estimates and a claimed independently measured physical focal length is explicitly checked.

If the native sensor pixels were cropped from `(crop_x, crop_y)` and resized from crop dimensions `(crop_w, crop_h)` to `(output_w, output_h)`, then:

```
scale_x = output_w / crop_w
scale_y = output_h / crop_h
fx_out = fx_native * scale_x
fy_out = fy_native * scale_y
cx_out = (cx_native-crop_x) * scale_x
cy_out = (cy_native-crop_y) * scale_y
```

Resizing **does not** physically alter the lens focal length in millimetres. A crop can substantially alter visible FoV despite unchanged optics. All image resizing or perspective warps must be reported.

## 4. Two distinct calibration regimes

**Known-K mode:** input `K` must be independently measured or controlled synthetic ground truth, never deduced from the same holdout measurements. The module predicts independently labelled 3D point projections, 3D line segment endpoints and optionally physical vanishing directions from `R`, `t`, and K.

**Fit-focal-from-train mode:** with independently established `R`, `t` and `(cx,cy)`, estimate `fx` and `fy` by weighted robust least squares from at least ten **train** 3D↔2D correspondences with sufficient angular diversity. **Holdout correspondences are not used to fit** the parameters. If train labels have no independently justified provenance, or Brown–Conrady coefficients are present with unknown focal, return `INDETERMINATE` rather than solve a badly identified joint model.

The accuracy of 3D points, pose, calibration and lens parameters fundamentally limits validity; deliberately fabricated independent measurements defeat a purely mathematical checker. Metadata coherence is only a conditional cross-check, never cryptographic authenticity evidence.

## 5. Evidence protocol

- Sample IDs are unique; `role=train/holdout` must be explicit.
- A minimum of eight **disjoint holdouts** is required.
- For image points, each holdout requires `world_xyz`, `observed_xy_px`, `observed_sigma_px > 0`, and `measurement_provenance`.
- Per-point threshold is `max(tolerance_px, 3 * observed_sigma_px)`; default `tolerance_px = 2.5`. This 3-sigma threshold is an engineering tolerance, **not** a calibrated 99.7% joint confidence interval in the presence of shared parameter errors or non-Gaussian correspondences.
- Independently observed vanishing directions and fronto-parallel segment lengths are separate holdout checks, not used to fit K.
- Optical sensor metadata must be **independently justified**; arbitrary user-supplied metadata are untrusted as evidence.
- `CONSISTENT`, `INCONSISTENT_UNDER_ASSUMPTIONS` and `INDETERMINATE` are conditional geometric statuses only. `decision` always equals `NO_AI_ORIGIN_CONCLUSION`.
- Do not compare image measurements to a generated image's metadata then claim AI detection; circularly estimated 3D scene and pose may explain manipulated content.

## 6. JSON schema and command line

Run `python -m aiforensics demo-optics --out outputs/p4_o03_demo`, then open the generated `p4_o03_fixture.json` for a **fully populated** manifest including `K`, `pose`, `samples`, `sensor_metadata`, `image_transform`, `vanishing_point_holdouts`, and `segment_holdouts`.

`python -m aiforensics demo-optics --fit-focal --out outputs/p4_o03_fit_demo` generates a 24-train, 32-holdout fit example. No holdout points are used to estimate K.

`python -m aiforensics analyze-optics --input <manifest.json> --out outputs/my_optics` creates `p4_o03_report.json` and retains all sample outcomes.

`python scripts/p4_optical_benchmark.py --trials 80 --out outputs/p4_o03_benchmark.json` generates reproducible, controlled synthetic stress measurements.

## 7. Acceptance and limitations

1. Reproduce all prior regression tests (P1, P2, P3, P4-O01/O02).
2. Synthetic positive controls should be geometrically consistent to specified precision.
3. Changed holdout locations, false FoV/focal claims, wrong cropping, unknown pose and invalid geometry should give appropriate conditional inconsistency or abstention.
4. Native Windows acceptance and independent real-lens/real-camera validation remain **deferred until the entire development roadmap is implemented**.
5. Perspective is a geometry consistency property, not proof of image authenticity. Valid physical rendering can be AI-generated; image processing can break the apparent constraints of real photographs.

**Future P4-O04:** radially varying vignetting, cos-fourth illumination, relative optical falloff, chromatic aberration, diffraction/PSF separation and independent photometric evidence when scene illumination is controlled.
