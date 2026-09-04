from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

import boto3

from .config import SaaSConfig


class ObjectStore:
    def __init__(self, cfg: SaaSConfig):
        self.bucket = cfg.r2_bucket
        self.client = boto3.client("s3", endpoint_url=cfg.r2_endpoint,
            aws_access_key_id=cfg.r2_access_key, aws_secret_access_key=cfg.r2_secret_key, region_name="auto")

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
                               ServerSideEncryption="AES256")

    def download(self, key: str, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, key, str(target))

    def upload(self, key: str, source: Path, content_type: str="application/octet-stream") -> None:
        self.client.upload_file(str(source), self.bucket, key, ExtraArgs={"ContentType": content_type, "ServerSideEncryption":"AES256"})

    def signed_download(self, key: str, expires: int=300) -> str:
        return self.client.generate_presigned_url("get_object", Params={"Bucket":self.bucket,"Key":key}, ExpiresIn=expires)

    def delete_prefix(self, prefix: str) -> None:
        paginator=self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket,Prefix=prefix):
            keys=[{"Key":item["Key"]} for item in page.get("Contents",[])]
            if keys: self.client.delete_objects(Bucket=self.bucket,Delete={"Objects":keys,"Quiet":True})
