# P6-M01 — Lambertian Material Reflection, BRDF & Energy Conservation

**Release:** v0.21.0 · **Evidence status:** conditional physical-model tests; **NOT AI-origin classification**.

## Motivation and measurement contract

A single object's RGB shade does **not** independently determine material reflectance, lighting power, geometry, or image origin. P6-M01 requires camera-*linear*, photometrically calibrated **outgoing radiance** (W sr⁻¹ m⁻²), **incident irradiance** (W m⁻²), independent 3D normals, and light direction. Values must be in compatible *per-channel* spectral/RGB response units and obtained with camera response / white-balance accounted for. A JPEG's gamma-encoded RGB values are not a valid input by themselves.

The geometric normal must be correctly oriented; we assume the observed material surface is front-facing and opaque. This first model omits specular reflection, transmission, internal scattering, interreflection, wavelength-dependent camera/sensor effects, camera saturation, and unknown shadow visibility. These effects can cause a lawful photograph to violate the simplified model.

## 1. Lambertian reflection

For independent known outgoing reflectance (albedo) `rho` in [0,1]:

\[
 f_r(\omega_i,\omega_o)=\frac{\rho}{\pi}\quad[\mathrm{sr}^{-1}],
 \qquad \cos\theta_i=\max(0,\mathbf n\cdot\mathbf l).
\]

For direct irradiance `E_direct` measured perpendicular to the illuminating ray, independently known ambient integrated irradiance `E_ambient`, and known visible fraction `V`:

\[
 L_o = \frac{\rho}{\pi}\left[E_{\rm ambient} + V\,E_{\rm direct}\max(0,\mathbf n\cdot\mathbf l)\right].
\]

Vectorized over 3 channels, but this RGB approximation is **not** a physically measured continuous reflectance spectrum. `E_ambient` is not additional emitted radiance and is not multiplied by the direct-light cosine.

## 2. Energy conservation and reciprocity

For any physically acceptable reflecting BRDF (no transmission), we require nonnegative BRDF, Helmholtz reciprocity, and:

\[
 \int_{\Omega^+}f_r(\omega_i,\omega_o)\cos\theta_i\,d\omega_i\ \leq\ 1
\]

for each \(\omega_o\). **Do not** test `BRDF <= 1`: the angular density has inverse-steradian units, and even correct BRDFs may exceed 1 at certain angles. A Lambertian BRDF integrates to exactly \(\rho\), not \(\rho/\pi\).

The included `audit_brdf_matrix()` accepts a tabulated BRDF matrix `[outgoing,incoming]` on a correctly weighted hemisphere. A discrete sum **cannot prove** conservation of an arbitrary BRDF between samples: increase angular resolution and model peak widths; evaluate grazing-angle and near-delta lobes separately. The audit checks sampled reciprocity and nonnegativity too.

Reference:
- [pbrt 4e, Surface Reflection](https://pbr-book.org/4ed/Radiometry%2C_Spectra%2C_and_Color/Surface_Reflection)
- [pbrt 4e, Diffuse Reflection](https://www.pbr-book.org/4ed/Reflection_Models/Diffuse_Reflection)

## 3. Calibration vs holdout

- `known_albedo`: material reflectance has independently documented provenance.
- `fit_albedo`: all three reflectances are fitted **only to train** samples under *independently fixed and known illumination*. A local weighted robust fit and conditional standard errors are reported.
- `holdout`: never used in fit. Each independent observation has an expected 3-channel radiance and a standardized residual; a threshold buffer separates `CONSISTENT` from `INCONSISTENT_UNDER_ASSUMPTIONS`. Border cases become `INDETERMINATE`.
- Every sample requires unique ID, independent normal and calibrated radiance provenance. Missing provenance or unidentifiable lighting → `INDETERMINATE`.

**Important**: `light_provenance` and per-sample fields are *declarations by the data provider*, not cryptographic attestation. This module does not independently certify them. No camera response calibration is executed here; P4-O04's flat-field routines may be used upstream under their own measurement contracts. No independent real-camera acceptance yet.

## 4. Example manifest schema

```json
{
  "calibration_mode": "fit_albedo",
  "light_provenance": "synthetic_ground_truth",
  "light_direction_world": [0.48, 0.20, 0.854],
  "direct_irradiance_rgb": [16, 13, 11],
  "ambient_irradiance_rgb": [2, 2.3, 2.1],
  "samples": [
    {"id":"train_1", "role":"train", "normal_world":[0,0,1],
     "observed_radiance_rgb":[1.2,0.6,0.4],
     "sigma_radiance_rgb":[0.018,0.018,0.018],
     "geometry_provenance":"synthetic_ground_truth",
     "radiometry_provenance":"synthetic_ground_truth"}
  ]
}
```

The short sample **cannot pass calibration** because it lacks adequate train/holdout observations. Run the generated fixture instead.

## 5. Commands

```powershell
python -m aiforensics demo-material
python -m aiforensics demo-material --known-albedo
python -m aiforensics analyze-material --input outputs/p6_m01_demo/p6_m01_fixture.json --out outputs/p6_m01_check
python scripts/p6_material_benchmark.py --trials 80
```

For the BRDF audit, create `audit.json` with `{"brdf_model":"lambertian","diffuse_albedo":0.7,"use_builtin_quadrature":true}` and run:

```powershell
python -m aiforensics audit-brdf --input audit.json --out outputs/p6_m01_brdf_audit.json
```

Or supply `brdf_values_matrix`, `directions`, and `solid_angle_weights` explicitly for arbitrary sampled BRDFs.

## 6. Known limitations and future stages

The validation generator uses the **same Lambertian family** as the fitting model; closed-loop success is expected and not strong evidence of performance on real materials or manipulations. This first module does not identify material class from RGB; P6-M02 should separately model microfacet/specular, Fresnel, roughness, and reflectance anisotropy. Real independent evaluation, lighting ground truth, noise calibration, material measurements, and Windows acceptance all occur after the feature build-out.
