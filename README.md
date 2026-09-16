# EEG to BIDS Curation

A guided, AI-assisted data-curation work sample: convert four public PhysioNet EEG Motor Movement/Imagery recordings to Brain Imaging Data Structure (BIDS), preserve the recorded signals and event timing, and document the decisions that a format validator cannot establish.

## Demonstrated results

The [verification report](reports/VALIDATION.md) records the original run:

| Check | Result |
|---|---|
| Scope | One participant, four recordings, 64 EEG channels each |
| Signals | Exact equality after direct EDF and BIDS-aware readback; maximum difference 0 V |
| Events | All 62 annotation onsets and durations preserved |
| Structure | BIDS validator 1.15.0: 0 errors, 1 documented `NO_AUTHORS` warning |
| Fault detection | Six corruption cases rejected; unmodified control accepted |
| Repeatability | All 25 generated BIDS files byte-identical in a fresh repeat |

This is a small, same-source practice subset. It does not demonstrate general conversion of arbitrary laboratory formats, signal-quality assessment, or a completed NEMAR submission.

A [fresh-directory packaging check](reports/PACKAGING_CHECK.md) also passed the full download and conversion flow plus all ten tests, using the existing tested Python environment.

## Data and attribution

Source: [PhysioNet EEG Motor Movement/Imagery Dataset 1.0.0](https://physionet.org/content/eegmmidb/1.0.0/), subject S001, runs R01-R04.

- R01: eyes-open baseline; R02: eyes-closed baseline.
- R03: actual left/right fist movement; R04: imagined left/right fist movement.
- Original dataset citation: Schalk, G. (2009). EEG Motor Movement/Imagery Dataset (version 1.0.0). [DOI: 10.13026/C28G6P](https://doi.org/10.13026/C28G6P).
- Original publication: Schalk et al. (2004). BCI2000: A General-Purpose Brain-Computer Interface (BCI) System. IEEE Transactions on Biomedical Engineering, 51(6), 1034-1043.
- Dataset license: [Open Data Commons Attribution License 1.0](https://opendatacommons.org/licenses/by/1-0/). This license concerns the source dataset; no ownership of the original recordings is claimed.

Raw and converted EEG recordings are excluded from this repository. `download_data.py` retrieves only the four source files and checks their pinned SHA-256 hashes before saving them.

## Reproduce

The original execution used Python 3.14.6, MNE 1.13.0, MNE-BIDS 0.19.0 and NumPy 2.5.3 on macOS. `requirements.txt` captures that installed Python environment. Other Python versions and operating systems have not been verified.

Install Python 3.14 and [Bun](https://bun.sh/docs/installation), with `python3.14` and `bunx` available on PATH. From the repository directory:

```sh
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python download_data.py
python convert.py
python -m unittest -v test_download_data test_verify
```

The converter invokes the pinned validator via `bunx --bun bids-validator@1.15.0`; the first invocation may download it. Conversion writes `bids/` and fresh evidence under `run-reports/`. It refuses an existing nonempty output directory.

```sh
python convert.py --verify-only
python convert.py --output bids-repeat
```

The alternate command requires an unused output directory and writes its report to `bids-repeat-validation/`.

## Decisions worth inspecting

1. **Names and bytes:** `raw.rename_channels()` updates the in-memory labels; MNE-BIDS copies the source EDF. The converter changes only the output EDF's fixed-width label slots, then verifies all remaining bytes and every signal sample.
2. **Event meaning:** `T1` means actual left-fist movement in R03 and imagined left-fist movement in R04. `events.tsv` records the task-specific `trial_type` and retains `original_code` for traceability.
3. **Missing information:** reference, ground, acquisition filters and hardware manufacturer remain `n/a`. The 60 Hz power-line value is explicitly an inference from US acquisition context.
4. **Units and duration:** EDF microvolts and MNE's in-memory volts are handled without extra scaling. Recording duration uses sample count / sampling frequency; event durations are not stretched to fill the recording.
5. **Evidence boundaries:** validator success does not establish correct experimental interpretation. The `NO_AUTHORS` warning is documented for this practice subset; NEMAR publication has additional requirements, including named authors and an ethics statement.

See [NEMAR submission standards](https://docs.nemar.org/policies/submission-standards/) and the [BIDS EEG specification](https://bids-specification.readthedocs.io/en/stable/modality-specific-files/electroencephalography.html).

## Files

- `convert.py`: conversion, readback checks, validator invocation and report generation.
- `test_verify.py`: six real corruption cases plus a normal-data control using temporary copies.
- `download_data.py`, `source_hashes.json`: bounded, checksum-verified source acquisition.
- `test_download_data.py`: download integrity, cache reuse and overwrite-protection tests.
- `reports/`: observed results from the original run, with local paths replaced by placeholders.
- [AI_USAGE.md](AI_USAGE.md): scope of AI assistance and the learner's contribution.
