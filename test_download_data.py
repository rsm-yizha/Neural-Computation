"""Download integrity checks without a network connection."""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import download_data


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'S001R01.edf'
        self.content = b'test recording'
        self.hash_patch = patch.dict(download_data.HASHES, {'01': hashlib.sha256(self.content).hexdigest()})
        self.hash_patch.start()
        self.addCleanup(self.hash_patch.stop)

    def test_valid_download_and_cached_reuse(self):
        with patch('download_data.urlopen', return_value=io.BytesIO(self.content)) as request:
            self.assertEqual(download_data.fetch_recording('01', self.path), 'downloaded and verified')
            self.assertEqual(download_data.fetch_recording('01', self.path), 'already verified')
            self.assertEqual(request.call_count, 1)
        self.assertEqual(self.path.read_bytes(), self.content)

    def test_bad_download_is_not_saved(self):
        with patch('download_data.urlopen', return_value=io.BytesIO(b'corrupt')):
            with self.assertRaisesRegex(ValueError, 'Download checksum mismatch'):
                download_data.fetch_recording('01', self.path)
        self.assertFalse(self.path.exists())

    def test_existing_bad_file_is_not_overwritten(self):
        self.path.write_bytes(b'keep this file')
        with patch('download_data.urlopen') as request:
            with self.assertRaisesRegex(ValueError, 'Existing file'):
                download_data.fetch_recording('01', self.path)
            request.assert_not_called()
        self.assertEqual(self.path.read_bytes(), b'keep this file')


if __name__ == '__main__':
    unittest.main(verbosity=2)
