# P6-M02 — Cook–Torrance / isotropic GGX single-scattering specular evidence

Status: **implemented, synthetic-only**. P6-M01 remains the diffuse Lambertian branch. No real images, optics / camera radiometric corrections or Windows native acceptance have been carried out.

## Physical contract and units

- Input `normal_world`, `to_light_world`, `to_camera_world`: world-frame vectors pointing **away from the surface**, normalized by the module. They must be independently constrained if a meaningful image-physics claim is intended.
- `incident_irradiance_rgb`: **linear spectral-channel irradiance perpendicular to the light direction** (not surface-tilted irradiance), same unit family as corresponding outgoing radiance multiplied by steradians. `observed_radiance_rgb`: calibrated linear outgoing radiance, not display-referred sRGB. Both can be normalized physical photometric channels if the same independent calibration is used throughout.
- `f0_rgb` in `[0,1]`: independently constrained reflectance at normal incidence. Schlick F0 is an approximation, **not proof of material identity**.
- `roughness` in `[0.045,1]`: isotropic perceptual roughness, `alpha = roughness²`. Delta-like ideal mirrors are excluded. This is a model parameter, not a universally calibrated surface height variance.
- The engine includes **specular only**; it does **not** silently add P6-M01 diffuse radiance or assume a pixel's total radiance is purely specular.
- Assumptions: opaque, isotropic, single-bounce single-scattering microfacets, one directional illumination per sample, known visiblity and no unknown color/tone processing. No rough metallicity inference from RGB.

## Equations

Let `l`, `v`, `n` be unit directions to source, to camera, and the macroscopic normal, with `n·l > 0`, `n·v > 0`, and `h = (l+v)/||l+v||`. Put `α = roughness²`:

\[
D_{GGX}(n,h,\alpha) = \frac{\alpha^2}{\pi[(n\cdot h)^2(\alpha^2-1)+1]^2}
\]

Exact Smith GGX height-uncorrelated one-sided masking term:

\[
G_1(\mu,\alpha) = \frac{2\mu}{\mu + \sqrt{\alpha^2 + (1-\alpha^2)\mu^2}},\qquad G=G_1(n\cdot l)G_1(n\cdot v).
\]

Approximate Schlick Fresnel RGB:

\[
F(v\cdot h)=F_0+(1-F_0)(1-v\cdot h)^5.
\]

Cook–Torrance single-scattering specular BRDF:

\[
f_r^{spec}(l,v)=\frac{D_{GGX}(n,h)\,G(n,l,v)\,F(v\cdot h)}{4(n\cdot l)(n\cdot v)}.
\]

Directional source outgoing **specular** radiance:

\[
L_o^{spec}=V E_{\perp} (n\cdot l)f_r^{spec}.
\]

The dot factor must NOT be applied twice; for rays below the surface the contribution is zero. BRDF reciprocity is tested by swapping `l` and `v`.

### Numerical energy audit

For each fixed `v` integrate outgoing-versus-incoming directional reflectance:

\[
\rho_{hd}^{spec}(v) = \int_{\Omega^+}f_r^{spec}(l,v)(n\cdot l)\,d\omega_l.
\]

The `audit-microfacet-energy` CLI computes this for three outgoing view cosines, comparing coarse and twice-dense Gaussian-cosine / azimuth meshes. **A uniform angle mesh may miss a needle-like highlight at both resolutions.** Therefore roughness below 0.18 and nonconvergent numerical integrations return `INDETERMINATE`; this is a numerical guard rather than a proof of all-roughness energy conservation. The audit **does not** certify combined diffuse + specular reflectance or multiple-scattering compensation.

### Conditional roughness estimation

- `known_roughness`: independent material parameter and F0 must both be explicitly declared and supplied.
- `fit_roughness`: robust nonlinear least squares on **train** samples; enforce feasible interior optimum, nonzero sensitivity and a local linearized uncertainty guard.
- **holdout** samples are never used to select roughness; each has independent ID and independently calibrated radiometry/geometry. A sample with only image-estimated normals, inferred light, or a non-linear JPEG radiance is `INDETERMINATE`.
- Standardized residual `max_rgb |L_measured-L_predicted| / sigma_effective`. Below 2.5 -> `CONSISTENT`, above 4.5 -> `INCONSISTENT_UNDER_ASSUMPTIONS`, interval -> `INDETERMINATE`. In `fit_roughness`, `sigma_effective` includes a first-order roughness parameter uncertainty term. These are engineering thresholds, **not calibrated p-values**.
- Group status becomes `INDETERMINATE` if any measurement is indeterminate. Per-measurement results remain available.
- `decision` is always `NO_AI_ORIGIN_CONCLUSION`.

## CLI

```powershell
python -m aiforensics demo-microfacet --out outputs/p6_m02_demo
python -m aiforensics demo-microfacet --known-roughness --out outputs/p6_m02_known
python -m aiforensics analyze-microfacet --input outputs/p6_m02_demo/p6_m02_fixture.json --out outputs/p6_m02_check
python -m aiforensics audit-microfacet-energy --roughness 0.45 --f0 0.04 0.04 0.04 --out outputs/p6_m02_energy_audit.json
python scripts/p6_microfacet_benchmark.py --trials 80
python -m pytest -q
```

## Manifest example

```json
{
  "calibration_mode": "known_roughness",
  "roughness": 0.42,
  "roughness_provenance": "independent_material_measurement",
  "f0_rgb": [0.04, 0.04, 0.04],
  "f0_provenance": "independent_material_measurement",
  "incident_irradiance_rgb": [16.0, 15.0, 13.0],
  "light_provenance": "independent_irradiance_measurement",
  "samples": [
    {
      "id": "feature-001", "role": "holdout",
      "normal_world": [0,0,1], "to_light_world": [0,0,1], "to_camera_world": [0,0,1],
      "observed_radiance_rgb": [0.8,0.8,0.8],
      "sigma_radiance_rgb": [0.02,0.02,0.02],
      "geometry_provenance": "independent_metric_normal_and_view",
      "radiometry_provenance": "independent_linear_calibration"
    }
  ]
}
```

For a verdict, the default minimum is **6 holdout** samples; the short example is a schema illustration and therefore abstains. Fit mode defaults to **14 train** and **6 holdout**.

## Controlled synthetic regression and limitations

Positive tests include Fresnel limits, reciprocity, GGX NDF normalization, Smith boundaries, below-surface rejection, known-versus-fitted roughness, train/holdout separation, and data provenance. Negative tests deliberately change F0 or roughness, radiance, sample IDs, and input vectors. Controlled benchmark: 40 known roughness + 40 fitted roughness runs, each with 21 physically clean and 3 deliberately corrupted holdouts. Test values **do not transfer to real photos** because forward generator and estimation assume the same functional family.

This module does not infer material type, roughness/F0 jointly from one image, physical light source from intensity, diffuse/specular decomposition, multiple GGX lobes, color management, camera optics, BRDF spectral dispersion, or AI-image provenance. Those require independent inputs or later work.

## Formula references

- LearnOpenGL, [PBR Theory](https://learnopengl.com/PBR/Theory) and [PBR Lighting](https://learnopengl.com/PBR/Lighting) (describes the Cook–Torrance/GGX/Schlick decomposition; this module uses **exact Smith G1** rather than the shader's remapped Schlick-GGX approximation).
- Pharr, Jakob & Humphreys, [Physically Based Rendering, v4](https://pbr-book.org/4ed/Reflection_Models/Roughness_Using_Microfacet_Theory), for microfacet framework and subtleties in masking/multiple scattering.
