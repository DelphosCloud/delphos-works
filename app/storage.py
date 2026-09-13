import asyncio

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.config import (
    DOWNLOAD_URL_EXPIRY_SECONDS,
    SPACES_BUCKET,
    SPACES_CONNECT_TIMEOUT,
    SPACES_KEY,
    SPACES_READ_TIMEOUT,
    SPACES_REGION,
    SPACES_SECRET,
)

ENDPOINT_URL = f"https://{SPACES_REGION}.digitaloceanspaces.com"

_client = None


def _get_client():
    # (#11) Bound how long any single Spaces call can take, so a stuck
    # connection fails cleanly instead of hanging forever.
    global _client
    if _client is None:
        session = boto3.session.Session()
        _client = session.client(
            "s3",
            region_name=SPACES_REGION,
            endpoint_url=ENDPOINT_URL,
            aws_access_key_id=SPACES_KEY,
            aws_secret_access_key=SPACES_SECRET,
            config=Config(
                connect_timeout=SPACES_CONNECT_TIMEOUT,
                read_timeout=SPACES_READ_TIMEOUT,
            ),
        )
    return _client


# --- Synchronous implementations (unchanged behaviour) ---


def _upload_file_sync(local_path: str, remote_key: str) -> None:
    _get_client().upload_file(local_path, SPACES_BUCKET, remote_key)


def _download_file_sync(remote_key: str, local_path: str) -> None:
    _get_client().download_file(SPACES_BUCKET, remote_key, local_path)


def _delete_file_sync(remote_key: str) -> None:
    _get_client().delete_object(Bucket=SPACES_BUCKET, Key=remote_key)


def _file_exists_sync(remote_key: str) -> bool:
    try:
        _get_client().head_object(Bucket=SPACES_BUCKET, Key=remote_key)
        return True
    except ClientError:
        return False


def _list_files_sync(prefix: str) -> list[str]:
    client = _get_client()
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=SPACES_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def _check_connectivity_sync() -> bool:
    try:
        _get_client().head_bucket(Bucket=SPACES_BUCKET)
        return True
    except Exception:
        return False


def _presigned_download_url_sync(remote_key: str, filename: str) -> str:
    return _get_client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": SPACES_BUCKET,
            "Key": remote_key,
            "ResponseContentDisposition": f'attachment; filename="{filename}"',
        },
        ExpiresIn=DOWNLOAD_URL_EXPIRY_SECONDS,
    )


# --- Async wrappers (#9) ---
#
# boto3 is a blocking library. Calling it directly inside an `async def`
# route would freeze the whole event loop — and every other in-flight
# request — until the network call to Spaces returns. Running each call in
# a background thread keeps requests running concurrently instead of
# serialising behind whichever one happens to be talking to Spaces.


async def upload_file(local_path: str, remote_key: str) -> None:
    await asyncio.to_thread(_upload_file_sync, local_path, remote_key)


async def download_file(remote_key: str, local_path: str) -> None:
    await asyncio.to_thread(_download_file_sync, remote_key, local_path)


async def delete_file(remote_key: str) -> None:
    await asyncio.to_thread(_delete_file_sync, remote_key)


async def file_exists(remote_key: str) -> bool:
    return await asyncio.to_thread(_file_exists_sync, remote_key)


async def list_files(prefix: str) -> list[str]:
    return await asyncio.to_thread(_list_files_sync, prefix)


async def check_connectivity() -> bool:
    return await asyncio.to_thread(_check_connectivity_sync)


async def presigned_download_url(remote_key: str, filename: str) -> str:
    return await asyncio.to_thread(_presigned_download_url_sync, remote_key, filename)
