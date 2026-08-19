from datetime import datetime, timedelta, timezone
from hashlib import sha256

from azure.storage.blob import BlobSasPermissions, BlobServiceClient, ContentSettings, generate_blob_sas

from backend.app.core.config import settings
from backend.app.core.logging_config import service_logger


logger = service_logger("blob")


def blob_ref(blob_path: str) -> str:
    return sha256(blob_path.encode("utf-8")).hexdigest()[:12]


def get_blob_service() -> BlobServiceClient:
    if not settings.azure_storage_connection_string:
        raise RuntimeError("Azure Blob Storage is not configured")
    return BlobServiceClient.from_connection_string(settings.azure_storage_connection_string)


def ensure_container() -> None:
    client = get_blob_service().get_container_client(settings.azure_storage_container)
    if not client.exists():
        client.create_container()


def upload_resume(blob_path: str, content: bytes, content_type: str | None) -> None:
    ensure_container()
    blob = get_blob_service().get_blob_client(settings.azure_storage_container, blob_path)
    blob.upload_blob(content, overwrite=False, content_settings=ContentSettings(content_type=content_type))
    logger.info("blob_uploaded", extra={"blob_ref": blob_ref(blob_path), "bytes": len(content), "content_type": content_type})


def delete_resume(blob_path: str) -> None:
    get_blob_service().get_blob_client(settings.azure_storage_container, blob_path).delete_blob(delete_snapshots="include")
    logger.info("blob_deleted", extra={"blob_ref": blob_ref(blob_path)})


def create_download_url(blob_path: str, minutes: int = 10, download_name: str | None = None) -> str:
    service = get_blob_service()
    blob = service.get_blob_client(settings.azure_storage_container, blob_path)
    credential = service.credential
    account_key = getattr(credential, "account_key", None)
    if not account_key:
        raise RuntimeError("Storage account key is required to generate a SAS URL")
    token = generate_blob_sas(
        account_name=service.account_name,
        container_name=settings.azure_storage_container,
        blob_name=blob_path,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(minutes=minutes),
        content_disposition=f'attachment; filename="{download_name.replace(chr(34), "")}"' if download_name else None,
    )
    logger.info("sas_generated", extra={"blob_ref": blob_ref(blob_path), "minutes": minutes, "download": bool(download_name)})
    return f"{blob.url}?{token}"