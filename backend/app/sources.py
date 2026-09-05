from __future__ import annotations

import html
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid

from copy import deepcopy
from datetime import (
    datetime,
    timezone,
)

from pathlib import Path

from fastapi import (
    APIRouter,
    HTTPException,
)

from pydantic import (
    BaseModel,
    Field,
)

from app.broadcastify_calls_client import (
    broadcastify_calls_client,
)


router = APIRouter(
    prefix="/api/sources",
    tags=["sources"],
)


DATA_DIR = (
    Path(__file__)
    .resolve()
    .parent
    .parent
    / "data"
)


SOURCES_FILE = (
    DATA_DIR
    / "sources.json"
)


BROADCASTIFY_HOSTS = {
    "broadcastify.com",
    "www.broadcastify.com",
}


PLAYLIST_PATH = (
    "/calls/playlists/"
)


UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)


TITLE_PATTERN = re.compile(
    r"<title[^>]*>(.*?)</title>",
    flags=(
        re.IGNORECASE
        | re.DOTALL
    ),
)


H1_PATTERN = re.compile(
    r"<h[1-4][^>]*>"
    r"(.*?)"
    r"</h[1-4]>",
    flags=(
        re.IGNORECASE
        | re.DOTALL
    ),
)


TAG_PATTERN = re.compile(
    r"<[^>]+>"
)


class BroadcastifyProbeRequest(
    BaseModel
):
    url: str = Field(
        min_length=1,
        max_length=2048,
    )


class SourceCreateRequest(
    BaseModel
):
    name: str = Field(
        min_length=1,
        max_length=120,
    )

    type: str = Field(
        default=(
            "broadcastify_calls"
        ),
    )

    url: str = Field(
        min_length=1,
        max_length=2048,
    )


_store_lock = (
    threading.Lock()
)


def utc_now() -> str:
    return (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )


def ensure_storage() -> None:
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if SOURCES_FILE.exists():
        return

    SOURCES_FILE.write_text(
        json.dumps(
            {
                "version": 1,
                "sources": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def load_store() -> dict:
    ensure_storage()

    with _store_lock:
        try:
            return json.loads(
                SOURCES_FILE.read_text(
                    encoding="utf-8"
                )
            )

        except (
            OSError,
            json.JSONDecodeError,
        ) as error:
            raise RuntimeError(
                (
                    "Unable to read "
                    "sources store: "
                    f"{error}"
                )
            ) from error


def save_store(
    store: dict,
) -> None:
    ensure_storage()

    temporary_file = (
        SOURCES_FILE
        .with_suffix(
            ".json.tmp"
        )
    )

    with _store_lock:
        temporary_file.write_text(
            json.dumps(
                store,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        temporary_file.replace(
            SOURCES_FILE
        )


def normalize_text(
    value: str,
) -> str:
    value = (
        TAG_PATTERN.sub(
            " ",
            value,
        )
    )

    value = html.unescape(
        value
    )

    value = " ".join(
        value.split()
    )

    return value.strip()


def parse_broadcastify_playlist_url(
    url: str,
) -> dict:
    parsed = (
        urllib.parse.urlparse(
            url.strip()
        )
    )


    if (
        parsed.scheme
        not in (
            "http",
            "https",
        )
    ):
        raise ValueError(
            (
                "Broadcastify URL "
                "must use HTTP or HTTPS"
            )
        )


    hostname = (
        parsed.hostname
        or ""
    ).lower()


    if (
        hostname
        not in BROADCASTIFY_HOSTS
    ):
        raise ValueError(
            (
                "URL is not a Broadcastify "
                "playlist URL"
            )
        )


    if (
        not parsed.path.startswith(
            PLAYLIST_PATH
        )
    ):
        raise ValueError(
            (
                "Expected Broadcastify Calls "
                "playlist URL"
            )
        )


    query = (
        urllib.parse.parse_qs(
            parsed.query
        )
    )


    playlist_uuid = (
        query.get(
            "uuid",
            [None],
        )[0]
    )


    if not playlist_uuid:
        raise ValueError(
            (
                "Broadcastify playlist URL "
                "does not contain uuid"
            )
        )


    if not UUID_PATTERN.fullmatch(
        playlist_uuid
    ):
        raise ValueError(
            (
                "Invalid Broadcastify "
                "playlist UUID"
            )
        )


    requested_view = (
        query.get(
            "view",
            ["list"],
        )[0]
        or
        "list"
    )


    if (
        requested_view
        not in (
            "list",
            "console",
        )
    ):
        requested_view = (
            "list"
        )


    canonical_url = (
        "https://www.broadcastify.com"
        "/calls/playlists/"
        f"?uuid={playlist_uuid}"
        f"&view={requested_view}"
    )


    return {
        "provider":
            "broadcastify",

        "source_type":
            "broadcastify_calls",

        "playlist_uuid":
            playlist_uuid,

        "view":
            requested_view,

        "canonical_url":
            canonical_url,
    }


def extract_page_name(
    page: str,
) -> str | None:
    title_match = (
        TITLE_PATTERN.search(
            page
        )
    )


    if title_match:
        title = normalize_text(
            title_match.group(1)
        )


        for suffix in (
            " - Broadcastify",
            " | Broadcastify",
        ):
            if title.endswith(
                suffix
            ):
                title = (
                    title[
                        :-len(
                            suffix
                        )
                    ]
                    .strip()
                )


        if (
            title
            and
            title.lower()
            not in (
                "broadcastify",
                "broadcastify calls",
            )
        ):
            return title


    for match in (
        H1_PATTERN.finditer(
            page
        )
    ):
        heading = normalize_text(
            match.group(1)
        )


        if heading.lower().startswith(
            "playlist:"
        ):
            heading = (
                heading.split(
                    ":",
                    1,
                )[1]
                .strip()
            )


        if heading:
            return heading


    return None


def fetch_playlist_page(
    canonical_url: str,
) -> dict:
    request = (
        urllib.request.Request(
            canonical_url,
            headers={
                "User-Agent":
                    (
                        "RF-Gateway/0.11 "
                        "(Broadcastify Source Probe)"
                    ),

                "Accept":
                    (
                        "text/html,"
                        "application/xhtml+xml"
                    ),
            },
        )
    )


    try:
        with urllib.request.urlopen(
            request,
            timeout=10,
        ) as response:
            status_code = (
                response.status
            )

            raw = response.read(
                2 * 1024 * 1024
            )

            final_url = (
                response.geturl()
            )


    except urllib.error.HTTPError as error:
        return {
            "reachable":
                False,

            "http_status":
                error.code,

            "page_name":
                None,

            "final_url":
                canonical_url,

            "error":
                f"HTTP {error.code}",
        }


    except urllib.error.URLError as error:
        return {
            "reachable":
                False,

            "http_status":
                None,

            "page_name":
                None,

            "final_url":
                canonical_url,

            "error":
                str(
                    error.reason
                ),
        }


    except TimeoutError:
        return {
            "reachable":
                False,

            "http_status":
                None,

            "page_name":
                None,

            "final_url":
                canonical_url,

            "error":
                (
                    "Connection timed out"
                ),
        }


    page = raw.decode(
        "utf-8",
        errors="replace",
    )


    page_name = (
        extract_page_name(
            page
        )
    )


    lower_page = (
        page.lower()
    )


    looks_like_playlist = (
        "playlist:"
        in lower_page
        or
        "broadcastify calls"
        in lower_page
        or
        "calls/playlists"
        in lower_page
    )


    return {
        "reachable":
            bool(
                status_code == 200
                and
                looks_like_playlist
            ),

        "http_status":
            status_code,

        "page_name":
            page_name,

        "final_url":
            final_url,

        "error":
            (
                None
                if looks_like_playlist
                else
                (
                    "Page did not look like "
                    "a Broadcastify Calls "
                    "playlist"
                )
            ),
    }


def get_audio_api_status() -> dict:
    status = (
        broadcastify_calls_client
        .configuration_status()
    )


    jwt_configured = bool(
        status.get(
            "configured",
            False,
        )
        and
        status.get(
            "jwt_auth_configured",
            False,
        )
    )


    jwt_generation_ready = False

    jwt_generation_error = None


    if jwt_configured:
        try:
            token = (
                broadcastify_calls_client
                .mint_jwt()
            )


            jwt_generation_ready = bool(
                len(
                    token.split(
                        "."
                    )
                )
                == 3
            )


            if not jwt_generation_ready:
                jwt_generation_error = (
                    "Generated JWT does not "
                    "contain three parts"
                )


        except Exception as error:
            jwt_generation_error = str(
                error
            )


    endpoint_templates_configured = bool(
        status.get(
            "playlist_endpoint_configured",
            False,
        )
        and
        status.get(
            "live_calls_endpoint_configured",
            False,
        )
        and
        status.get(
            "call_endpoint_configured",
            False,
        )
    )


    live_playback_configured = bool(
        jwt_generation_ready
        and
        endpoint_templates_configured
    )


    return {
        **status,

        "jwt_configured":
            jwt_configured,

        "jwt_generation_ready":
            jwt_generation_ready,

        "jwt_generation_error":
            jwt_generation_error,

        "endpoint_templates_configured":
            endpoint_templates_configured,

        "live_playback_configured":
            live_playback_configured,
    }


def get_playback_state(
    audio_api: dict,
) -> str:
    if audio_api.get(
        "live_playback_configured",
        False,
    ):
        return "configured"


    if audio_api.get(
        "jwt_generation_error"
    ):
        return "jwt_error"


    if audio_api.get(
        "jwt_generation_ready",
        False,
    ):
        return "endpoints_not_configured"


    return "not_configured"


def apply_current_audio_api_status(
    source: dict,
) -> dict:
    current = deepcopy(
        source
    )


    probe = current.get(
        "probe"
    )


    if not isinstance(
        probe,
        dict,
    ):
        probe = {}


    audio_api = (
        get_audio_api_status()
    )


    probe[
        "audio_api_configured"
    ] = bool(
        audio_api.get(
            "live_playback_configured",
            False,
        )
    )


    probe[
        "playback_state"
    ] = (
        get_playback_state(
            audio_api
        )
    )


    probe[
        "playback_model"
    ] = (
        "discrete_calls"
    )


    probe[
        "audio_api"
    ] = audio_api


    current[
        "probe"
    ] = probe


    return current


def probe_broadcastify(
    url: str,
) -> dict:
    parsed = (
        parse_broadcastify_playlist_url(
            url
        )
    )


    page_probe = (
        fetch_playlist_page(
            parsed[
                "canonical_url"
            ]
        )
    )


    audio_api = (
        get_audio_api_status()
    )


    audio_api_configured = bool(
        audio_api.get(
            "live_playback_configured",
            False,
        )
    )


    return {
        **parsed,

        "reachable":
            page_probe[
                "reachable"
            ],

        "http_status":
            page_probe[
                "http_status"
            ],

        "page_name":
            page_probe[
                "page_name"
            ],

        "final_url":
            page_probe[
                "final_url"
            ],

        "error":
            page_probe[
                "error"
            ],

        "audio_api_configured":
            audio_api_configured,

        "playback_state":
            get_playback_state(
                audio_api
            ),

        "playback_model":
            "discrete_calls",

        "audio_api":
            audio_api,

        "probed_at":
            utc_now(),
    }


def get_source_or_404(
    source_id: str,
) -> dict:
    store = (
        load_store()
    )


    for source in store.get(
        "sources",
        [],
    ):
        if (
            source.get(
                "id"
            )
            == source_id
        ):
            return (
                apply_current_audio_api_status(
                    source
                )
            )


    raise HTTPException(
        status_code=404,
        detail="Source not found",
    )


@router.get("")
def list_sources():
    store = (
        load_store()
    )


    sources = (
        store.get(
            "sources",
            [],
        )
    )


    return {
        "version":
            store.get(
                "version",
                1,
            ),

        "count":
            len(
                sources
            ),

        "sources":
            [
                apply_current_audio_api_status(
                    source
                )
                for source
                in sources
            ],
    }


@router.get(
    "/broadcastify/api-status"
)
def broadcastify_api_status():
    status = (
        get_audio_api_status()
    )


    return {
        "provider":
            "broadcastify",

        "client_api":
            status,
    }


@router.post(
    "/broadcastify/probe"
)
def probe_broadcastify_endpoint(
    request:
        BroadcastifyProbeRequest,
):
    try:
        return probe_broadcastify(
            request.url
        )


    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


@router.post("")
def create_source(
    request:
        SourceCreateRequest,
):
    if (
        request.type
        !=
        "broadcastify_calls"
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "v0.11 currently supports "
                "broadcastify_calls only"
            ),
        )


    try:
        probe = (
            probe_broadcastify(
                request.url
            )
        )


    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


    now = utc_now()


    name = (
        request.name.strip()
    )


    if (
        not name
        and
        probe.get(
            "page_name"
        )
    ):
        name = (
            probe[
                "page_name"
            ]
        )


    source = {
        "id":
            str(
                uuid.uuid4()
            ),

        "name":
            name,

        "type":
            "broadcastify_calls",

        "provider":
            "broadcastify",

        "url":
            probe[
                "canonical_url"
            ],

        "playlist_uuid":
            probe[
                "playlist_uuid"
            ],

        "view":
            probe[
                "view"
            ],

        "created_at":
            now,

        "updated_at":
            now,

        "probe":
            probe,
    }


    store = (
        load_store()
    )


    store.setdefault(
        "sources",
        [],
    ).append(
        source
    )


    save_store(
        store
    )


    return source


@router.post(
    "/{source_id}/probe"
)
def probe_existing_source(
    source_id: str,
):
    source = (
        get_source_or_404(
            source_id
        )
    )


    try:
        probe = (
            probe_broadcastify(
                source[
                    "url"
                ]
            )
        )


    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


    store = (
        load_store()
    )


    for item in store.get(
        "sources",
        [],
    ):
        if (
            item.get(
                "id"
            )
            == source_id
        ):
            item[
                "probe"
            ] = probe

            item[
                "updated_at"
            ] = utc_now()


            save_store(
                store
            )


            return item


    raise HTTPException(
        status_code=404,
        detail="Source not found",
    )


@router.delete(
    "/{source_id}"
)
def delete_source(
    source_id: str,
):
    store = (
        load_store()
    )


    sources = (
        store.get(
            "sources",
            [],
        )
    )


    remaining = [
        source
        for source in sources
        if source.get(
            "id"
        )
        != source_id
    ]


    if (
        len(
            remaining
        )
        ==
        len(
            sources
        )
    ):
        raise HTTPException(
            status_code=404,
            detail="Source not found",
        )


    store[
        "sources"
    ] = remaining


    save_store(
        store
    )


    return {
        "deleted":
            True,

        "id":
            source_id,
    }