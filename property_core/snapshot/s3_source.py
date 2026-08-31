"""Read-only Tigris delivery, signed by the official AWS SDK.

The existing HTTP stream/verifier retains ownership of download budgets and
length checks. Credentials are headers, never URLs. No credential discovery,
metadata-service lookup, retries or cloud writes occur in this source.
"""

from __future__ import annotations

import ipaddress
import re
import urllib.parse
import urllib.request

from property_core.snapshot.errors import SnapshotExtraMissingError, SnapshotSourceError
from property_core.snapshot.models import validate_component
from property_core.snapshot.source import HttpObjectSource

TIGRIS_ENDPOINT = "https://t3.storage.dev"


def _component(value: str, field: str) -> str:
    try:
        return validate_component(value, field, reserved=False)
    except ValueError:
        # Do not echo arbitrary input (which might itself contain credentials).
        raise SnapshotSourceError(f"{field} must be a safe path component") from None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        fp.close()
        raise SnapshotSourceError("snapshot source redirected; credentials not forwarded")


class TigrisObjectSource(HttpObjectSource):
    """A bucket/prefix-scoped signed GET source; no write interface.

    Production uses the fixed Tigris HTTPS endpoint. An explicit loopback HTTP
    endpoint is permitted for real-boundary tests; no endpoint comes from a
    manifest or an environment variable.
    """

    def __init__(self, bucket: str, *, access_key: str, secret_key: str,
                 prefix: str = "ppd", endpoint: str = TIGRIS_ENDPOINT,
                 socket_timeout: float = 10.0):
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", bucket):
            raise SnapshotSourceError("invalid snapshot bucket name")
        if not access_key or not secret_key:
            raise SnapshotSourceError("snapshot access key and secret are required")
        parts = [_component(part, "snapshot prefix")
                 for part in prefix.split("/")] if prefix else []
        parsed = urllib.parse.urlsplit(endpoint)
        try:
            loopback = ipaddress.ip_address(parsed.hostname or "").is_loopback
        except ValueError:
            loopback = False
        if endpoint != TIGRIS_ENDPOINT and not (
                parsed.scheme == "http" and loopback and parsed.path == ""
                and not parsed.username and not parsed.password
                and not parsed.query and not parsed.fragment):
            raise SnapshotSourceError("snapshot endpoint must be the Tigris HTTPS endpoint")
        try:
            from botocore.auth import S3SigV4Auth
            from botocore.awsrequest import AWSRequest
            from botocore.credentials import Credentials
        except ImportError as exc:
            raise SnapshotExtraMissingError(
                package="botocore", feature="private snapshot delivery"
            ) from exc
        self._signer = S3SigV4Auth(Credentials(access_key, secret_key), "s3", "auto")
        self._aws_request = AWSRequest
        self._opener = urllib.request.build_opener(_NoRedirect())
        base = "/".join([endpoint, bucket] + parts)
        super().__init__(base, socket_timeout=socket_timeout)

    def _request(self, name: str):
        request = super()._request(_component(name, "snapshot object"))
        signed = self._aws_request(method="GET", url=request.full_url,
                                   headers=dict(request.header_items()))
        self._signer.add_auth(signed)
        for key, value in signed.headers.items():
            request.add_header(key, value)
        return request

    def _open(self, name: str):
        return self._opener.open(self._request(name), timeout=self.socket_timeout)
