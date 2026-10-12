# G02 independent real-camera evaluation protocol

## Status

**HOLD: no true real-camera measurements made yet.** This environment cannot retrieve the photographic binary assets. Unit tests exercise the validation implementation with synthetic images and known synthetic `K` only; they must not be represented as experimental findings from a camera.

## Target data

Use [York Urban Database](https://www.elderlab.yorku.ca/resources/york-urban-line-segment-database-information/), Denis, Elder & Estrada (ECCV 2008). The original dataset contains 102 real camera photographs, physically calibrated intrinsics and manual Manhattan direction annotations. A [public GitHub mirror](https://github.com/trocolit2/vanishing-point-detection/tree/master/resource/datasets/yorkurban) contains JPEGs and horizon/zenith arrays **but does not itself provide the independent camera K and all original line-direction annotations**; those must be extracted from the original source. Optionally fetch five mirror JPEGs with `python scripts/fetch_yorkurban.py --count 5` in a connected Windows environment. Do not treat this as having completed camera validation.

The original YorkUrbanDB `cameraParameters.mat` is documented in [YUD+](https://github.com/fkluger/yud_plus) as containing `focal`, `pixelSize` and `pp`; construct `K = [[focal/pixelSize,0,pp[0]],[0,focal/pixelSize,pp[1]],[0,0,1]]`. Verify image dimensions/rectification and annotate an **independent** train/holdout split for each of the three Manhattan world axes. Do NOT estimate independent K from the same 3 VP triplets you're evaluating (circularity).

## JSON contract

- `image`: JPEG filename under the same folder as JSON manifest, not arbitrary external path.
- `image_shape_hw`: `[height,width]` as verified from image file.
- `known_intrinsics_K`: independently measured 3×3 camera K; near-square pixels & zero skew required by current G02.
- `train_orthogonal_groups`: exactly 3 lists of segments, each `[x1,y1,x2,y2]`; at least 5 per group advisable.
- `holdout_orthogonal_groups`: 3 disjoint lists of lines, each with at least 2 segments; never used during calibration.
- `source`, `capture_and_calibration_provenance`: nonempty human-auditable citations to capture and camera calibration.

A dataset with finite VP at infinity or severe lens distortion may cause G02 to return `INDETERMINATE`; this is valid behavior, not a failed fake-image detection.

## Results

```powershell
python -m aiforensics validate-g02-real --input data/real/case.json --out outputs/g02_real
```

Reported: estimated K, reference K, focal absolute/relative error, principal point error, held-out line-to-VP median/RMSE for each independent direction, image SHA-256. The orthogonal 3D line-group labels are verified **externally**; these cannot be inferred from the three fitted models.

**Acceptance goal** (not yet attained): end-to-end evaluation over at least 20 distinct held-out real photographic frames with precommitted metrics and thresholds, per-frame image SHA256 and no train/test leakage. Thresholds must be established on development data without tuning on the final held-out photographs.
