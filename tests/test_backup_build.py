import gzip
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scripts import backup_build as backup


class BuildBackupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.env = dict(JOB_NAME='Project Y/main', BUILD_NUMBER='42',
                        GIT_COMMIT='a' * 40, BUILD_RESULT='SUCCESS',
                        BUILD_IMAGE='project-y:build-42-aaaaaaaaaaaa', IMAGE_BUILT='true',
                        NAS_HOST='10.50.2.10', NAS_USER='ubuntu',
                        NAS_BACKUP_ROOT='/data/share/project-y-builds',
                        NAS_KNOWN_HOSTS='/tmp/known_hosts', DB_PASSWORD='must-not-be-exported')

    def export_process(self, status=0):
        process = MagicMock()
        process.__enter__.return_value = process
        process.stdout = io.BytesIO(b'docker-image-export')
        process.wait.return_value = status
        return process

    def test_image_export_checksums_and_no_runtime_secrets(self):
        with patch.object(backup.subprocess, 'check_output', return_value='sha256:123\n'), \
             patch.object(backup.subprocess, 'Popen', return_value=self.export_process()):
            record = backup.make_bundle(self.directory, self.env)
        self.assertEqual(record['image'], self.env['BUILD_IMAGE'])
        with gzip.open(self.directory / 'image.tar.gz', 'rb') as archive:
            self.assertEqual(archive.read(), b'docker-image-export')
        for line in (self.directory / 'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ')
            self.assertEqual(digest, backup.sha256(self.directory / name))
        self.assertNotIn(self.env['DB_PASSWORD'], (self.directory / 'build.json').read_text())
        self.assertEqual(json.loads((self.directory / 'build.json').read_text())['commit'], 'a' * 40)

    def test_failed_build_records_failure_without_exporting_stale_image(self):
        self.env.update(IMAGE_BUILT='false', BUILD_RESULT='FAILURE')
        with patch.object(backup.subprocess, 'check_output') as inspect, \
             patch.object(backup.subprocess, 'Popen') as exporter:
            record = backup.make_bundle(self.directory, self.env)
        inspect.assert_not_called()
        exporter.assert_not_called()
        self.assertIsNone(record['image'])
        self.assertFalse((self.directory / 'image.tar.gz').exists())
        self.assertEqual(record['build_result_before_backup'], 'FAILURE')

    def test_export_failure_is_not_treated_as_complete(self):
        with patch.object(backup.subprocess, 'check_output', return_value='sha256:123'), \
             patch.object(backup.subprocess, 'Popen', return_value=self.export_process(1)):
            with self.assertRaisesRegex(RuntimeError, 'Docker export failed'):
                backup.make_bundle(self.directory, self.env)
        self.assertFalse((self.directory / 'SHA256SUMS').exists())

    def test_success_without_image_marker_cannot_publish_metadata_only(self):
        self.env['IMAGE_BUILT'] = 'false'
        with self.assertRaisesRegex(RuntimeError, 'Successful build has no image marker'):
            backup.make_bundle(self.directory, self.env)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_jobs_with_same_slug_have_different_directories(self):
        first, _ = backup.destination_paths(self.env)
        self.env['JOB_NAME'] = 'Project Y-main'
        second, _ = backup.destination_paths(self.env)
        self.assertNotEqual(first, second)

    def test_invalid_paths_and_commit_are_rejected(self):
        for value in ('/', '/data', '/data/../share', 'relative/path'):
            with self.subTest(root=value), self.assertRaises(ValueError):
                backup.destination_paths(dict(self.env, NAS_BACKUP_ROOT=value))
        with self.assertRaises(ValueError):
            backup.destination_paths(dict(self.env, GIT_COMMIT='invalid;command'))

    def stage_path(self):
        job, name = backup.destination_paths(self.env)
        return str(job / f'.upload-{name}-ABC123')

    def test_publish_checks_integrity_before_making_files_readable(self):
        (self.directory / 'build.json').write_text('{}')
        with patch.object(backup.subprocess, 'check_output', return_value=self.stage_path()), \
             patch.object(backup.subprocess, 'run') as run:
            backup.publish(self.directory, self.env)
        upload, finalize = [call.args[0] for call in run.call_args_list]
        self.assertEqual(upload[0], 'scp')
        self.assertIn('StrictHostKeyChecking=yes', upload)
        self.assertIn('BatchMode=yes', upload)
        command = finalize[-1]
        self.assertLess(command.index('sha256sum -c'), command.index('chmod 644'))
        self.assertLess(command.index('chmod 644'), command.index('mv -T'))
        self.assertIn('test ! -e', command)

    def test_upload_failure_never_publishes_directory(self):
        with patch.object(backup.subprocess, 'check_output', return_value=self.stage_path()), \
             patch.object(backup.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'scp')) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                backup.publish(self.directory, self.env)
        self.assertEqual(run.call_count, 1)

    def test_unexpected_staging_path_is_rejected_before_upload(self):
        with patch.object(backup.subprocess, 'check_output', return_value='/other/path'), \
             patch.object(backup.subprocess, 'run') as run:
            with self.assertRaises(RuntimeError):
                backup.publish(self.directory, self.env)
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
