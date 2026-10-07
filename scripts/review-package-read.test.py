import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('snapshot_reader', Path(__file__).with_name('review-package-read.py'))
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)

class SnapshotReads(unittest.TestCase):
    def test_symlinks_and_special_files_refused(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            (base / 'real').write_text('synthetic')
            (base / 'link').symlink_to(base / 'real')
            os.mkfifo(base / 'fifo')
            for name in ['link', 'fifo']:
                with self.assertRaises((OSError, ValueError)):
                    reader.read_snapshot(root, [name])

    def test_total_bytes_bounded(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'large'
            with path.open('wb') as file:
                file.truncate(reader.LIMIT + 1)
            with self.assertRaisesRegex(ValueError, '12 MB'):
                reader.read_snapshot(root, ['large'])

    def test_parent_swap_cannot_redirect_read(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            (base / 'inside').mkdir()
            (base / 'outside').mkdir()
            (base / 'inside' / 'value').write_text('synthetic inside')
            (base / 'outside' / 'value').write_text('outside must never be read')
            original_open = os.open
            def swap(path, flags, *args, **kwargs):
                if path == 'value':
                    (base / 'inside').rename(base / 'saved')
                    (base / 'inside').symlink_to(base / 'outside', target_is_directory=True)
                return original_open(path, flags, *args, **kwargs)
            # Preserve the real capability set while replacing only the open operation.
            with patch.object(reader.os, 'supports_dir_fd', os.supports_dir_fd | {swap}):
                with patch.object(reader.os, 'open', swap):
                    result = reader.read_snapshot(root, ['inside/value'])
            self.assertEqual(result[0]['content'], 'synthetic inside')

if __name__ == '__main__':
    unittest.main()
