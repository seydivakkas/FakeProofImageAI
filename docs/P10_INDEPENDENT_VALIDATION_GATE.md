# P10 — Independent photographic, camera and Windows acceptance gate

**State: NOT STARTED.** This is a validation protocol, not evidence that a real-world acceptance test was performed.

## P10-A01 — Original image provenance and measurement plan
- Collect authorized original photographs with original bytes, SHA-256, camera/lens RAW where relevant, capture settings, tripod/scene geometry and written consent/usage rights.
- Preserve separate training/reference and independent holdout frames, capture/device/session identities, and a no-leakage manifest.
- Define ground truth through independent measurements, laser targets, known scene geometry / metrology with units and measured error/uncertainty.
- Record exclusions: demosaicing/JPEG/nonlinear images cannot be treated as RAW PRNU/DSNU identity references.
- Pre-register model-specific assumptions, eligible modules and fixed thresholds **before** opening holdouts.
- Do not treat a discrepancy as proof of AI origin.

## P10-A02 — Device and camera calibration
- Validate G01/G02/G04 separately: camera intrinsics K, lens distortion, calibration target, extrinsic references, reprojection train/holdout errors; never claim G02 three direction fits independently validate K.
- Independently validate optical / shadow / BRDF / sensor modules against instrumented references and measured noise/saturation constraints.
- Check precision of linkages: every source record must identify its image/camera calibration and reproduce the measurement. Reject unsupported auto source links.

## P10-A03 — Independent photo controls and error analysis
- Distinct *real* images under difficult conditions (reflections, shadows, backlit and multiple illumination, low-light, spatially correlated noise, compressed JPEG) with controlled labels and failure modes.
- Report false-alarm rates with uncertainty intervals, stratify by device/conditions, define abstention rates, ensure no duplicated correlated samples create fictional effective sample sizes.
- External reviewer examines uncertain cases and confidence statement; no AI-origin calibration without an independently validated purpose-designed identification study.

## P10-A04 — Real Windows 10/11 package and GUI
- Build signed/unsigned artifacts separately; verify installer/onedir, antivirus alerts and OS provenance.
- Execute installation/uninstallation, offline start, file loading, corrupted input, project reopening, cancellation, >1000 E03 record scrolling, focus/tab order, keyboard shortcuts, 100/125/150% DPI and 1366x768/1920x1080.
- Collect native Windows screenshots and accessibility observations, compare to agreed visual mocks and issue list. CI virtual-display screenshots do **not** close this criterion.
- Record performance/memory, dependency and licensing checks, executable hashes, reproducible build artifacts, and user acceptance signatures.

## Acceptance table

| Gate | Current status | Required closure |
|---|---|---|
| Synthetic regression + Ubuntu GUI screenshot | Previously executed per CI, recheck release | Published CI logs and checksums |
| Independent camera calibration | NOT PERFORMED | Original data, holdout and independent metrology |
| Real photos and error rates | NOT PERFORMED | Pre-registered test + external reviewer |
| Real Windows 10/11 installation | NOT PERFORMED | Native install, usability, DPI and keyboard logs |
| Mockup pixel/ergonomic acceptance | NOT ACCEPTED | User-approved native screenshot matrix |

**No implicit acceptance:** a passing CI check, demo or committed source file is not a physical validity certificate.
