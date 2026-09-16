"""Download only S001 R01-R04 from PhysioNet and verify pinned SHA-256 hashes."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
SOURCE = 'https://physionet.org/files/eegmmidb/1.0.0/S001/'
HASHES = json.loads((ROOT/'source_hashes.json').read_text())


def fetch_recording(run, destination):
    """Reuse matching files; reject mismatches without replacing existing data."""
    destination = Path(destination)
    expected = HASHES[run]
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Existing file has an unexpected hash: {destination}')
        return 'already verified'
    with urlopen(SOURCE + f'S001R{run}.edf', timeout=60) as response:
        content = response.read()
    if hashlib.sha256(content).hexdigest() != expected:
        raise ValueError(f'Download checksum mismatch: R{run}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream:
        stream.write(content)
    return 'downloaded and verified'


if __name__ == '__main__':
    for run in HASHES:
        path = ROOT/'raw'/'S001'/f'S001R{run}.edf'
        print(path.name, fetch_recording(run, path))
