import boto3
from botocore.exceptions import ClientError

from app.config import SPACES_KEY, SPACES_SECRET, SPACES_REGION, SPACES_BUCKET

ENDPOINT_URL = f"https://{SPACES_REGION}.digitaloceanspaces.com"

_client = None


def _get_client():
    global _client
    if _client is None:
        session = boto3.session.Session()
        _client = session.client(
            "s3",
            region_name=SPACES_REGION,
            endpoint_url=ENDPOINT_URL,
            aws_access_key_id=SPACES_KEY,
            aws_secret_access_key=SPACES_SECRET,
        )
    return _client


def upload_file(local_path: str, remote_key: str) -> None:
    _get_client().upload_file(local_path, SPACES_BUCKET, remote_key)


def download_file(remote_key: str, local_path: str) -> None:
    _get_client().download_file(SPACES_BUCKET, remote_key, local_path)


def delete_file(remote_key: str) -> None:
    _get_client().delete_object(Bucket=SPACES_BUCKET, Key=remote_key)


def file_exists(remote_key: str) -> bool:
    try:
        _get_client().head_object(Bucket=SPACES_BUCKET, Key=remote_key)
        return True
    except ClientError:
        return False


def list_files(prefix: str) -> list[str]:
    client = _get_client()
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=SPACES_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def check_connectivity() -> bool:
    try:
        _get_client().head_bucket(Bucket=SPACES_BUCKET)
        return True
    except Exception:
        return False
