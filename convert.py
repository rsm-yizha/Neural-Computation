#!/usr/bin/env python3
"""Convert the four S001 EDF recordings to BIDS, then verify every sample.

Run with python convert.py. Existing nonempty output is refused.
Use --output bids-repeat for a fresh repeat, or --verify-only to recheck output.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import sys
import warnings

import mne
import mne_bids
import numpy as np

ROOT = Path(__file__).resolve().parent
SOURCE_URL = 'https://physionet.org/content/eegmmidb/1.0.0/'
TASKS = {'01': 'eyesopen', '02': 'eyesclosed', '03': 'execution', '04': 'imagery'}
# Codes are interpreted in the context of the run, never globally.
EVENT_MAPPING = {
    '01': {'T0': 'rest'},
    '02': {'T0': 'rest'},
    '03': {'T0': 'rest', 'T1': 'execute_left_fist', 'T2': 'execute_right_fist'},
    '04': {'T0': 'rest', 'T1': 'imagine_left_fist', 'T2': 'imagine_right_fist'},
}
TASK_DESCRIPTIONS = {
    '01': 'Resting baseline with eyes open.',
    '02': 'Resting baseline with eyes closed.',
    '03': 'Actual opening and closing of the left or right fist, alternating with rest.',
    '04': 'Imagined opening and closing of the left or right fist, alternating with rest.',
}
TIME_ATOL = 1e-9  # Seconds; much smaller than one 160 Hz sample (0.00625 s).


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def read_tsv(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream, delimiter='\t'))


def write_tsv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter='\t', lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def source_path(run):
    return ROOT / 'raw' / 'S001' / f'S001R{run}.edf'


def bids_path(output, run):
    return mne_bids.BIDSPath(subject='001', task=TASKS[run], run=run,
                             datatype='eeg', suffix='eeg', extension='.edf', root=output)


def sidecar(path, suffix, extension):
    return path.copy().update(suffix=suffix, extension=extension).fpath


def channel_mapping(names):
    # This template provides canonical labels only; no template coordinates are assigned.
    montage = mne.channels.make_standard_montage('colin27_1020')
    canonical = {name.lower(): name for name in montage.ch_names}
    require(len(canonical) == len(montage.ch_names), 'Ambiguous template labels')
    mapping = {old: canonical[old.rstrip('.').lower()] for old in names}
    require(len(mapping) == len(names), 'Duplicate source names')
    require(len(set(mapping.values())) == len(names), 'Canonical label collision')
    return mapping


def renamed_edf_bytes(source, mapping):
    """Change only the 16-byte signal label slots in an EDF copy.

    EDF has a 256-byte fixed header, followed by 16 bytes per signal label.
    Annotation labels and all sample/calibration/recording bytes are untouched.
    """
    original = source.read_bytes()
    n_signals = int(original[252:256])
    require(int(original[184:192]) == 256 + n_signals * 256, 'Unexpected EDF header layout')
    result = bytearray(original)
    found = []
    for i in range(n_signals):
        start = 256 + 16 * i
        name = original[start:start + 16].decode('ascii').strip()
        if name == 'EDF Annotations':
            continue
        replacement = mapping[name].encode('ascii')
        require(len(replacement) <= 16, 'EDF label exceeds 16 bytes')
        result[start:start + 16] = replacement.ljust(16, b' ')
        found.append(name)
    require(found == list(mapping), 'EDF signal order differs from MNE channel order')
    return bytes(result)


def convert_run(output, run):
    raw = mne.io.read_raw_edf(source_path(run), preload=False, verbose='ERROR')
    mapping = channel_mapping(raw.ch_names)
    original_codes = list(raw.annotations.description)
    raw.rename_channels(mapping)
    raw.info['line_freq'] = 60  # Inferred from US acquisition location, not stored in EDF.
    raw.annotations.rename(EVENT_MAPPING[run])
    event_id = {label: int(code[1:]) for code, label in EVENT_MAPPING[run].items()}
    path = bids_path(output, run)
    mne_bids.write_raw_bids(raw, path, event_id=event_id, overwrite=False,
                            readme=False, verbose='WARNING')
    # The writer copies the original EDF, even after raw.rename_channels().
    require(path.fpath.read_bytes() == source_path(run).read_bytes(), 'Writer unexpectedly changed EDF bytes')
    path.fpath.write_bytes(renamed_edf_bytes(source_path(run), mapping))
    event_file = sidecar(path, 'events', '.tsv')
    rows = read_tsv(event_file)
    require(len(rows) == len(original_codes), 'Writer changed event count')
    for row, code, onset, duration in zip(rows, original_codes, raw.annotations.onset, raw.annotations.duration):
        require(row['trial_type'] == EVENT_MAPPING[run][code], 'Writer reordered event labels')
        require(abs(float(row['onset']) - onset) <= TIME_ATOL, 'Writer changed event onset')
        require(abs(float(row['duration']) - duration) <= TIME_ATOL, 'Writer changed event duration')
        row['original_code'] = code
    write_tsv(event_file, rows)
    event_json = sidecar(path, 'events', '.json')
    metadata = json.loads(event_json.read_text())
    metadata['original_code'] = {'Description': 'Unmodified EDF annotation code; interpret together with run/task.',
                                 'Levels': EVENT_MAPPING[run]}
    metadata['trial_type'] = {'Description': 'Run-specific interpretation of the source annotation.',
                             'Levels': {v: v.replace('_', ' ') for v in EVENT_MAPPING[run].values()}}
    write_json(event_json, metadata)
    channel_file = sidecar(path, 'channels', '.tsv')
    channels = read_tsv(channel_file)
    for row in channels:
        require(row['units'] in ('uV', 'µV', 'μV'), 'Unexpected EDF channel unit')
        row['units'] = 'uV'
        row['low_cutoff'] = 'n/a'
        row['high_cutoff'] = 'n/a'
        row['status_description'] = 'Not assessed; source supplies no bad-channel labels.'
    write_tsv(channel_file, channels)
    eeg_json = sidecar(path, 'eeg', '.json')
    metadata = json.loads(eeg_json.read_text())
    metadata.update(EEGReference='n/a', EEGGround='n/a', PowerLineFrequency=60,
                    EEGPlacementScheme='10-10', TaskDescription=TASK_DESCRIPTIONS[run],
                    Manufacturer='n/a', SoftwareFilters='n/a', HardwareFilters='n/a',
                    RecordingDuration=raw.n_times/raw.info['sfreq'])
    write_json(eeg_json, metadata)


def verify_run(output, run):
    """Compare fresh source reads, direct EDF reads, and BIDS-aware reads."""
    src = source_path(run)
    path = bids_path(output, run)
    original = mne.io.read_raw_edf(src, preload=True, verbose='ERROR')
    direct = mne.io.read_raw_edf(path.fpath, preload=True, verbose='ERROR')
    restored = mne_bids.read_raw_bids(path, extra_params={'preload': True}, verbose='WARNING')
    mapping = channel_mapping(original.ch_names)
    expected_names = list(mapping.values())
    for kind, actual in [('EDF', direct), ('BIDS', restored)]:
        require(actual.ch_names == expected_names, f'{run}: {kind} channel names/order changed')
        require(actual.n_times == original.n_times, f'{run}: {kind} sample count changed')
        require(actual.info['sfreq'] == original.info['sfreq'], f'{run}: {kind} sampling rate changed')
        require(actual.get_channel_types() == original.get_channel_types(), f'{run}: {kind} channel types changed')
        require(np.array_equal(actual.get_data(), original.get_data()), f'{run}: {kind} signal samples changed')
    # This also checks calibration, EDF annotations, and all bytes outside label slots.
    require(path.fpath.read_bytes() == renamed_edf_bytes(src, mapping), f'{run}: unexpected EDF byte changes')
    np.testing.assert_array_equal(direct.annotations.description, original.annotations.description)
    np.testing.assert_allclose(direct.annotations.onset, original.annotations.onset, rtol=0, atol=TIME_ATOL)
    np.testing.assert_allclose(direct.annotations.duration, original.annotations.duration, rtol=0, atol=TIME_ATOL)
    rows = read_tsv(sidecar(path, 'events', '.tsv'))
    require(len(rows) == len(original.annotations) == len(restored.annotations), f'{run}: event count changed')
    expected_labels = [EVENT_MAPPING[run][code] for code in original.annotations.description]
    require([row['trial_type'] for row in rows] == expected_labels, f'{run}: event semantics changed')
    require([row['original_code'] for row in rows] == list(original.annotations.description), f'{run}: original codes changed')
    require([int(row['value']) for row in rows] == [int(code[1:]) for code in original.annotations.description], f'{run}: event values changed')
    expected_samples = original.time_as_index(original.annotations.onset, use_rounding=True)
    require([int(row['sample']) for row in rows] == list(expected_samples), f'{run}: event sample indices changed')
    np.testing.assert_array_equal(restored.annotations.description, expected_labels)
    onset_error = duration_error = 0.0
    for field in ('onset', 'duration'):
        expected = getattr(original.annotations, field)
        stored = np.array([float(row[field]) for row in rows])
        reread = getattr(restored.annotations, field)
        np.testing.assert_allclose(stored, expected, rtol=0, atol=TIME_ATOL)
        np.testing.assert_allclose(reread, expected, rtol=0, atol=TIME_ATOL)
        error = float(max(np.max(np.abs(stored-expected)), np.max(np.abs(reread-expected))))
        if field == 'onset':
            onset_error = error
        else:
            duration_error = error
    channels = read_tsv(sidecar(path, 'channels', '.tsv'))
    require([r['name'] for r in channels] == expected_names, f'{run}: channels.tsv names/order mismatch')
    require(all(r['units'] == 'uV' and r['type'] == 'EEG' for r in channels), f'{run}: units/types mismatch')
    metadata = json.loads(sidecar(path, 'eeg', '.json').read_text())
    require(metadata['EEGReference'] == 'n/a', f'{run}: undocumented reference')
    require(metadata['PowerLineFrequency'] == 60 == restored.info['line_freq'], f'{run}: line frequency mismatch')
    require(metadata['SamplingFrequency'] == original.info['sfreq'], f'{run}: JSON sample rate mismatch')
    duration = original.n_times / original.info['sfreq']
    require(abs(metadata['RecordingDuration'] - duration) <= TIME_ATOL, f'{run}: JSON duration mismatch')
    return {'run': run, 'task': TASKS[run], 'channels': len(expected_names), 'sfreq_hz': original.info['sfreq'],
            'samples_per_channel': int(original.n_times), 'duration_s': duration,
            'events_source': len(original.annotations), 'events_bids': len(restored.annotations),
            'event_counts': dict(Counter(original.annotations.description)),
            'max_signal_diff_v': float(np.max(np.abs(original.get_data()-restored.get_data()))),
            'max_onset_diff_s': onset_error, 'max_duration_diff_s': duration_error,
            'annotation_end_s': float(np.max(original.annotations.onset + original.annotations.duration)),
            'only_edf_labels_changed': True, 'source_sha256': sha256(src), 'output_sha256': sha256(path.fpath)}


def run_validator(output, report_dir):
    bunx = shutil.which('bunx')
    if bunx is None:
        raise RuntimeError('bunx is not on PATH. Install Bun and add its bin directory to PATH; see README.md.')
    command = [bunx, '--bun', 'bids-validator@1.15.0', str(output), '--json']
    result = subprocess.run(command, text=True, capture_output=True, timeout=180)
    (report_dir/'bids-validator.json').write_text(result.stdout)
    (report_dir/'bids-validator.stderr.txt').write_text(result.stderr)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    payload = json.loads(result.stdout)
    issues = payload['issues']
    return {'command': command, 'returncode': result.returncode,
            'errors': issues.get('errors', []), 'warnings': issues.get('warnings', [])}


def make_report(report_dir, output, results, validator, caught):
    evidence = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'output': str(output),
                'python': sys.version, 'mne': mne.__version__, 'mne_bids': mne_bids.__version__,
                'numpy': np.__version__, 'runs': results, 'validator': validator,
                'python_warnings': sorted(set(str(w.message) for w in caught))}
    write_json(report_dir/'validation.json', evidence)
    lines = ['# EDF to BIDS validation', '', f"Checked: {evidence['checked_at_utc']}", '',
             '## Round-trip results', '',
             '| Run | Task | EEG channels | Hz | Samples/channel | Seconds | Events source / BIDS | Max signal diff (V) | Max onset diff (s) | Max duration diff (s) |',
             '|---|---|---:|---:|---:|---:|---|---:|---:|---:|']
    for r in results:
        lines.append(f"| {r['run']} | {r['task']} | {r['channels']} | {r['sfreq_hz']} | {r['samples_per_channel']} | {r['duration_s']} | {r['events_source']} / {r['events_bids']} | {r['max_signal_diff_v']} | {r['max_onset_diff_s']} | {r['max_duration_diff_s']} |")
    lines += ['', 'All samples were compared exactly, in their original channel order. Both direct EDF and BIDS-aware reads were checked. No filtering, resampling, or re-referencing was performed.',
              'The output EDF differs from the source only in the fixed-width EEG label slots; its calibration, annotations, and signal bytes are unchanged. Source hashes were checked before and after conversion.',
              '', '## Validator', '', f"Pinned validator: 1.15.0; exit code: {validator['returncode']}; error groups: {len(validator['errors'])}; warning groups: {len(validator['warnings'])}."]
    warning_reasons = {
        'NO_AUTHORS': 'No authorship is assigned to the learner for the original recordings; original creators and citation are identified in README and ReferencesAndLinks.',
        'README_FILE_MISSING': 'Unexpected: a README is intended to be generated; investigate.',
        'TOO_FEW_AUTHORS': 'This is a one-person learning conversion, with original dataset attribution recorded separately.',
    }
    for item in validator['errors'] + validator['warnings']:
        key = item.get('key', str(item.get('code')))
        lines += [f"- {key}: {item.get('reason', '')}", f"  Disposition: {warning_reasons.get(key, 'Review the full validator JSON; no justification has been assumed.')}"]
    lines += ['', '## Decisions and limitations', '',
              '- Source: '+SOURCE_URL+' (S001, R01-R04). This is a local practice subset, not a NEMAR release.',
              '- Channel labels: remove trailing dots and look up canonical case in MNE colin27_1020. All 64 labels map uniquely. Template coordinates are not assigned or represented as measured positions.',
              '- MNE-BIDS copies EDF without applying in-memory renames. The script updates only the destination EDF label slots and verifies every other byte.',
              '- Events: the original T codes remain inside EDF and in events.tsv original_code. trial_type distinguishes execution and imagery; value retains the numeric suffix 0/1/2. Onsets and durations are preserved.',
              '- Baselines are distinct eyesopen/eyesclosed tasks; their T0 annotations remain rest.',
              '- Durations come from samples / sampling rate: 61 s and 125 s, not the rounded protocol durations. Annotation coverage need not extend to the recording end; no events are stretched or synthesized.',
              '- PowerLineFrequency=60 is inferred from the US acquisition background and US mains frequency; EDF does not supply it. Setting this field does not filter the signal.',
              '- EEGReference and EEGGround are n/a: the inspected source documentation and EDF header do not specify them. No average reference is imposed.',
              '- MNE-BIDS writes the equivalent microvolt spelling µV; we normalize it to the EDF spelling uV. EDF units are uV; MNE reads them as V. channels.tsv retains uV for the EDF storage. No extra scaling is applied.',
              '- MNE-BIDS uses the final sample timestamp for RecordingDuration (60.99375 s or 124.99375 s). We explicitly use the EDF record duration, samples / Hz (61 s or 125 s). The difference is one sample interval; no sample is added or removed.',
              '- channels.tsv status=good means no source bad-channel flag, not successful signal-quality assessment; status_description states not assessed.',
              '- EDF prefilter text is HP:0Hz LP:0Hz N:0Hz. Treat it as insufficient to establish acquisition filter settings; HardwareFilters, SoftwareFilters, and channel cutoff values are n/a. The converter itself applies no filters.',
              '- Hardware manufacturer is n/a. BCI2000 is identified by the source as the acquisition system, not inferred to be the amplifier manufacturer.',
              '- Existing public recording timestamps are retained; the converter does not claim to anonymize the source.',
              '', '## Runtime warnings', '']
    lines += ['- '+w for w in evidence['python_warnings']] or ['None.']
    lines += ['', '## Reproduce', '', '```sh', 'python convert.py', 'python convert.py --verify-only', 'python convert.py --output bids-repeat', '```', '',
              'Existing nonempty output directories are refused. Alternate output reports are stored beside that output in <output-name>-validation/. Full numeric evidence and hashes: validation.json. Raw validator output: bids-validator.json.']
    (report_dir/'VALIDATION.md').write_text('\n'.join(lines)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'bids')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    require(output != ROOT and ROOT/'raw' not in [output, *output.parents], 'Output must not overwrite project/source')
    report_dir = ROOT/'run-reports' if output == ROOT/'bids' else output.parent/(output.name+'-validation')
    report_dir.mkdir(parents=True, exist_ok=True)
    before = {run: sha256(source_path(run)) for run in TASKS}
    if not args.verify_only:
        require(not output.exists() or not any(output.iterdir()), 'Output is nonempty; use --verify-only or a fresh --output')
        output.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        if not args.verify_only:
            for run in TASKS:
                convert_run(output, run)
            write_json(output/'dataset_description.json', {
                'Name': 'PhysioNet EEGMMIDB S001 four-run BIDS practice subset', 'BIDSVersion': '1.8.0',
                'DatasetType': 'raw', 'License': 'ODC-By-1.0',
                'ReferencesAndLinks': [SOURCE_URL, 'https://doi.org/10.13026/C28G6P'],
                'SourceDatasets': [{'DOI': '10.13026/C28G6P', 'Version': '1.0.0', 'URL': SOURCE_URL}],
            })
            (output/'README').write_text('''Local learning conversion of PhysioNet EEG Motor Movement/Imagery Dataset, S001 R01-R04.
Original dataset: Gerwin Schalk (2009), version 1.0.0, https://doi.org/10.13026/C28G6P
Source: https://physionet.org/content/eegmmidb/1.0.0/
License: Open Data Commons Attribution License v1.0 (ODC-By-1.0).
Original publication: Schalk et al., BCI2000: A General-Purpose Brain-Computer Interface (BCI) System, IEEE TBME 51(6), 1034-1043, 2004.
Tasks: eyesopen R01; eyesclosed R02; execution R03; imagery R04.
This subset is not a publication or an official NEMAR release.
EEG labels are canonicalized. All other EDF bytes, including signals and annotations, are retained.
events.tsv trial_type supplies run-specific meaning; original_code preserves T0/T1/T2.
PowerLineFrequency=60 is inferred from US acquisition context, not read from EDF.
Reference, ground, hardware manufacturer, and acquisition filters are undocumented here (n/a).
No filtering, re-referencing, resampling, or extra unit scaling is performed.
No template electrode positions are assigned. Public source timestamps are retained.
The accompanying convert.py and run-reports/VALIDATION.md outside the BIDS root document reproduction and checks.
''')
        results = [verify_run(output, run) for run in TASKS]
    require(before == {run: sha256(source_path(run)) for run in TASKS}, 'Source EDF changed during conversion/verification')
    for warning in caught:
        print(f'{warning.category.__name__}: {warning.message}', file=sys.stderr)
    validator = run_validator(output, report_dir)
    make_report(report_dir, output, results, validator, caught)
    for row in results:
        print(json.dumps(row))
    print('REPORT', report_dir/'VALIDATION.md')
    require(validator['returncode'] == 0 and not validator['errors'], 'BIDS validator failed; inspect report')


if __name__ == '__main__':
    main()
