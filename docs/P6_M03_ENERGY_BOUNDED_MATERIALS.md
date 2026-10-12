# P6-M03 — Energy-bounded diffuse + microfacet material consistency

**Version:** 0.23.0. **Status:** implemented, controlled synthetic tests only. Never infer AI image provenance from a BRDF mismatch.

## Scope and independently required inputs

The engine combines the already-tested P6-M01 Lambertian and P6-M02 single-scattering isotropic GGX/Smith/Schlick contributions. It explicitly requires a calibrated, linear RGB outgoing radiance measurement, an independently known incident illumination (perpendicular incident irradiance), surface normals, viewer/light unit directions, and material parameters `F0`, `roughness`, and lobe weights. Measured pixel values in gamma-encoded JPEG/PNG or tone-mapped render output **cannot** be substituted for calibrated radiance. Geometry is not inferred from an uncalibrated photograph.

### BRDF mixing and energy reasoning

Let `ws` be the specular lobe weight and `wm` the optional phenomenological multiple-scattering proxy weight. Set `wd=1-ws-wm`. All weights must be nonnegative and `ws+wm<=1`.

```text
f_total(wi,wo) = wd * rho_d / pi
               + ws * D_GGX(h) G_Smith(wi,wo) F_Schlick(wi,h) /
                      [4 * (n·wi) * (n·wo)]
               + wm * rho_proxy / pi

L_out = f_total * E_incident * max(0,n·wi) * visibility
```

The BRDF is reciprocal under the inputs' adopted Smith-GGX implementation, and the convex combination of passive BRDFs preserves nonnegativity, reciprocity and passivity. Note: the weights are **model mixing fractions**, not a derivation of the Fresnel-transmitted/subsurface scattering path of a real dielectric. This is an explicitly *simplified* passive BRDF, not a definitive physically accurate multi-layer BSDF.

`rho_proxy` is an energy-bounded **phenomenological diffuse proxy** only. It must **not** be described as a validated GGX multi-bounce transport solution (such as a calibrated multiple-scattering lookup-table or path-traced BSDF). An unknown multiple-scattering contribution is represented by `multiscattering_policy="unknown"`, causing `INDETERMINATE` even when a simple BRDF predicts a large residual. Only independently characterized proxy weights and albedo may be used in `bounded_diffuse_proxy` mode. Under `assumed_negligible` the engine tests that **assumption**, not that the material truly exhibits negligible multiple scattering.

Numerical directional-hemispherical energy checks reuse P6-M02's two-resolution quadrature and its near-delta-lobe abstention. In particular a low-roughness numerical integral by itself is never called global energy certification. For a given outgoing direction `wo`, the sampled reflectance is:

```text
rho_dh(wo) = wd * rho_d + ws * Integral_hemisphere f_GGX(wi,wo) cos(theta_i) dwi
             + wm * rho_proxy
```

Numerical evaluations do not prove this bound for every possible hemisphere direction. The convex weighting and individual lobe passivity are the structural guarantee under the chosen analytic model.

## Train / holdout and material-surface separation

Data contracts (`p6_m03_fixture.json` provides a complete example):

- `calibration_mode`: `known_material` or `fit_diffuse_albedo`.
- `materials`: mapping from `material_id` to `diffuse_albedo_rgb`, `roughness`, `f0_rgb`, `specular_weight`, `material_provenance`, and `multiscattering_policy`; optional `multiscatter_proxy_weight`, `multiscatter_proxy_albedo_rgb`, `multiscatter_proxy_provenance`.
- `incident_irradiance_rgb` and `light_provenance` must identify independently known lighting (synthetic ground truth is accepted *for synthetic tests only*).
- `samples`: unique IDs with disjoint `train` / `holdout` roles; `material_id`, `surface_id`; `normal_world`, `to_light_world`, `to_camera_world`; nonnegative `observed_radiance_rgb`; **positive** `sigma_radiance_rgb`; optional `visible_fraction`; `geometry_provenance`, `radiometry_provenance`.

In `fit_diffuse_albedo`, diffuse albedo is fitted by robust bounded least squares **using training samples only**, with known incident irradiance / F0 / roughness / weights. The input albedo is an unused placeholder in this mode. The approximate uncertainty is propagated to holdout RGB residuals; near-degenerate albedo observability and endpoint solutions abstain. The holdout test must include **at least two distinct surface IDs** belonging to the same declared material, so a single patch cannot silently substitute for cross-surface consistency. Training material may be a separate independent reference coupon. Multiple materials can be declared and analysed separately.

Predicted vs. observed linear RGB data are compared using maximum per-channel standardized residual `z`:

- `z <= 2.5`: `CONSISTENT` conditional on verified assumptions.
- `z >= 4.5`: `INCONSISTENT_UNDER_ASSUMPTIONS` conditional on verified assumptions.
- Between thresholds, unknown illumination, dubious geometry/radiometry, uncharacterized multiple scattering, too few samples or material mix ambiguity: `INDETERMINATE`.

The `NO_AI_ORIGIN_CONCLUSION` decision is constant: even a genuine mismatch does not certify AI generation.

## Commands

```powershell
python -m aiforensics demo-combined-material --out outputs/p6_m03_demo
python -m aiforensics demo-combined-material --known-material --proxy --out outputs/p6_m03_proxy_demo
python -m aiforensics analyze-combined-material --input outputs/p6_m03_demo/p6_m03_fixture.json --out outputs/p6_m03_recheck
python -m aiforensics audit-combined-energy --input outputs/p6_m03_demo/p6_m03_fixture.json --out outputs/p6_m03_energy_audit.json
python scripts/p6_combined_benchmark.py --trials 80 --out outputs/p6_m03_benchmark.json
python -m pytest -q
```

The module produces `p6_m03_report.json`, and the controlled demo also renders `p6_m03_holdout.png` when matplotlib is installed.

## Scientific limits and future work

Unmodeled factors: multi-bounce microfacet transport, anisotropic BRDFs, conductor complex IOR vs Schlick approximations, coatings, subsurface transport, polarized reflection, spatially varying material, multi-illuminant mixing, camera color calibration, tone curves, clipped highlights, indirect global illumination and shadows not declared in the input. Negative controls explicitly refuse to turn these missing assumptions into conclusive violations.

If the scientific scope expands, true multiple-scattering correction requires a separate physically derived, energy-audited BSDF implementation (e.g. directional-albedo compensation or unbiased microsurface transport). That is not claimed here.

**Bibliography (external, mathematical background only):**

- *Physically Based Rendering*, 3rd edition, Microfacet Models: https://pbr-book.org/3ed-2018/Reflection_Models/Microfacet_Models
- Dassault Systèmes Enterprise PBR Shading Model, multiple-scattering GGX discussion: https://github.com/DassaultSystemes-Technology/EnterprisePBRShadingModel/blob/master/spec-2022x.md.html
- MaterialX physically-based shading specification: https://github.com/AcademySoftwareFoundation/MaterialX/blob/main/documents/Specification/MaterialX.PBRSpec.md

All included experimental measurements are **synthetic same-family generator** tests; external real-photo/RAW material measurements and final Windows user acceptance are intentionally deferred to the final project phase.
