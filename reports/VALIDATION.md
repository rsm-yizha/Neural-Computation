# EDF to BIDS validation

Checked: 2026-09-15T04:20:22.088308+00:00

## Round-trip results

| Run | Task | EEG channels | Hz | Samples/channel | Seconds | Events source / BIDS | Max signal diff (V) | Max onset diff (s) | Max duration diff (s) |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|
| 01 | eyesopen | 64 | 160.0 | 9760 | 61.0 | 1 / 1 | 0.0 | 0.0 | 0.0 |
| 02 | eyesclosed | 64 | 160.0 | 9760 | 61.0 | 1 / 1 | 0.0 | 0.0 | 0.0 |
| 03 | execution | 64 | 160.0 | 20000 | 125.0 | 30 / 30 | 0.0 | 0.0 | 0.0 |
| 04 | imagery | 64 | 160.0 | 20000 | 125.0 | 30 / 30 | 0.0 | 0.0 | 0.0 |

All samples were compared exactly, in their original channel order. Both direct EDF and BIDS-aware reads were checked. No filtering, resampling, or re-referencing was performed.
The output EDF differs from the source only in the fixed-width EEG label slots; its calibration, annotations, and signal bytes are unchanged. Source hashes were checked before and after conversion.

## Validator

Pinned validator: 1.15.0; exit code: 0; error groups: 0; warning groups: 1.
- NO_AUTHORS: The Authors field of dataset_description.json should contain an array of fields - with one author per field. This was triggered because there are no authors, which will make DOI registration from dataset metadata impossible.
  Disposition: No authorship is assigned to the learner for the original recordings; original creators and citation are identified in README and ReferencesAndLinks.

## Decisions and limitations

- Source: https://physionet.org/content/eegmmidb/1.0.0/ (S001, R01-R04). This is a local practice subset, not a NEMAR release.
- Channel labels: remove trailing dots and look up canonical case in MNE colin27_1020. All 64 labels map uniquely. Template coordinates are not assigned or represented as measured positions.
- MNE-BIDS copies EDF without applying in-memory renames. The script updates only the destination EDF label slots and verifies every other byte.
- Events: the original T codes remain inside EDF and in events.tsv original_code. trial_type distinguishes execution and imagery; value retains the numeric suffix 0/1/2. Onsets and durations are preserved.
- Baselines are distinct eyesopen/eyesclosed tasks; their T0 annotations remain rest.
- Durations come from samples / sampling rate: 61 s and 125 s, not the rounded protocol durations. Annotation coverage need not extend to the recording end; no events are stretched or synthesized.
- PowerLineFrequency=60 is inferred from the US acquisition background and US mains frequency; EDF does not supply it. Setting this field does not filter the signal.
- EEGReference and EEGGround are n/a: the inspected source documentation and EDF header do not specify them. No average reference is imposed.
- MNE-BIDS writes the equivalent microvolt spelling µV; we normalize it to the EDF spelling uV. EDF units are uV; MNE reads them as V. channels.tsv retains uV for the EDF storage. No extra scaling is applied.
- MNE-BIDS uses the final sample timestamp for RecordingDuration (60.99375 s or 124.99375 s). We explicitly use the EDF record duration, samples / Hz (61 s or 125 s). The difference is one sample interval; no sample is added or removed.
- channels.tsv status=good means no source bad-channel flag, not successful signal-quality assessment; status_description states not assessed.
- EDF prefilter text is HP:0Hz LP:0Hz N:0Hz. Treat it as insufficient to establish acquisition filter settings; HardwareFilters, SoftwareFilters, and channel cutoff values are n/a. The converter itself applies no filters.
- Hardware manufacturer is n/a. BCI2000 is identified by the source as the acquisition system, not inferred to be the amplifier manufacturer.
- Existing public recording timestamps are retained; the converter does not claim to anonymize the source.

## Runtime warnings

None.

## Reproduce

```sh
python convert.py
python convert.py --verify-only
python convert.py --output bids-repeat
```

Existing nonempty output directories are refused. Alternate output reports are stored beside that output in <output-name>-validation/. Full numeric evidence and hashes: validation.json. Raw validator output: bids-validator.json.
