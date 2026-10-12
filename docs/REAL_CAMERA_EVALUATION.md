# G02 real-camera verification — acceptance remains HOLD

As of this revision, no independent real calibrated camera data have been run in this environment. The test harness has been implemented, but **all passing end-to-end numerical tests use controlled synthetic line observations**, not actual photographic measurements.

Recommended source: [York Urban Line Segment Database, York University](https://www.elderlab.yorku.ca/resources/york-urban-line-segment-database-information/), 102 calibrated 640 × 480 photos, ground truth line groups and original calibration. The public [YUD+ reference loader](https://github.com/fkluger/yud_plus/blob/master/yud.py) shows original calibration field mapping: `focal`, `pixelSize`, `pp`, yielding `K=[[focal/pixelSize,0,pp0],[0,focal/pixelSize,pp1],[0,0,1]]`. The JPEG-only repository mirror **lacks calibration and sufficient independent per-direction line labels**. It is not a substitute for the original dataset.

When data is available: (1) record official archive provenance and actual image SHA-256, (2) verify camera dimensions, focal units and whether images were undistorted, (3) select 3 separately validated orthogonal line groups, each split into calibration and disjoint test lines, (4) compute 3 vanishing points using G01 only on train lines, (5) calibrate K and R using G02, (6) compare K to externally calibrated camera K and report test-only line-to-VP errors for each direction, (7) measure distributions on the precommitted held-out subset with no threshold tuning. Additional physical scene labels must be verified rather than inferred from arbitrary triplets of vanishing points.

Run per-case command:

```powershell
python -m aiforensics validate-g02-real --input data/real/sample.json --out outputs/g02_case
```

Or several independent case manifests:

```powershell
python -m aiforensics validate-g02-batch --inputs data/real/case1.json data/real/case2.json --out outputs/g02_batch
```

The batch endpoint requires an explicit `capture_type: real_camera` declaration. It supports optional `image_sha256` validation and reports `NOT_MEASURED` when no case is processed successfully; a declaration alone is **not cryptographic provenance proof**. Existing `g02_real_case_template.json` describes the required camera and annotation fields.

No publicly reproducible real-photo calibration error, FPR or TPR has been established yet. The software must not be described as field-validated until this protocol is executed.
