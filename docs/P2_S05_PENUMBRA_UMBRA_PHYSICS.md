# P2-S05 — Umbra, Penumbra, Extended-Source Angular Size and Irradiance Edge Physics

**Version:** v0.10.0 | **Status:** synthetic mathematical regression tested; real-image validation **DEFERRED**.

## 1. What this module proves and does not prove

- Measures **one-dimensional, annotated** soft-shadow profiles in **linear relative irradiance** space.
- Fits a simplified geometric-optics model of a distant, uniform **disk** or **strip** light source occulted by a locally straight opaque edge.
- Under separately established metric scene scale, occluder–receiver separation and **near-normal, approximately parallel** illumination, estimates the source's **apparent angular diameter**.
- Compares *independent edge scans declared in advance to come from the same source*, including edges at **different blocker heights**. The common-source claim is a hypothesis, not independently proven.
- Models finite circular coaxial source/blocker/receiver geometry to distinguish full umbra and partial-shadow extents.
- **Never** infers AI provenance, physical source size and source distance separately, full 3D lighting from one 1D profile, or the existence of a full 2D umbra region from one scan.
- Does **not** automatically discover photo shadow boundaries or infer radiometric linearity from PNG/JPEG metadata.

## 2. Forward model: visible luminous disk fraction

Assumptions: locally straight infinitely long opaque knife-edge, planar locally diffuse receiver, distant uniform disk source with diameter much smaller than its distance, no significant specular highlights, interreflections, transmission, atmospheric scattering or lens-blur contamination; an input profile approximately proportional to received direct irradiance.

Let `u = (x - x0) / R` be signed projected distance from the geometric shadow boundary, scaled by **penumbra half-width** `R > 0`. The directly visible fraction of a uniform circular source is

\[
 F_\mathrm{disk}(u) = \begin{cases}
 0, & u \le -1 \\
 \frac12 + \frac{\arcsin(u)+u\sqrt{1-u^2}}{\pi}, & -1<u<1 \\
 1, & u\ge 1.
 \end{cases}
\]

For a uniform strip source (1D uniform projected emission),

\[
 F_\mathrm{strip}(u) = \max\left(0,\min\left(1, \frac{u+1}{2}\right)\right).
\]

Measured irradiance is approximated by

\[
 I(x)= I_\mathrm{dark} + (I_\mathrm{lit}-I_\mathrm{dark})F_\mathrm{shape}(u) + \epsilon(x).
\]

For a left-lit profile, reverse the sign of `u`. The dark level can be nonzero because ambient/indirect light may still arrive. **Dark plateau ≠ zero pixel value**.

## 3. Angular inversion (strong conditional contract)

Under near-normal **parallel**, distant-source rays with independent receiving-plane scale `s` [pixels/meter] and blocker height above the receiver `h` [meters]:

\[
 W_\mathrm{px}=2R_\mathrm{px},\qquad
 W_\mathrm{m} = \frac{W_\mathrm{px}}{s},\qquad
 \boxed{\beta=2\arctan\left(\frac{W_\mathrm{m}}{2h}\right)}.
\]

This yields **angular diameter** `β`, not emitter physical diameter or source distance. The close-to-normal approximation is essential: slanted shadows, anisotropic optical projection, changing receiver normals or non-parallel rays need a different Jacobian/geometric forward model. These cases must not be silently interpreted by this formula. Near-normal is **asserted in the manifest by an external independent geometry check**; S05 does not currently verify it automatically.

For an emitter of physical radius `a` at distance `d` from the blocker, in coaxial source/blocker/receiver planes, `tan(β/2)=a/d`; the penumbra width is `W=2ah/d`.

## 4. Umbra of a finite coaxial circular blocker

With circular emitter radius `a`, opaque circular blocker radius `b`, source-to-blocker separation `d` and blocker-to-receiver separation `h`, all measured along the common axis:

\[
 R_\mathrm{outer}=b\left(1+\frac{h}{d}\right)+a\frac{h}{d},\qquad
 R_\mathrm{inner}=b\left(1+\frac{h}{d}\right)-a\frac{h}{d}.
\]

If `R_inner > 0`, geometric full umbra occupies the central receiver disk of radius `R_inner`, and a partial-shadow ring extends to `R_outer`. If `R_inner ≤ 0`, the total umbra vanishes on this plane (an antumbral configuration may occur). This finite-source circular blocker model is a **separate** analytic geometry check: it is not automatically inverted from a single straight-edge profile.

## 5. Numerical fitting and decision logic

1. Validate monotone sample positions, finite irradiance in `[0,1]`, explicit `LINEAR_RELATIVE_IRRADIANCE`, source shape and lit orientation.
2. Initialize plateau levels, midpoint and 10–90% transition width; fit dark, light, center and positive half-width using SciPy robust nonlinear least squares (`soft_l1`).
3. Abstain on insufficient contrast, inadequate umbra/lit plateaus, poor fit, unresolved sub-pixel edge or fit width at parameter bounds.
4. If and only if `metric_geometry.verified=true` with `model=NEAR_NORMAL_PARALLEL_RAYS` and positive independently known pixel scale and blocker height, estimate conditional angular diameter. Abstain from angle reporting when camera PSF is comparable to the fitted penumbra.
5. Require at least **three** independently annotated measurable edges and explicit `declared_common_source=true` to test inter-edge angular consistency.
6. Report `CONSISTENT_UNDER_ASSUMPTIONS`, `INCONSISTENT_UNDER_ASSUMPTIONS` or `INDETERMINATE`. The relative tolerance is currently a **heuristic engineering gate**, **not** a calibrated p-value or AI-origin posterior.

The optional parametric Monte Carlo interval assumes independent Gaussian pixel noise with spread inferred from residual RMSE, so it is a **conditional simulation interval**, **not** a coverage-validated 90% confidence interval. Residual correlation, source heterogeneity and PSF misspecification are not removed by Monte Carlo.

## 6. Manifest schema

```json
{
  "schema": "P2_S05_EDGE_PROFILES_V1",
  "declared_common_source": true,
  "edges": [{
    "id": "edge_floor_01",
    "radiometric_space": "LINEAR_RELATIVE_IRRADIANCE",
    "source_shape": "UNIFORM_DISK",
    "light_side": "right",
    "x_px": [-20, -19, -18],
    "linear_irradiance": [0.1, 0.1, 0.1],
    "metric_geometry": {
      "model": "NEAR_NORMAL_PARALLEL_RAYS",
      "verified": true,
      "receiver_pixels_per_meter": 125.0,
      "occluder_receiver_separation_m": 1.8,
      "optical_psf_sigma_px": 0.0
    }
  }]
}
```

(The abbreviated arrays above are **not sufficient** for a fit. At least 35 distinct positions with both plateaus are needed.)

### Annotated linear-image transects

For a calibrated **linear** `.npy` image array of size `H×W` or `H×W×3` and a separate manifest:

```json
{
  "schema":"P2_S05_TRANSECTS_V1",
  "radiometric_space":"LINEAR_RELATIVE_IRRADIANCE",
  "declared_common_source":false,
  "transects":[{
    "id":"profile_1",
    "start_xy":[80,100],
    "end_xy":[280,100],
    "sample_count":161,
    "source_shape":"UNIFORM_DISK",
    "light_side":"right"
  }]
}
```

The transect should cross the shadow boundary approximately **perpendicularly**. If camera or receiver-plane geometry is not independently verified, `metric_geometry` must be omitted and only descriptive fitted widths can be reported. A raw JPEG/PNG is not a verified linear irradiance array; do not merely rename or cast it.

## 7. CLI usage

```powershell
python -m aiforensics demo-penumbra --out outputs/p2_s05_demo
python -m aiforensics analyze-penumbra --input outputs/p2_s05_demo/p2_s05_fixture.json --out outputs/p2_s05_check
python -m aiforensics analyze-penumbra --input edge_manifest.json --bootstrap 64 --out outputs/custom
python -m aiforensics sample-penumbra --npy measured_linear.npy --transects transects.json --out outputs/measured_edges.json
python -m aiforensics analyze-penumbra --input outputs/measured_edges.json --out outputs/measured_analysis
python scripts/p2_penumbra_benchmark.py --trials 80 --out outputs/p2_s05_benchmark.json
```

Outputs: `p2_s05_report.json` containing all per-profile estimated quantities, bounds and evidence, and `p2_s05_profiles.png` showing raw irradiance profiles (cyan), predicted geometric models (green), and theoretical penumbra bounds (orange).

## 8. Relationship with previous modules

- **S01/S02** yield projected light convergence families from annotated shadow correspondences. They **do not** supply irradiance scans or validate a disk emitter.
- **S03** yields calibrated 3D light solutions if depth and height constraints exist. Those results may externally support metric distance assumptions, but S05 requires its own explicit verified scan geometry.
- **S04** estimates solar azimuth/elevation when an ENU scene and shadow correspondences are available. A guessed solar elevation cannot replace S05's independent near-normal-incidence validation.
- Fusion with S02–S04 is a later development stage. **Do not** sum correlated evidence as if it were independent.

## 9. Acceptance criteria and unresolved work

**Synthetic unit and stress:** analytic source visibility, disk/strip profiles, inverse angle, known-h 3D scale relation, finite-source umbra, rejection of low contrast/sub-resolution, mixed-source incompatibility, repeatability, pipeline CLI and deterministic benchmark. Track every non-measured case and do not delete it from statistics.

**Not yet done:** automatic 2D shadow segmentation, scene-independent color/material correction, camera PSF estimation, non-normal/general area-light inverse rendering, empirical confidence calibration, user Windows acceptance and real-image field study. All **real data** acceptance intentionally deferred until the overall P0–P8 project development is finished.

## 10. Independent physics reference

- NVIDIA, *Percentage-Closer Soft Shadows*, SIGGRAPH 2005: finite light-source/blocker/receiver distance model, `w_penumbra ~ source_width * blocker-receiver / light-blocker` (parallel plane approximation).
  https://download.nvidia.com/developer/SDK/Individual_Samples/MEDIA/docPix/docs/PCSS.pdf
- Eric Chan, MIT thesis: area-source shadow, visibility function, umbra/penumbra and blocker–receiver distance dependency.
  https://people.csail.mit.edu/ericchan/papers/mthesis/ericchan_mthesis.pdf
