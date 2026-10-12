# P4-O02 — Thin lens, geometric defocus, circle of confusion and depth of field

## Purpose and scope

This is a conditional physics experiment, **not** an AI-origin classifier. Input distances are in **mm**, native sensor pitch in **µm**, predicted blur diameter in **sensor pixels**. The model assumes a paraxial symmetrical thin lens with circular pupil and a planar sensor focused at a known distance. It does *not* recover depths or a lens PSF from an arbitrary JPG photograph.

## 1. Geometric derivation

Thin-lens equation for object distance `z > f` and image-plane distance `v_z`:

```
1/f = 1/z + 1/v_z
v_z = f z / (z - f)
```

For focus distance `s > f`, place the sensor at `v_s = f s/(s-f)`. The aperture diameter is `D = f/N`, where `N` is the f-number. Similar triangles imply geometric blur diameter **on the sensor**:

```
c(z) = D |v_s/v_z - 1|
     = (f²/N) |z-s| / (z(s-f))           [mm]

c_px = c_mm * 1000 / pixel_pitch_um      [native pixels]
```

For an object at infinity with finite focus: `c_inf = f²/(N(s-f))`. For an infinity-focus sensor: `c(z) = f²/(Nz)`.

For a permissible CoC `c0 = acceptable_coc_px * pixel_pitch_um/1000`:

```
near = f² s / ( f² + N*c0*(s-f) )
far  = f² s / ( f² - N*c0*(s-f) )   if denominator > 0; otherwise infinity
H    = f²/(N*c0) + f
```

At infinity focus, the near limit is `f²/(N*c0)` (the exact thin-lens limit). The classic `H` formula uses a specific principal-plane convention; real thick-lens lenses can differ.

**The acceptable CoC is a user-selected threshold, not a biological or optical universal constant.** There is no physically sharp/blurred binary division, and optical blur increases continuously away from the focus distance.

## 2. PSF approximation

`circular_psf(diameter_px)` returns a normalized **uniform disk** aperture kernel with subpixel area integration, suitable for generating isolated controlled patches. Its energy is exactly normalized; huge kernels cause a hard failure rather than clipped blur. It is *not* a complete lens simulation: diffraction Airy patterns, field-dependent aberrations, longitudinal chromatic aberration, occlusion at depth boundaries, foreground bokeh shapes, aperture blade geometry, lens breathing, and sensor microlenses are omitted. Different depth layers must be composited with visibility and occlusion logic for production-grade 3D rendering.

If measurements come from JPEG edges, edge spread width is **not** directly CoC diameter; calibrated PSF estimation and a motion/denoising/sharpening separation are prerequisites to a physical comparison.

## 3. JSON data contract

```json
{
  "schema_version": "p4-o02-v1",
  "optics": {
    "focal_mm": 35.0,
    "f_number": 5.6,
    "pixel_pitch_um": 4.0,
    "focus_distance_mm": 2500.0,
    "focus_sigma_mm": 0.0
  },
  "acceptable_coc_px": 2.0,
  "samples": [
    {
      "id": "independent_patch_01",
      "role": "holdout",
      "depth_mm": 1800.0,
      "depth_sigma_mm": 0.0,
      "observed_coc_px": 6.70,
      "observed_sigma_px": 0.25,
      "measurement_provenance": "calibrated_coc_diameter"
    }
  ]
}
```

`focus_distance_mm` may be `null` to **fit focus from training observations only**; that option requires ≥5 sufficiently distinct training depth observations and ≥3 independent held-out observations. For an exact focus provided from external calibration, no focus fitting occurs. Training observations do not form independent evidence when focus is fitted.

If `measurement_provenance` is absent or differs from `calibrated_coc_diameter`, observations are reported `INDETERMINATE`, **not** treated as optical inconsistency. This field is a *declaration* rather than a verified certificate; users must provide genuinely independent CoC calibration and validate scene depths. Conditional uncertainty propagates reported depth/focus σ using seeded Monte Carlo sampling; this is not a real-data coverage guarantee.

A sample is `CONSISTENT` if absolute measured-minus-predicted diameter is within `tolerance_sigma * hypot(observed_sigma_px, prediction_sigma_px)`. Otherwise it is `INCONSISTENT_UNDER_ASSUMPTIONS`, not "AI-generated". A missing or unsuitable observed CoC is `INDETERMINATE`. The global state uses independently evaluated holdout (or independently calibrated optics) only. No cross-sample statistical error-rate calibration has yet been established.

## 4. Run

```powershell
python -m aiforensics demo-defocus --out outputs/p4_o02_demo
python -m aiforensics demo-defocus --fit-focus --out outputs/p4_o02_fit_demo
python -m aiforensics analyze-defocus --input outputs/p4_o02_demo/p4_o02_fixture.json --out outputs/p4_o02_analysis
python scripts/p4_defocus_benchmark.py --trials 80 --out outputs/p4_o02_benchmark.json
python -m pytest -q
```

Outputs: `p4_o02_report.json`, `p4_o02_fixture.json`, `p4_o02_depth_comparison.png`, benchmark JSON.

## 5. Connection to P4-O01 and next work

P4-O01 addresses geometrical **distortion** of projected positions; P4-O02 predicts **defocus** of known-depth points and should consume physically calibrated optical information and unresized native-pixel scale. Correcting Brown–Conrady image coordinates does not calibrate the optical PSF and interpolation during undistortion can alter observed edge sharpness. Later P4 modules should address focus breathing, diffraction/field-dependent PSF and exposure / sensor-pipeline confounders.

## Acceptance boundaries

- Mathematical forward prediction, input validation and synthetic regression can be PASS.
- Real lens PSF / independently known depth / camera metadata, ground-truth CoC calibration and Windows acceptance: **DEFERRED to the final validation phase**.
- No reported mathematical inconsistency is a provenance verdict; AI-generated imagery can respect the thin lens model, and real camera pictures can depart from the ideal model.

Sources used as background for model assumptions (not empirical validation): [RP Photonics, Depth of Field](https://www.rp-photonics.com/depth_of_field.html); [Circle of Confusion](https://en.wikipedia.org/wiki/Circle_of_confusion).
