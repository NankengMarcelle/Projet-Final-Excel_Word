from pathlib import Path

import boto3
from botocore.config import Config

from app.core.config import settings

# Path-style addressing (bucket in the URL path, not a subdomain) is required for
# non-AWS S3-compatible endpoints like Supabase Storage/MinIO/R2 — virtual-hosted-style
# addressing assumes a real AWS DNS setup that these don't have.
_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            region_name=settings.S3_REGION,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
            # botocore >=1.36 defaults to always sending the new AWS-specific checksum headers
            # (x-amz-sdk-checksum-algorithm etc.) on every S3 request. Non-AWS S3-compatible
            # backends like Supabase Storage/MinIO don't understand them and reject the request
            # with an opaque, empty-body "An error occurred ()" PutObject failure — this pair
            # restores the pre-1.36 behavior of only sending a checksum when one is actually
            # required, which is what these providers expect.
            config=Config(
                s3={"addressing_style": "path"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )
    return _client


def download(key: str, local_path: Path) -> None:
    # get_object, not download_file: download_file goes through s3transfer's TransferManager,
    # which (a known, still-open boto3/s3transfer bug as of botocore 1.36+) forces AWS-specific
    # checksum headers regardless of the request_checksum_calculation config above — Supabase's
    # S3 gateway (and MinIO/R2) rejects those with an opaque, empty "An error occurred ()".
    # Plain get_object/put_object never go through TransferManager, so they're unaffected.
    # Workbooks are small enough (well under the 1GB free-tier bucket anyway) that loading the
    # whole body into memory here is fine — the rest of this codebase already does the same
    # (e.g. workbook_service.import_workbook reads the whole upload into memory too).
    local_path.parent.mkdir(parents=True, exist_ok=True)
    response = _get_client().get_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
    local_path.write_bytes(response["Body"].read())


def upload(local_path: Path, key: str) -> None:
    _get_client().put_object(Bucket=settings.S3_BUCKET_NAME, Key=key, Body=local_path.read_bytes())


def delete(key: str) -> None:
    _get_client().delete_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
