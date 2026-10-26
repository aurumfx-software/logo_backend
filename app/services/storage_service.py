import base64
import mimetypes
import os
import uuid
from typing import Optional
from fastapi import UploadFile

try:
    import boto3
    from botocore.client import Config
except ImportError:
    boto3 = None
    Config = None

from app.core.config import settings


class SpacesStorageService:
    """Service to upload and manage media on DigitalOcean Spaces (S3 compatible)."""

    def __init__(self):
        self.bucket = settings.SPACES_BUCKET or "aurumfx-images"
        self.region = settings.SPACES_REGION or "sgp1"
        self.access_key = settings.SPACES_ACCESS_KEY
        self.secret_key = settings.SPACES_SECRET_KEY
        
        # S3 endpoint for boto3 MUST be the regional endpoint
        # e.g. https://sgp1.digitaloceanspaces.com
        endpoint = settings.SPACES_ENDPOINT or ""
        if "digitaloceanspaces.com" in endpoint:
            # Normalize to https://{region}.digitaloceanspaces.com
            self.endpoint_url = f"https://{self.region}.digitaloceanspaces.com"
        elif endpoint:
            self.endpoint_url = endpoint
        else:
            self.endpoint_url = f"https://{self.region}.digitaloceanspaces.com"

        # Public CDN / Web URL prefix
        self.cdn_base_url = f"https://{self.bucket}.{self.region}.digitaloceanspaces.com"
        self._client = None

    @property
    def client(self):
        if self._client is None and boto3 is not None and self.access_key and self.secret_key:
            try:
                session = boto3.session.Session()
                self._client = session.client(
                    "s3",
                    region_name=self.region,
                    endpoint_url=self.endpoint_url,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    config=Config(s3={"addressing_style": "virtual"}),
                )
            except Exception as e:
                print(f"[SpacesStorageService] Error initializing boto3 client: {e}")
                self._client = None
        return self._client

    def upload_bytes(
        self,
        file_bytes: bytes,
        filename: str,
        folder: str = "merchants/photos",
        content_type: Optional[str] = None,
    ) -> str:
        """Upload raw bytes to DigitalOcean Spaces and return full public CDN URL."""
        ext = os.path.splitext(filename)[1].lower() if filename else ".jpg"
        unique_key = f"{folder}/{uuid.uuid4().hex}{ext}"

        if not content_type:
            content_type, _ = mimetypes.guess_type(filename)
            if not content_type:
                if ext in [".jpg", ".jpeg"]:
                    content_type = "image/jpeg"
                elif ext == ".png":
                    content_type = "image/png"
                elif ext == ".webp":
                    content_type = "image/webp"
                elif ext == ".mp4":
                    content_type = "video/mp4"
                elif ext == ".webm":
                    content_type = "video/webm"
                elif ext in [".mov", ".qt"]:
                    content_type = "video/quicktime"
                else:
                    content_type = "application/octet-stream"

        if self.client:
            try:
                self.client.put_object(
                    Bucket=self.bucket,
                    Key=unique_key,
                    Body=file_bytes,
                    ACL="public-read",
                    ContentType=content_type,
                )
                public_url = f"{self.cdn_base_url}/{unique_key}"
                print(f"[SpacesStorageService] Uploaded to Spaces: {public_url}")
                return public_url
            except Exception as e:
                print(f"[SpacesStorageService] Spaces upload failed, falling back to local: {e}")

        # Local fallback if Spaces is unavailable
        local_dir = os.path.join("uploads", folder)
        os.makedirs(local_dir, exist_ok=True)
        local_filename = f"{uuid.uuid4().hex}{ext}"
        local_path = os.path.join(local_dir, local_filename)
        with open(local_path, "wb") as f:
            f.write(file_bytes)

        server_host = os.environ.get("SERVER_HOST", "http://168.144.18.149:8000")
        return f"{server_host}/static/{folder}/{local_filename}"

    def upload_file(self, upload_file: UploadFile, folder: str = "merchants/photos") -> str:
        """Upload a FastAPI UploadFile to Spaces and return full public CDN URL."""
        upload_file.file.seek(0)
        file_bytes = upload_file.file.read()
        return self.upload_bytes(
            file_bytes=file_bytes,
            filename=upload_file.filename or f"media_{uuid.uuid4().hex[:8]}",
            folder=folder,
            content_type=upload_file.content_type,
        )

    def upload_base64_media(
        self,
        val: Optional[str],
        folder: str = "merchants/photos",
        default_ext: str = ".jpg",
    ) -> Optional[str]:
        """
        If val is a base64 Data URL, decodes and uploads it to Spaces.
        If val is already an HTTP/HTTPS URL, returns it unchanged.
        """
        if not val or not isinstance(val, str):
            return val

        clean_val = val.strip()
        if not clean_val.startswith("data:"):
            # Normalize legacy relative /static/... URLs to full host URLs
            if clean_val.startswith("/static/"):
                server_host = os.environ.get("SERVER_HOST", "http://168.144.18.149:8000")
                return f"{server_host}{clean_val}"
            return clean_val

        try:
            header, encoded = clean_val.split(",", 1)
            ext = default_ext
            content_type = "image/jpeg"

            if "image/jpeg" in header or "image/jpg" in header:
                ext = ".jpg"
                content_type = "image/jpeg"
            elif "image/png" in header:
                ext = ".png"
                content_type = "image/png"
            elif "image/webp" in header:
                ext = ".webp"
                content_type = "image/webp"
            elif "image/gif" in header:
                ext = ".gif"
                content_type = "image/gif"
            elif "video/mp4" in header:
                ext = ".mp4"
                content_type = "video/mp4"
            elif "video/webm" in header:
                ext = ".webm"
                content_type = "video/webm"
            elif "video/quicktime" in header or "video/mov" in header:
                ext = ".mov"
                content_type = "video/quicktime"

            file_bytes = base64.b64decode(encoded)
            return self.upload_bytes(
                file_bytes=file_bytes,
                filename=f"upload_{uuid.uuid4().hex[:8]}{ext}",
                folder=folder,
                content_type=content_type,
            )
        except Exception as e:
            print(f"[SpacesStorageService] Error decoding base64 media: {e}")
            return None


# Global singleton instance
storage_service = SpacesStorageService()
