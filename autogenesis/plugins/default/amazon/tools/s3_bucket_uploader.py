"""S3 Bucket Uploader."""

from typing import Any, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class AmazonS3BucketUploaderTool(PluginTool):
    """S3 Bucket Uploader."""

    name: str = 's3_bucket_uploader'
    display_name: str = 'S3 Bucket Uploader'
    description: str = 'Uploads files to S3 bucket.'
    category: str = 'files'
    type: str = 'tool'

    async def __call__(self, bucket_name: str = "", file_path: str = "", s3_key: str = "", aws_access_key_id: str = "", aws_secret_access_key: str = "", **kwargs) -> Response:
        if not bucket_name or not file_path:
            return self._fail("amazon.s3: 'bucket_name' and 'file_path' are required.")
        akid = self._secret(aws_access_key_id, "AWS_ACCESS_KEY_ID")
        secret = self._secret(aws_secret_access_key, "AWS_SECRET_ACCESS_KEY")
        try:
            import boto3
            import os as _os
            client = boto3.client("s3", aws_access_key_id=akid or None, aws_secret_access_key=secret or None)
            key = s3_key or _os.path.basename(file_path)
            client.upload_file(file_path, bucket_name, key)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"amazon.s3: {type(exc).__name__}: {exc}")
        return self._ok(f"Uploaded {file_path} to s3://{bucket_name}/{key}.", bucket=bucket_name, key=key)
