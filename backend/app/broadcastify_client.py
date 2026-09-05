from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from dataclasses import dataclass
from typing import Any


LIVE_CALLS_URL = (
    "https://www.broadcastify.com"
    "/calls/apis/live-calls"
)


DEFAULT_USER_AGENT = (
    "RF-Gateway/0.11 "
    "(Broadcastify Calls Client)"
)


@dataclass
class BroadcastifyCall:
    key: str

    id: str | None
    timestamp: int | None

    system_id: int | None

    filename: str | None
    encoding: str | None
    file_hash: str | None

    start_time: int | None
    stop_time: int | None

    duration: float | None

    talkgroup: int | None
    source_id: int | None

    frequency_mhz: float | None

    description: str | None
    display: str | None
    grouping: str | None

    transcription: str | None

    metadata: dict[str, Any]

    raw: dict[str, Any]


def _optional_int(
    value: Any,
) -> int | None:
    if value is None:
        return None

    try:
        return int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def _optional_float(
    value: Any,
) -> float | None:
    if value is None:
        return None

    try:
        return float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def _optional_string(
    value: Any,
) -> str | None:
    if value is None:
        return None

    text = str(
        value
    ).strip()

    if not text:
        return None

    return text


def build_call_key(
    raw_call: dict[str, Any],
) -> str:
    filename = (
        _optional_string(
            raw_call.get(
                "filename"
            )
        )
        or
        "unknown"
    )

    file_hash = (
        _optional_string(
            raw_call.get(
                "hash"
            )
        )
        or
        "nohash"
    )

    return (
        f"{filename}:{file_hash}"
    )


def parse_call(
    raw_call: dict[str, Any],
) -> BroadcastifyCall:
    metadata = (
        raw_call.get(
            "metadata"
        )
    )

    if not isinstance(
        metadata,
        dict,
    ):
        metadata = {}


    return BroadcastifyCall(
        key=build_call_key(
            raw_call
        ),

        id=_optional_string(
            raw_call.get(
                "id"
            )
        ),

        timestamp=_optional_int(
            raw_call.get(
                "ts"
            )
        ),

        system_id=_optional_int(
            raw_call.get(
                "systemId"
            )
        ),

        filename=_optional_string(
            raw_call.get(
                "filename"
            )
        ),

        encoding=_optional_string(
            raw_call.get(
                "enc"
            )
        ),

        file_hash=_optional_string(
            raw_call.get(
                "hash"
            )
        ),

        start_time=_optional_int(
            raw_call.get(
                "meta_starttime"
            )
        ),

        stop_time=_optional_int(
            raw_call.get(
                "meta_stoptime"
            )
        ),

        duration=_optional_float(
            raw_call.get(
                "call_duration"
            )
        ),

        talkgroup=_optional_int(
            raw_call.get(
                "call_tg"
            )
        ),

        source_id=_optional_int(
            raw_call.get(
                "call_src"
            )
        ),

        frequency_mhz=_optional_float(
            raw_call.get(
                "call_freq"
            )
        ),

        description=_optional_string(
            raw_call.get(
                "descr"
            )
        ),

        display=_optional_string(
            raw_call.get(
                "display"
            )
        ),

        grouping=_optional_string(
            raw_call.get(
                "grouping"
            )
        ),

        transcription=_optional_string(
            raw_call.get(
                "transcription"
            )
        ),

        metadata=metadata,

        raw=raw_call,
    )


class BroadcastifyClient:
    def __init__(
        self,
        playlist_uuid: str,
        *,
        session_key: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        playlist_uuid = (
            playlist_uuid
            .strip()
        )

        if not playlist_uuid:
            raise ValueError(
                "playlist_uuid cannot be empty"
            )


        self.playlist_uuid = (
            playlist_uuid
        )

        self.session_key = (
            session_key
            or
            (
                "rf-gateway-"
                + uuid.uuid4().hex[:12]
            )
        )

        self.timeout = (
            timeout
        )


        self.position: int = 0

        self.server_time: int | None = None

        self.last_pos: int | None = None

        self.initialized: bool = False


        self._seen_calls:
            set[str] = set()


    @property
    def referer(self) -> str:
        query = urllib.parse.urlencode(
            {
                "uuid":
                    self.playlist_uuid,

                "view":
                    "list",
            }
        )

        return (
            "https://www.broadcastify.com"
            "/calls/playlists/"
            f"?{query}"
        )


    def _request(
        self,
        *,
        position: int,
        do_init: bool,
    ) -> dict[str, Any]:
        form = {
            "pos":
                str(
                    position
                ),

            "doInit":
                "1"
                if do_init
                else "0",

            "systemId":
                "0",

            "sid":
                "0",

            "playlist_uuid":
                self.playlist_uuid,

            "sessionKey":
                self.session_key,
        }


        body = (
            urllib.parse.urlencode(
                form
            )
            .encode(
                "utf-8"
            )
        )


        request = urllib.request.Request(
            LIVE_CALLS_URL,

            data=body,

            method="POST",

            headers={
                "User-Agent":
                    DEFAULT_USER_AGENT,

                "Accept":
                    "*/*",

                "Content-Type":
                    (
                        "application/"
                        "x-www-form-urlencoded; "
                        "charset=UTF-8"
                    ),

                "Origin":
                    "https://www.broadcastify.com",

                "Referer":
                    self.referer,

                "X-Requested-With":
                    "XMLHttpRequest",
            },
        )


        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                response_body = (
                    response.read()
                )

        except urllib.error.HTTPError as error:
            try:
                error_body = (
                    error.read()
                    .decode(
                        "utf-8",
                        errors="replace",
                    )
                )

            except Exception:
                error_body = ""


            raise RuntimeError(
                "Broadcastify returned "
                f"HTTP {error.code}: "
                f"{error_body[:500]}"
            ) from error


        except urllib.error.URLError as error:
            raise RuntimeError(
                "Unable to connect to "
                f"Broadcastify: {error}"
            ) from error


        except TimeoutError as error:
            raise RuntimeError(
                "Broadcastify request "
                "timed out"
            ) from error


        try:
            data = json.loads(
                response_body.decode(
                    "utf-8"
                )
            )

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            preview = (
                response_body[
                    :500
                ]
                .decode(
                    "utf-8",
                    errors="replace",
                )
            )

            raise RuntimeError(
                "Broadcastify returned "
                "invalid JSON: "
                f"{preview}"
            ) from error


        if not isinstance(
            data,
            dict,
        ):
            raise RuntimeError(
                "Broadcastify response "
                "is not a JSON object"
            )


        return data


    def _process_response(
        self,
        data: dict[str, Any],
    ) -> list[BroadcastifyCall]:
        server_time = (
            _optional_int(
                data.get(
                    "serverTime"
                )
            )
        )

        last_pos = (
            _optional_int(
                data.get(
                    "lastPos"
                )
            )
        )


        if server_time is not None:
            self.server_time = (
                server_time
            )


        if last_pos is not None:
            self.last_pos = (
                last_pos
            )

            self.position = (
                last_pos
            )


        raw_calls = (
            data.get(
                "calls",
                [],
            )
        )


        if not isinstance(
            raw_calls,
            list,
        ):
            raise RuntimeError(
                "Broadcastify response "
                "'calls' field is not a list"
            )


        parsed_calls:
            list[BroadcastifyCall] = []


        for item in raw_calls:
            if not isinstance(
                item,
                dict,
            ):
                continue


            call = parse_call(
                item
            )


            if (
                call.key
                in self._seen_calls
            ):
                continue


            self._seen_calls.add(
                call.key
            )

            parsed_calls.append(
                call
            )


        parsed_calls.sort(
            key=lambda call:
                call.timestamp
                or 0
        )


        return parsed_calls


    def initialize(
        self,
    ) -> list[BroadcastifyCall]:
        data = self._request(
            position=0,
            do_init=True,
        )


        calls = (
            self._process_response(
                data
            )
        )


        self.initialized = (
            True
        )


        return calls


    def poll(
        self,
    ) -> list[BroadcastifyCall]:
        if not self.initialized:
            return self.initialize()


        data = self._request(
            position=self.position,
            do_init=False,
        )


        return (
            self._process_response(
                data
            )
        )


    def status(
        self,
    ) -> dict[str, Any]:
        return {
            "playlist_uuid":
                self.playlist_uuid,

            "session_key":
                self.session_key,

            "initialized":
                self.initialized,

            "position":
                self.position,

            "last_pos":
                self.last_pos,

            "server_time":
                self.server_time,

            "seen_calls":
                len(
                    self._seen_calls
                ),
        }


def run_test_client(
    playlist_uuid: str,
    *,
    poll_interval: float = 3.0,
) -> None:
    client = BroadcastifyClient(
        playlist_uuid
    )


    print(
        "Broadcastify client"
    )

    print(
        json.dumps(
            client.status(),
            indent=2,
        )
    )


    initial_calls = (
        client.initialize()
    )


    print(
        "\nInitial calls:"
    )

    print(
        len(
            initial_calls
        )
    )


    for call in initial_calls:
        print(
            (
                f"[{call.timestamp}] "
                f"{call.display or call.description or '--'} "
                f"{call.duration or 0}s "
                f"{call.filename or '--'}."
                f"{call.encoding or '--'}"
            )
        )


    print(
        "\nPolling for new calls..."
    )


    try:
        while True:
            time.sleep(
                poll_interval
            )


            calls = (
                client.poll()
            )


            for call in calls:
                print(
                    (
                        f"[NEW] "
                        f"[{call.timestamp}] "
                        f"{call.display or call.description or '--'} "
                        f"{call.duration or 0}s "
                        f"{call.filename or '--'}."
                        f"{call.encoding or '--'}"
                    )
                )


                if (
                    call.transcription
                ):
                    print(
                        "      "
                        + call.transcription
                    )


    except KeyboardInterrupt:
        print(
            "\nStopped."
        )
