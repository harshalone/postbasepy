"""Synchronous storage client — /api/storage/v1/... ."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

from .types import Bucket, QueryResult, SingleResult, StorageObject

# Accepts raw bytes, or any file-like object exposing .read() -> bytes.


def _encode_path(path: str) -> str:
    return "/".join(quote(part) for part in path.split("/"))


def _read_bytes(file: Any) -> bytes:
    if isinstance(file, (bytes, bytearray)):
        return bytes(file)
    if hasattr(file, "read"):
        data: bytes = file.read()
        return data
    raise TypeError("file must be bytes or a file-like object with .read()")


class StorageBucketClient:
    def __init__(
        self, http: httpx.Client, base_url: str, headers: Dict[str, str], bucket: str
    ) -> None:
        self._http = http
        self._base_url = base_url
        self._headers = headers
        self._bucket = bucket

    def upload(
        self,
        path: str,
        file: Any,
        content_type: Optional[str] = None,
        upsert: bool = False,
        cache_control: Optional[str] = None,
    ) -> SingleResult[Dict[str, str]]:
        try:
            data = _read_bytes(file)
            filename = path.rsplit("/", 1)[-1]
            files = {"file": (filename, data, content_type or "application/octet-stream")}
            form: Dict[str, str] = {"path": path}
            if upsert:
                form["upsert"] = "true"
            if cache_control:
                form["cacheControl"] = cache_control
            method = "PUT" if upsert else "POST"
            url = f"{self._base_url}/api/storage/v1/object/{self._bucket}/{_encode_path(path)}"
            res = self._http.request(method, url, headers=self._headers, data=form, files=files)
            text = res.text
            try:
                json_body = res.json() if text else {}
            except Exception:  # noqa: BLE001
                json_body = {}
            if res.is_error:
                return SingleResult(
                    data=None,
                    error=json_body.get("error")
                    or json_body.get("message")
                    or (text or "Upload failed"),
                )
            return SingleResult(
                data={"path": path, "fullPath": f"{self._bucket}/{path}"}, error=None
            )
        except Exception as err:  # noqa: BLE001
            return SingleResult(data=None, error=str(err))

    def download(self, path: str) -> Dict[str, Any]:
        try:
            url = f"{self._base_url}/api/storage/v1/object/{self._bucket}/{_encode_path(path)}"
            res = self._http.get(url, headers=self._headers)
            if res.is_error:
                return {"data": None, "error": "Download failed"}
            return {"data": res.content, "error": None}
        except Exception as err:  # noqa: BLE001
            return {"data": None, "error": str(err)}

    def remove(self, paths: List[str]) -> QueryResult[Dict[str, str]]:
        try:
            url = f"{self._base_url}/api/storage/v1/object/{self._bucket}"
            headers = {**self._headers, "Content-Type": "application/json"}
            res = self._http.request("DELETE", url, headers=headers, json={"prefixes": paths})
            json_body = res.json()
            if res.is_error:
                return QueryResult(
                    data=None, count=None, error=json_body.get("error", "Delete failed")
                )
            data = json_body.get("data")
            return QueryResult(data=data, count=(len(data) if data else None), error=None)
        except Exception as err:  # noqa: BLE001
            return QueryResult(data=None, count=None, error=str(err))

    def list(
        self,
        prefix: str = "",
        limit: int = 100,
        offset: int = 0,
        sort_by_column: Optional[str] = None,
        sort_by_order: Optional[str] = None,
    ) -> QueryResult[StorageObject]:
        try:
            url = f"{self._base_url}/api/storage/v1/object/list/{self._bucket}"
            headers = {**self._headers, "Content-Type": "application/json"}
            body: Dict[str, Any] = {"prefix": prefix, "limit": limit, "offset": offset}
            if sort_by_column:
                body["sortBy"] = {"column": sort_by_column, "order": sort_by_order}
            res = self._http.post(url, headers=headers, json=body)
            json_body = res.json()
            if res.is_error:
                return QueryResult(
                    data=None, count=None, error=json_body.get("error", "List failed")
                )
            data = json_body.get("data")
            return QueryResult(data=data, count=(len(data) if data else None), error=None)
        except Exception as err:  # noqa: BLE001
            return QueryResult(data=None, count=None, error=str(err))

    def get_public_url(self, path: str) -> Dict[str, Dict[str, str]]:
        object_path = f"{self._bucket}/{_encode_path(path)}"
        public_url = f"{self._base_url}/api/storage/v1/object/public/{object_path}"
        return {"data": {"publicUrl": public_url}}

    def create_signed_url(self, path: str, expires_in: int) -> SingleResult[Dict[str, str]]:
        try:
            url = f"{self._base_url}/api/storage/v1/object/sign/{self._bucket}/{_encode_path(path)}"
            headers = {**self._headers, "Content-Type": "application/json"}
            res = self._http.post(url, headers=headers, json={"expiresIn": expires_in})
            json_body = res.json()
            if res.is_error:
                return SingleResult(data=None, error=json_body.get("error", "Sign failed"))
            return SingleResult(
                data={"signedUrl": f"{self._base_url}{json_body['signedUrl']}"}, error=None
            )
        except Exception as err:  # noqa: BLE001
            return SingleResult(data=None, error=str(err))

    def move(self, from_path: str, to_path: str) -> Dict[str, Optional[str]]:
        try:
            url = f"{self._base_url}/api/storage/v1/object/move"
            headers = {**self._headers, "Content-Type": "application/json"}
            res = self._http.post(
                url,
                headers=headers,
                json={"bucketId": self._bucket, "sourceKey": from_path, "destinationKey": to_path},
            )
            json_body = res.json()
            if res.is_error:
                return {"error": json_body.get("error", "Move failed")}
            return {"error": None}
        except Exception as err:  # noqa: BLE001
            return {"error": str(err)}

    def copy(self, from_path: str, to_path: str) -> SingleResult[Dict[str, str]]:
        try:
            url = f"{self._base_url}/api/storage/v1/object/copy"
            headers = {**self._headers, "Content-Type": "application/json"}
            res = self._http.post(
                url,
                headers=headers,
                json={"bucketId": self._bucket, "sourceKey": from_path, "destinationKey": to_path},
            )
            json_body = res.json()
            if res.is_error:
                return SingleResult(data=None, error=json_body.get("error", "Copy failed"))
            return SingleResult(data={"path": to_path}, error=None)
        except Exception as err:  # noqa: BLE001
            return SingleResult(data=None, error=str(err))


class StorageClient:
    def __init__(
        self,
        http: httpx.Client,
        base_url: str,
        api_key: str,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self._http = http
        self._base_url = base_url
        self._headers = {"Authorization": f"Bearer {api_key}", **(extra_headers or {})}

    def from_(self, bucket: str) -> StorageBucketClient:
        return StorageBucketClient(self._http, self._base_url, self._headers, bucket)

    def create_bucket(
        self,
        name: str,
        public: bool = False,
        file_size_limit: Optional[int] = None,
        allowed_mime_types: Optional[List[str]] = None,
    ) -> SingleResult[Bucket]:
        try:
            url = f"{self._base_url}/api/storage/v1/bucket"
            headers = {**self._headers, "Content-Type": "application/json"}
            res = self._http.post(
                url,
                headers=headers,
                json={
                    "name": name,
                    "id": name,
                    "public": public,
                    "file_size_limit": file_size_limit,
                    "allowed_mime_types": allowed_mime_types,
                },
            )
            json_body = res.json()
            if res.is_error:
                return SingleResult(data=None, error=json_body.get("error", "Create bucket failed"))
            return SingleResult(data=Bucket.from_dict(json_body["data"]), error=None)
        except Exception as err:  # noqa: BLE001
            return SingleResult(data=None, error=str(err))

    def get_bucket(self, bucket_id: str) -> SingleResult[Bucket]:
        try:
            url = f"{self._base_url}/api/storage/v1/bucket/{bucket_id}"
            res = self._http.get(url, headers=self._headers)
            json_body = res.json()
            if res.is_error:
                return SingleResult(data=None, error=json_body.get("error", "Get bucket failed"))
            return SingleResult(data=Bucket.from_dict(json_body["data"]), error=None)
        except Exception as err:  # noqa: BLE001
            return SingleResult(data=None, error=str(err))

    def list_buckets(self) -> QueryResult[Bucket]:
        try:
            url = f"{self._base_url}/api/storage/v1/bucket"
            res = self._http.get(url, headers=self._headers)
            json_body = res.json()
            if res.is_error:
                return QueryResult(
                    data=None, count=None, error=json_body.get("error", "List buckets failed")
                )
            data = [Bucket.from_dict(b) for b in json_body.get("data", [])]
            return QueryResult(data=data, count=len(data), error=None)
        except Exception as err:  # noqa: BLE001
            return QueryResult(data=None, count=None, error=str(err))

    def update_bucket(
        self,
        bucket_id: str,
        public: Optional[bool] = None,
        file_size_limit: Optional[int] = None,
        allowed_mime_types: Optional[List[str]] = None,
    ) -> SingleResult[Bucket]:
        try:
            url = f"{self._base_url}/api/storage/v1/bucket/{bucket_id}"
            headers = {**self._headers, "Content-Type": "application/json"}
            res = self._http.put(
                url,
                headers=headers,
                json={
                    "public": public,
                    "file_size_limit": file_size_limit,
                    "allowed_mime_types": allowed_mime_types,
                },
            )
            json_body = res.json()
            if res.is_error:
                return SingleResult(data=None, error=json_body.get("error", "Update bucket failed"))
            return SingleResult(data=Bucket.from_dict(json_body["data"]), error=None)
        except Exception as err:  # noqa: BLE001
            return SingleResult(data=None, error=str(err))

    def delete_bucket(self, bucket_id: str) -> Dict[str, Optional[str]]:
        try:
            url = f"{self._base_url}/api/storage/v1/bucket/{bucket_id}"
            res = self._http.delete(url, headers=self._headers)
            json_body = res.json()
            if res.is_error:
                return {"error": json_body.get("error", "Delete bucket failed")}
            return {"error": None}
        except Exception as err:  # noqa: BLE001
            return {"error": str(err)}

    def empty_bucket(self, bucket_id: str) -> Dict[str, Optional[str]]:
        try:
            url = f"{self._base_url}/api/storage/v1/bucket/{bucket_id}/empty"
            res = self._http.post(url, headers=self._headers)
            json_body = res.json()
            if res.is_error:
                return {"error": json_body.get("error", "Empty bucket failed")}
            return {"error": None}
        except Exception as err:  # noqa: BLE001
            return {"error": str(err)}
