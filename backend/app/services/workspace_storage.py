"""Durable analysis storage shared by the API and worker.

Local paths remain the default for development.  Azure Container Apps Express
environments do not support Azure Files volume mounts, so production can set
``STORAGE_BACKEND=azure_blob`` to persist uploads and generated artifacts in a
private Azure Blob Storage container instead.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath

from app.core.config import settings


class WorkspaceStorage:
    """Keep the existing path-based analysis code while synchronising to Blob."""

    def __init__(self) -> None:
        self.enabled = settings.STORAGE_BACKEND.lower() == "azure_blob"
        self._container = None
        self._hydrated: set[int] = set()

    def _container_client(self):
        if not self.enabled:
            return None
        if self._container is None:
            if not settings.AZURE_STORAGE_CONNECTION_STRING:
                raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is required for azure_blob storage.")
            try:
                from azure.storage.blob import BlobServiceClient
            except ImportError as exc:  # pragma: no cover - guarded by production dependency
                raise RuntimeError("azure-storage-blob must be installed for azure_blob storage.") from exc
            self._container = BlobServiceClient.from_connection_string(
                settings.AZURE_STORAGE_CONNECTION_STRING
            ).get_container_client(settings.AZURE_STORAGE_CONTAINER)
        return self._container

    def store_upload(self, local_path: Path, object_name: str) -> str:
        """Persist an accepted upload and return a value suitable for Analysis.file_path."""
        if not self.enabled:
            return str(local_path.resolve())
        blob_name = f"uploads/{object_name}"
        with local_path.open("rb") as stream:
            self._container_client().upload_blob(blob_name, stream, overwrite=False)
        return f"blob://{blob_name}"

    def materialize_upload(self, stored_path: str, destination: Path) -> Path:
        """Return a local readable path for an upload, downloading it when needed."""
        if not self.enabled or not stored_path.startswith("blob://"):
            return Path(stored_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as stream:
            self._container_client().download_blob(stored_path.removeprefix("blob://")).readinto(stream)
        return destination

    def hydrate_workspace(self, analysis_id: int, root: Path) -> None:
        """Download one analysis workspace once for the lifetime of this service."""
        if not self.enabled or analysis_id in self._hydrated:
            return
        prefix = f"analyses/{analysis_id}/"
        container = self._container_client()
        for blob in container.list_blobs(name_starts_with=prefix):
            relative = PurePosixPath(blob.name).relative_to(prefix)
            destination = root.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as stream:
                container.download_blob(blob.name).readinto(stream)
        self._hydrated.add(analysis_id)

    def publish_workspace(self, analysis_id: int, root: Path) -> None:
        """Upload generated reports and datasets after a worker completes an analysis."""
        if not self.enabled:
            return
        container = self._container_client()
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            with path.open("rb") as stream:
                container.upload_blob(f"analyses/{analysis_id}/{relative}", stream, overwrite=True)
