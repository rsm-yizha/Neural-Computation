# Repository preparation check

On September 15, 2026, the repository version was copied into a new directory and tested on mini using the existing Python 3.14.6 environment.

- All four source EDF files were downloaded afresh from PhysioNet and matched the pinned SHA-256 hashes.
- The updated converter found bunx through PATH, created a fresh BIDS output, and wrote reports into run-reports/.
- All four signal comparisons returned a maximum difference of 0 V; all 62 event onsets and durations were preserved.
- BIDS validator 1.15.0 returned zero errors and the documented NO_AUTHORS warning.
- All ten tests passed: three download-integrity tests, six conversion-corruption tests, and one normal-data control.

Commands executed in that new directory, using the existing interpreter:

```sh
python -B download_data.py
python -B convert.py
python -B -m unittest -v test_download_data test_verify
```

A fresh installation of the pinned dependencies and execution on other operating systems were not part of this check.
