from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from dataclasses import (
    dataclass,
)

from typing import (
    Any,
    Mapping,
)


DEFAULT_BASE_URL = (
    "https://api.bcfy.io"
)

DEFAULT_TIMEOUT_SECONDS = 15.0

DEFAULT_JWT_TTL_SECONDS = 3600

MAX_JWT_TTL_SECONDS = 86400


ENV_BASE_URL = (
    "BROADCASTIFY_CALLS_BASE_URL"
)

ENV_KEY_ID = (
    "BROADCASTIFY_CALLS_KEY_ID"
)

ENV_SIGNING_SECRET = (
    "BROADCASTIFY_CALLS_SIGNING_SECRET"
)

ENV_ISSUER = (
    "BROADCASTIFY_CALLS_ISSUER"
)

ENV_JWT_TTL_SECONDS = (
    "BROADCASTIFY_CALLS_JWT_TTL_SECONDS"
)

ENV_TIMEOUT_SECONDS = (
    "BROADCASTIFY_CALLS_TIMEOUT_SECONDS"
)


ENV_PLAYLIST_PATH = (
    "BROADCASTIFY_CALLS_PLAYLIST_PATH"
)

ENV_LIVE_CALLS_PATH = (
    "BROADCASTIFY_CALLS_LIVE_CALLS_PATH"
)

ENV_CALL_PATH = (
    "BROADCASTIFY_CALLS_CALL_PATH"
)

ENV_GROUP_ARCHIVE_PATH = (
    "BROADCASTIFY_CALLS_GROUP_ARCHIVE_PATH"
)


class BroadcastifyCallsError(
    RuntimeError
):
    pass


class BroadcastifyCallsConfigurationError(
    BroadcastifyCallsError
):
    pass


class BroadcastifyCallsHTTPError(
    BroadcastifyCallsError
):
    def __init__(
        self,
        status_code: int,
        message: str,
        response_body: str | None = None,
    ) -> None:
        super().__init__(
            message
        )

        self.status_code = (
            status_code
        )

        self.response_body = (
            response_body
        )


def _base64url_encode(
    value: bytes,
) -> str:
    return (
        base64.urlsafe_b64encode(
            value
        )
        .decode(
            "ascii"
        )
        .rstrip(
            "="
        )
    )


@dataclass(
    frozen=True,
)
class BroadcastifyCallsConfig:
    base_url: str

    key_id: str

    signing_secret: str

    issuer: str

    jwt_ttl_seconds: int = (
        DEFAULT_JWT_TTL_SECONDS
    )

    playlist_path: str = ""

    live_calls_path: str = ""

    call_path: str = ""

    group_archive_path: str = ""

    timeout_seconds: float = (
        DEFAULT_TIMEOUT_SECONDS
    )


    @classmethod
    def from_environment(
        cls,
    ) -> "BroadcastifyCallsConfig":
        timeout_raw = (
            os.getenv(
                ENV_TIMEOUT_SECONDS,
                str(
                    DEFAULT_TIMEOUT_SECONDS
                ),
            )
        )

        jwt_ttl_raw = (
            os.getenv(
                ENV_JWT_TTL_SECONDS,
                str(
                    DEFAULT_JWT_TTL_SECONDS
                ),
            )
        )


        try:
            timeout_seconds = float(
                timeout_raw
            )

        except ValueError as error:
            raise (
                BroadcastifyCallsConfigurationError(
                    (
                        "Invalid "
                        f"{ENV_TIMEOUT_SECONDS}"
                    )
                )
            ) from error


        try:
            jwt_ttl_seconds = int(
                jwt_ttl_raw
            )

        except ValueError as error:
            raise (
                BroadcastifyCallsConfigurationError(
                    (
                        "Invalid "
                        f"{ENV_JWT_TTL_SECONDS}"
                    )
                )
            ) from error


        return cls(
            base_url=(
                os.getenv(
                    ENV_BASE_URL,
                    DEFAULT_BASE_URL,
                )
                .strip()
            ),

            key_id=(
                os.getenv(
                    ENV_KEY_ID,
                    "",
                )
                .strip()
            ),

            signing_secret=(
                os.getenv(
                    ENV_SIGNING_SECRET,
                    "",
                )
                .strip()
            ),

            issuer=(
                os.getenv(
                    ENV_ISSUER,
                    "",
                )
                .strip()
            ),

            jwt_ttl_seconds=(
                jwt_ttl_seconds
            ),

            playlist_path=(
                os.getenv(
                    ENV_PLAYLIST_PATH,
                    "",
                )
                .strip()
            ),

            live_calls_path=(
                os.getenv(
                    ENV_LIVE_CALLS_PATH,
                    "",
                )
                .strip()
            ),

            call_path=(
                os.getenv(
                    ENV_CALL_PATH,
                    "",
                )
                .strip()
            ),

            group_archive_path=(
                os.getenv(
                    ENV_GROUP_ARCHIVE_PATH,
                    "",
                )
                .strip()
            ),

            timeout_seconds=(
                timeout_seconds
            ),
        )


    def validate_transport(
        self,
    ) -> None:
        missing: list[str] = []


        if not self.base_url:
            missing.append(
                ENV_BASE_URL
            )


        if not self.key_id:
            missing.append(
                ENV_KEY_ID
            )


        if not self.signing_secret:
            missing.append(
                ENV_SIGNING_SECRET
            )


        if not self.issuer:
            missing.append(
                ENV_ISSUER
            )


        if missing:
            raise (
                BroadcastifyCallsConfigurationError(
                    (
                        "Broadcastify Calls API "
                        "is not configured. Missing: "
                        + ", ".join(
                            missing
                        )
                    )
                )
            )


        parsed = (
            urllib.parse.urlparse(
                self.base_url
            )
        )


        if (
            parsed.scheme
            not in (
                "http",
                "https",
            )
        ):
            raise (
                BroadcastifyCallsConfigurationError(
                    (
                        f"{ENV_BASE_URL} "
                        "must use HTTP or HTTPS"
                    )
                )
            )


        if not parsed.netloc:
            raise (
                BroadcastifyCallsConfigurationError(
                    (
                        f"{ENV_BASE_URL} "
                        "must contain a host"
                    )
                )
            )


        if (
            self.timeout_seconds
            <= 0
        ):
            raise (
                BroadcastifyCallsConfigurationError(
                    (
                        "Broadcastify Calls timeout "
                        "must be greater than zero"
                    )
                )
            )


        if (
            self.jwt_ttl_seconds
            <= 0
        ):
            raise (
                BroadcastifyCallsConfigurationError(
                    (
                        "Broadcastify Calls JWT TTL "
                        "must be greater than zero"
                    )
                )
            )


        if (
            self.jwt_ttl_seconds
            >
            MAX_JWT_TTL_SECONDS
        ):
            raise (
                BroadcastifyCallsConfigurationError(
                    (
                        "Broadcastify Calls JWT TTL "
                        "must not exceed "
                        f"{MAX_JWT_TTL_SECONDS} seconds"
                    )
                )
            )


    def transport_configured(
        self,
    ) -> bool:
        try:
            self.validate_transport()

        except BroadcastifyCallsConfigurationError:
            return False

        return True


class BroadcastifyCallsClient:
    def __init__(
        self,
        config:
            BroadcastifyCallsConfig
            | None = None,
    ) -> None:
        self.config = (
            config
            or
            BroadcastifyCallsConfig
            .from_environment()
        )


    @property
    def configured(
        self,
    ) -> bool:
        return (
            self.config
            .transport_configured()
        )


    def configuration_status(
        self,
    ) -> dict[str, Any]:
        jwt_auth_configured = bool(
            self.config.key_id
            and
            self.config.signing_secret
            and
            self.config.issuer
        )


        return {
            "configured":
                self.config
                .transport_configured(),

            "base_url_configured":
                bool(
                    self.config
                    .base_url
                ),

            "key_id_configured":
                bool(
                    self.config
                    .key_id
                ),

            "signing_secret_configured":
                bool(
                    self.config
                    .signing_secret
                ),

            "issuer_configured":
                bool(
                    self.config
                    .issuer
                ),

            "jwt_auth_configured":
                jwt_auth_configured,

            "jwt_ttl_seconds":
                self.config
                .jwt_ttl_seconds,

            #
            # Compatibility fields for the
            # current sources.py / frontend.
            #
            # These can be removed after the
            # source API status contract is
            # migrated to the JWT field names.
            #
            "api_key_configured":
                bool(
                    self.config
                    .signing_secret
                ),

            "auth_header_configured":
                jwt_auth_configured,

            "playlist_endpoint_configured":
                bool(
                    self.config
                    .playlist_path
                ),

            "live_calls_endpoint_configured":
                bool(
                    self.config
                    .live_calls_path
                ),

            "call_endpoint_configured":
                bool(
                    self.config
                    .call_path
                ),

            "group_archive_endpoint_configured":
                bool(
                    self.config
                    .group_archive_path
                ),
        }


    def mint_jwt(
        self,
        *,
        now:
            int
            | None = None,
    ) -> str:
        self.config.validate_transport()


        issued_at = (
            int(
                time.time()
            )
            if now is None
            else int(
                now
            )
        )


        expires_at = (
            issued_at
            +
            self.config
            .jwt_ttl_seconds
        )


        header = {
            "alg":
                "HS256",

            "typ":
                "JWT",

            "kid":
                self.config
                .key_id,
        }


        payload = {
            "iss":
                self.config
                .issuer,

            "iat":
                issued_at,

            "exp":
                expires_at,
        }


        encoded_header = (
            _base64url_encode(
                json.dumps(
                    header,
                    separators=(
                        ",",
                        ":",
                    ),
                    ensure_ascii=False,
                )
                .encode(
                    "utf-8"
                )
            )
        )


        encoded_payload = (
            _base64url_encode(
                json.dumps(
                    payload,
                    separators=(
                        ",",
                        ":",
                    ),
                    ensure_ascii=False,
                )
                .encode(
                    "utf-8"
                )
            )
        )


        signing_input = (
            f"{encoded_header}."
            f"{encoded_payload}"
        )


        signature = (
            hmac.new(
                self.config
                .signing_secret
                .encode(
                    "utf-8"
                ),

                signing_input
                .encode(
                    "ascii"
                ),

                hashlib.sha256,
            )
            .digest()
        )


        encoded_signature = (
            _base64url_encode(
                signature
            )
        )


        return (
            f"{signing_input}."
            f"{encoded_signature}"
        )


    def _headers(
        self,
        *,
        accept: str,
        authenticated: bool,
    ) -> dict[str, str]:
        headers = {
            "Accept":
                accept,

            "User-Agent":
                (
                    "RF-Gateway/0.11 "
                    "(Broadcastify Calls Client)"
                ),
        }


        if authenticated:
            token = (
                self.mint_jwt()
            )

            headers[
                "Authorization"
            ] = (
                f"Bearer {token}"
            )


        return headers


    def _build_url(
        self,
        path: str,
        query:
            Mapping[
                str,
                Any,
            ]
            | None = None,
    ) -> str:
        if (
            path.startswith(
                "http://"
            )
            or
            path.startswith(
                "https://"
            )
        ):
            url = path

        else:
            self.config.validate_transport()


            base_url = (
                self.config
                .base_url
                .rstrip(
                    "/"
                )
            )


            url = (
                base_url
                + "/"
                + path.lstrip(
                    "/"
                )
            )


        if query:
            normalized_query: dict[
                str,
                str,
            ] = {}


            for (
                key,
                value,
            ) in query.items():
                if value is None:
                    continue

                normalized_query[
                    key
                ] = str(
                    value
                )


            if normalized_query:
                separator = (
                    "&"
                    if "?" in url
                    else "?"
                )

                url = (
                    url
                    + separator
                    + urllib.parse.urlencode(
                        normalized_query
                    )
                )


        return url


    def _is_api_origin(
        self,
        url: str,
    ) -> bool:
        base = (
            urllib.parse.urlparse(
                self.config
                .base_url
            )
        )

        target = (
            urllib.parse.urlparse(
                url
            )
        )


        return bool(
            base.scheme.lower()
            ==
            target.scheme.lower()
            and
            base.netloc.lower()
            ==
            target.netloc.lower()
        )


    def _decode_error_body(
        self,
        body: bytes,
    ) -> str | None:
        if not body:
            return None


        return (
            body.decode(
                "utf-8",
                errors="replace",
            )
        )


    def _request_bytes(
        self,
        *,
        method: str,
        path: str,
        query:
            Mapping[
                str,
                Any,
            ]
            | None = None,
        accept: str = "*/*",
        authenticated:
            bool
            | None = None,
    ) -> tuple[
        bytes,
        Mapping[
            str,
            str,
        ],
    ]:
        url = self._build_url(
            path,
            query,
        )


        if authenticated is None:
            authenticated = (
                self._is_api_origin(
                    url
                )
            )


        request = (
            urllib.request.Request(
                url,
                method=method,
                headers=(
                    self._headers(
                        accept=accept,
                        authenticated=authenticated,
                    )
                ),
            )
        )


        try:
            with (
                urllib.request.urlopen(
                    request,
                    timeout=(
                        self.config
                        .timeout_seconds
                    ),
                )
                as response
            ):
                return (
                    response.read(),
                    dict(
                        response.headers
                    ),
                )


        except urllib.error.HTTPError as error:
            try:
                body = error.read()

            except Exception:
                body = b""


            decoded_body = (
                self._decode_error_body(
                    body
                )
            )


            raise (
                BroadcastifyCallsHTTPError(
                    status_code=(
                        error.code
                    ),

                    message=(
                        "Broadcastify Calls API "
                        f"returned HTTP {error.code}"
                    ),

                    response_body=(
                        decoded_body
                    ),
                )
            ) from error


        except urllib.error.URLError as error:
            raise (
                BroadcastifyCallsError(
                    (
                        "Broadcastify Calls API "
                        "connection failed: "
                        f"{error.reason}"
                    )
                )
            ) from error


        except TimeoutError as error:
            raise (
                BroadcastifyCallsError(
                    (
                        "Broadcastify Calls API "
                        "request timed out"
                    )
                )
            ) from error


    def _request_json(
        self,
        *,
        method: str,
        path: str,
        query:
            Mapping[
                str,
                Any,
            ]
            | None = None,
    ) -> Any:
        body, _headers = (
            self._request_bytes(
                method=method,
                path=path,
                query=query,
                accept=(
                    "application/json"
                ),
                authenticated=True,
            )
        )


        try:
            return json.loads(
                body.decode(
                    "utf-8",
                    errors="strict",
                )
            )

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            raise (
                BroadcastifyCallsError(
                    (
                        "Broadcastify Calls API "
                        "returned invalid JSON"
                    )
                )
            ) from error


    def _require_endpoint(
        self,
        *,
        path_template: str,
        environment_name: str,
    ) -> str:
        if not path_template:
            raise (
                BroadcastifyCallsConfigurationError(
                    (
                        "Broadcastify Calls endpoint "
                        "is not configured. Set "
                        f"{environment_name}"
                    )
                )
            )


        return path_template


    def get_playlist(
        self,
        playlist_uuid: str,
    ) -> Any:
        template = (
            self._require_endpoint(
                path_template=(
                    self.config
                    .playlist_path
                ),

                environment_name=(
                    ENV_PLAYLIST_PATH
                ),
            )
        )


        path = template.format(
            playlist_uuid=(
                urllib.parse.quote(
                    playlist_uuid,
                    safe="",
                )
            ),
        )


        return self._request_json(
            method="GET",
            path=path,
        )


    def get_live_calls(
        self,
        *,
        playlist_uuid:
            str
            | None = None,
        group_id:
            str
            | None = None,
        extra_query:
            Mapping[
                str,
                Any,
            ]
            | None = None,
    ) -> Any:
        path = (
            self._require_endpoint(
                path_template=(
                    self.config
                    .live_calls_path
                ),

                environment_name=(
                    ENV_LIVE_CALLS_PATH
                ),
            )
        )


        query: dict[
            str,
            Any,
        ] = {}


        if extra_query:
            query.update(
                extra_query
            )


        if playlist_uuid:
            if (
                "playlist_uuid"
                in query
            ):
                raise ValueError(
                    (
                        "playlist_uuid cannot be "
                        "provided both as an argument "
                        "and in extra_query"
                    )
                )

            query[
                "playlist_uuid"
            ] = playlist_uuid


        if group_id:
            if (
                "groups"
                in query
            ):
                raise ValueError(
                    (
                        "group_id cannot be provided "
                        "together with groups in "
                        "extra_query"
                    )
                )

            query[
                "groups"
            ] = group_id


        selector_names = (
            "playlist_uuid",
            "sid",
            "nodeId",
            "groups",
        )


        selected = [
            name
            for name in selector_names
            if (
                query.get(
                    name
                )
                not in (
                    None,
                    "",
                )
            )
        ]


        if len(
            selected
        ) != 1:
            raise ValueError(
                (
                    "Broadcastify Live Calls requires "
                    "exactly one selector: "
                    "playlist_uuid, sid, nodeId, "
                    "or groups"
                )
            )


        if (
            "groups"
            in selected
        ):
            groups_value = str(
                query[
                    "groups"
                ]
            )

            groups = [
                item.strip()
                for item in (
                    groups_value
                    .split(
                        ","
                    )
                )
                if item.strip()
            ]


            if not groups:
                raise ValueError(
                    (
                        "groups cannot be empty"
                    )
                )


            if len(
                groups
            ) > 5:
                raise ValueError(
                    (
                        "Broadcastify Live Calls "
                        "supports at most 5 groups"
                    )
                )


            query[
                "groups"
            ] = ",".join(
                groups
            )


        if (
            query.get(
                "init"
            )
            not in (
                None,
                "",
                0,
                "0",
            )
            and
            query.get(
                "pos"
            )
            not in (
                None,
                "",
            )
        ):
            raise ValueError(
                (
                    "Broadcastify Live Calls init "
                    "and pos cannot be used together"
                )
            )


        if (
            selected[
                0
            ]
            ==
            "playlist_uuid"
            and
            query.get(
                "init"
            )
            not in (
                None,
                "",
                0,
                "0",
            )
        ):
            raise ValueError(
                (
                    "Broadcastify Live Calls init=1 "
                    "is not valid for playlist_uuid"
                )
            )


        return self._request_json(
            method="GET",
            path=path,
            query=query,
        )


    def get_call(
        self,
        *,
        group_id: str,
        ts: int,
    ) -> Any:
        template = (
            self._require_endpoint(
                path_template=(
                    self.config
                    .call_path
                ),

                environment_name=(
                    ENV_CALL_PATH
                ),
            )
        )


        path = template.format(
            group_id=(
                urllib.parse.quote(
                    group_id,
                    safe="",
                )
            ),

            ts=str(
                int(
                    ts
                )
            ),
        )


        return self._request_json(
            method="GET",
            path=path,
        )


    def get_group_archive(
        self,
        *,
        group_id: str,
        start_ts: int,
        end_ts: int,
        extra_query:
            Mapping[
                str,
                Any,
            ]
            | None = None,
    ) -> Any:
        template = (
            self._require_endpoint(
                path_template=(
                    self.config
                    .group_archive_path
                ),

                environment_name=(
                    ENV_GROUP_ARCHIVE_PATH
                ),
            )
        )


        path = template.format(
            group_id=(
                urllib.parse.quote(
                    group_id,
                    safe="",
                )
            ),

            start_ts=str(
                int(
                    start_ts
                )
            ),

            end_ts=str(
                int(
                    end_ts
                )
            ),
        )


        query: dict[
            str,
            Any,
        ] = {}


        if extra_query:
            query.update(
                extra_query
            )


        return self._request_json(
            method="GET",
            path=path,
            query=(
                query
                or None
            ),
        )


    def download_audio(
        self,
        audio_url: str,
    ) -> tuple[
        bytes,
        str | None,
    ]:
        if not audio_url:
            raise ValueError(
                "audio_url cannot be empty"
            )


        body, headers = (
            self._request_bytes(
                method="GET",
                path=audio_url,
                accept=(
                    "audio/*,"
                    "application/octet-stream"
                ),
                authenticated=None,
            )
        )


        content_type = (
            headers.get(
                "Content-Type"
            )
        )


        return (
            body,
            content_type,
        )


broadcastify_calls_client = (
    BroadcastifyCallsClient()
)