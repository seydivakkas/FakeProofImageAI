# P1-G03 reproducible experiment log

Runtime source: previous v0.2 baseline copied forward, extended with `cross_ratio.py`, `real_validation.py`, new CLI commands and tests.

- `PYTHONPATH=src pytest -q`: 37 tests PASS (G01+G02 regression + new G03 & real-validator contract tests). All newly added real-validator fixture images are **synthetic**.
- `python scripts/g03_demo.py`: expected CR = 1.3333333333333335, measured CR = 1.3333333333333337, disjoint holdout RMSE = 4.0194366942304644e-14 px. Deterministic ideal pinhole projection, not field test.
- Genuine real-photo validation: NOT RUN (no downloadable York Urban original camera imagery and corresponding reference calibration/labeled lines available inside this execution environment).
- Original York Urban photo download support is implemented for user's networked system, *not executed successfully here*.
- Automatic tile-joint detection: NOT IMPLEMENTED. Coordinate markers are supplied externally.
- Separate Windows execution: NOT RUN.

Required independent result before physical inference acceptance: manifest with real image SHA-256, externally measured original-camera K, physical Manhattan line grouping split by train/holdout, heldout error distribution, calibration error on >=20 photos.
