"""
Edge & Object Storage Layer (S3-compatible bucket & CDN routing).

Supports:
- Local filesystem serving (development)
- S3 / MinIO / Cloudflare R2 object storage (production)
- CDN edge caching acceleration for static and uploaded assets
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from flask import current_app, url_for

logger = logging.getLogger("opencampus.storage")


class StorageManager:
    def __init__(self):
        self.s3_client = None
        self._initialized = False

    def _init_s3(self):
        if self._initialized:
            return
        bucket = os.environ.get("S3_BUCKET_NAME")
        if bucket:
            try:
                import boto3
                endpoint = os.environ.get("S3_ENDPOINT_URL")
                self.s3_client = boto3.client(
                    "s3",
                    endpoint_url=endpoint,
                    aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
                    aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
                    region_name=os.environ.get("AWS_REGION", "us-east-1"),
                )
                logger.info("Connected to S3-compatible bucket: %s", bucket)
            except Exception as exc:
                logger.warning("Failed to initialize S3 client (%s); using local filesystem", exc)
                self.s3_client = None
        self._initialized = True

    def get_asset_url(self, filename: str, asset_type: str = "static") -> str:
        """
        Return CDN URL if configured, otherwise generate standard Flask static route.
        """
        cdn_base = os.environ.get("CDN_BASE_URL", "").rstrip("/")
        if cdn_base:
            return f"{cdn_base}/{asset_type}/{filename.lstrip('/')}"

        # Standard Flask local URL
        try:
            return url_for("static", filename=filename)
        except RuntimeError:
            return f"/static/{filename.lstrip('/')}"

    def upload_file(self, file_obj, destination_path: str) -> str:
        """
        Upload file to S3 bucket if configured, or save locally.
        Returns the public URL for the stored asset.
        """
        self._init_s3()
        bucket = os.environ.get("S3_BUCKET_NAME")
        if self.s3_client and bucket:
            self.s3_client.upload_fileobj(
                file_obj,
                bucket,
                destination_path,
                ExtraArgs={"ACL": "public-read"}
            )
            return self.get_asset_url(destination_path, asset_type="uploads")

        # Local storage
        local_dir = Path(os.environ.get("OPENCAMPUS_DATA_DIR", "./instance")) / "uploads"
        local_dir.mkdir(parents=True, exist_ok=True)
        target = local_dir / destination_path
        target.parent.mkdir(parents=True, exist_ok=True)
        file_obj.save(str(target))
        return f"/uploads/{destination_path}"


storage = StorageManager()
