import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.core.config import settings
from app.services.workspace_storage import WorkspaceStorage


class _Downloader:
    def __init__(self, data):
        self.data = data

    def readinto(self, stream):
        stream.write(self.data)


class _Container:
    def __init__(self):
        self.blobs = {}

    def upload_blob(self, name, stream, overwrite=False):
        if name in self.blobs and not overwrite:
            raise RuntimeError('Blob already exists')
        self.blobs[name] = stream.read()

    def download_blob(self, name):
        return _Downloader(self.blobs[name])

    def list_blobs(self, name_starts_with):
        return [SimpleNamespace(name=name) for name in self.blobs if name.startswith(name_starts_with)]


class WorkspaceStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.backend = patch.object(settings, 'STORAGE_BACKEND', 'azure_blob')
        self.connection = patch.object(settings, 'AZURE_STORAGE_CONNECTION_STRING', 'test-only')
        self.backend.start()
        self.connection.start()
        self.storage = WorkspaceStorage()
        self.container = _Container()
        self.storage._container = self.container

    def tearDown(self):
        self.connection.stop()
        self.backend.stop()
        self.temp.cleanup()

    def test_upload_and_workspace_round_trip(self):
        source = self.root / 'source.xlsx'
        source.write_bytes(b'workbook')
        stored_path = self.storage.store_upload(source, 'token.xlsx')
        self.assertEqual(stored_path, 'blob://uploads/token.xlsx')

        downloaded = self.storage.materialize_upload(stored_path, self.root / 'downloaded.xlsx')
        self.assertEqual(downloaded.read_bytes(), b'workbook')

        workspace = self.root / 'workspace'
        report = workspace / 'report' / 'audit_report.json'
        report.parent.mkdir(parents=True)
        report.write_bytes(b'{"ok": true}')
        self.storage.publish_workspace(7, workspace)

        hydrated = self.root / 'hydrated'
        reader = WorkspaceStorage()
        reader._container = self.container
        reader.hydrate_workspace(7, hydrated)
        self.assertEqual((hydrated / 'report' / 'audit_report.json').read_bytes(), b'{"ok": true}')


if __name__ == '__main__':
    unittest.main()
