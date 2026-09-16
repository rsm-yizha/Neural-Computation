"""Verify that the round-trip checks reject real corruption in disposable copies."""
from pathlib import Path
import shutil
import struct
import tempfile
import unittest

import convert


class CorruptionDetectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='nemar-fault-check-')
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name)/'bids'
        shutil.copytree(convert.ROOT/'bids', self.output)
        self.path = convert.bids_path(self.output, '03')

    def check_rejected(self, message):
        with self.assertRaisesRegex((ValueError, AssertionError), message):
            convert.verify_run(self.output, '03')

    def test_unmodified_control_passes(self):
        result = convert.verify_run(self.output, '03')
        self.assertEqual(result['max_signal_diff_v'], 0)
        self.assertEqual(result['events_bids'], 30)

    def test_one_digital_sample_change_is_detected(self):
        with self.path.fpath.open('r+b') as stream:
            header = stream.read(256)
            offset = int(header[184:192])
            stream.seek(offset)
            sample = struct.unpack('<h', stream.read(2))[0]
            stream.seek(offset)
            stream.write(struct.pack('<h', sample+1 if sample < 32767 else sample-1))
        self.check_rejected('signal samples changed')

    def test_one_sample_event_shift_is_detected(self):
        path = convert.sidecar(self.path, 'events', '.tsv')
        rows = convert.read_tsv(path)
        rows[1]['onset'] = str(float(rows[1]['onset']) + 1/160)
        convert.write_tsv(path, rows)
        self.check_rejected('Not equal')

    def test_event_duration_change_is_detected(self):
        path = convert.sidecar(self.path, 'events', '.tsv')
        rows = convert.read_tsv(path)
        rows[1]['duration'] = str(float(rows[1]['duration']) + 1/160)
        convert.write_tsv(path, rows)
        self.check_rejected('Not equal')

    def test_execution_mislabeled_as_imagery_is_detected(self):
        path = convert.sidecar(self.path, 'events', '.tsv')
        rows = convert.read_tsv(path)
        rows[1]['trial_type'] = 'imagine_right_fist'
        convert.write_tsv(path, rows)
        self.check_rejected('event semantics changed')

    def test_wrong_original_code_is_detected(self):
        path = convert.sidecar(self.path, 'events', '.tsv')
        rows = convert.read_tsv(path)
        rows[1]['original_code'] = 'T1'
        convert.write_tsv(path, rows)
        self.check_rejected('original codes changed')

    def test_reordered_channel_metadata_is_detected(self):
        path = convert.sidecar(self.path, 'channels', '.tsv')
        rows = convert.read_tsv(path)
        rows[0], rows[1] = rows[1], rows[0]
        convert.write_tsv(path, rows)
        with self.assertRaisesRegex(RuntimeError, 'Channel mismatch'):
            convert.verify_run(self.output, '03')


if __name__ == '__main__':
    unittest.main(verbosity=2)
