"""HTTP client for FlashScore (RapidAPI).

This module is a general-purpose template for "how to wrap a REST API in a
Python project." The patterns used here apply to ANY external service you
might integrate with — Stripe, Slack, OpenAI, a weather API, etc.

Key architectural choices (and why):

1. **One class owns all HTTP details.** Callers never build URLs, set
   headers, or parse JSON directly. If the API changes, only this file
   needs updating — the rest of the project is insulated.

2. **Typed dataclasses, not raw JSON dicts.** ``RawGame`` represents a
   completed match; ``RawFixture`` represents one that hasn't been
   played yet. Two types instead of one "game with optional scores"
   because the DIFFERENCE is semantic, not just presence/absence of a
   field. Your code is clearer when it says ``list[RawFixture]`` than
   ``list[RawGame]``-with-a-guess-about-scores.

3. **Pagination handled inside the client.** The public fetch methods
   loop through pages until the server returns an empty list. Callers
   never think about pages — that's the right boundary between
   "API-transport concern" and "business-logic concern".

4. **Shared pagination via a generic helper.** ``fetch_all_results`` and
   ``fetch_all_fixtures`` both call a single private ``_fetch_all_pages``
   method that takes the endpoint path and a per-item parser as params.
   Keeps the two public methods tiny and ensures the pagination bug fix
   in one place benefits both.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TypeVar
from zoneinfo import ZoneInfo

import requests

# Games in the Greek A1 are scheduled in Athens local time. The API gives
# us UTC Unix timestamps; we convert once here so callers don't have to
# think about timezones. tzdata (a pandas dependency) provides the zone
# database on Windows.
_ATHENS_TZ = ZoneInfo("Europe/Athens")


# ---------------------------------------------------------------------------
# Custom exceptions — specific enough that callers can handle each precisely
# ---------------------------------------------------------------------------


class APIClientError(Exception):
    """Base class for anything that goes wrong talking to the API."""


class APIAuthError(APIClientError):
    """The API key is missing, invalid, or out of quota."""


class APIResponseError(APIClientError):
    """The API returned something we couldn't parse as expected."""


# ---------------------------------------------------------------------------
# The shapes we expose to the rest of the project
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawGame:
    """A single completed game, as returned by the /results endpoint.

    ``frozen=True`` makes instances immutable — once fetched, the data is
    a fact and should not be "edited" in place. Any transformation
    produces a new object, keeping the data-flow traceable.

    Team names here are the API's names ("Kolossos Rhodes"), NOT our
    canonical names ("Kolossos Rodou"). The mapping step happens
    downstream so this module stays API-specific and doesn't know
    about our project's conventions.

    Both ``date`` and ``time`` are in **Athens local time** — converted
    from the API's UTC timestamp at this boundary so the rest of the
    project never has to think about timezones.
    """

    date: str  # "YYYY-MM-DD" in Athens local time
    time: str  # "HH:MM" in Athens local time (24h)
    home_team_api_name: str
    away_team_api_name: str
    home_score: int
    away_score: int
    # FlashScore's id for the match — needed to look up the final score via
    # /matches/details when /results only gives us the regulation-time tie.
    match_id: str = ""


@dataclass(frozen=True)
class RawFixture:
    """A single scheduled (not yet played) match, from the /fixtures endpoint.

    Same shape as RawGame minus the scores. We use a separate type rather
    than ``RawGame`` with ``home_score: int | None`` because the semantic
    meaning is different — "this game has no score" and "this game hasn't
    happened yet" mean different things. Two types, clear intent.
    """

    date: str  # "YYYY-MM-DD" in Athens local time
    time: str  # "HH:MM" in Athens local time (24h)
    home_team_api_name: str
    away_team_api_name: str


# TypeVar lets the generic pagination helper work with either RawGame or
# RawFixture — the type checker can see which parser produces which type.
_TItem = TypeVar("_TItem")


# ---------------------------------------------------------------------------
# The client
# ---------------------------------------------------------------------------

# Safety limit for pagination loops. Real leagues have a few hundred games;
# anything above this is almost certainly a bug (e.g., the server started
# returning the same page over and over). Without this, a server-side bug
# could turn into an infinite loop eating your API quota.
_MAX_PAGES: int = 50


class FlashScoreClient:
    """Thin wrapper around the flashscore4.p.rapidapi.com REST endpoints."""

    # Endpoint paths — kept as class constants so the rest of the file
    # doesn't have magic strings. If the API ever renames these paths,
    # you change them here, nowhere else.
    _RESULTS_PATH = "api/flashscore/v2/tournaments/results"
    _FIXTURES_PATH = "api/flashscore/v2/tournaments/fixtures"
    _DETAILS_PATH = "api/flashscore/v2/matches/details"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        host: str,
        *,
        session: requests.Session | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not api_key:
            raise APIAuthError("API key is empty. Set RAPIDAPI_KEY in your .env file.")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._host = host
        self._session = session or requests.Session()
        self._timeout = timeout_seconds

    # -- internal HTTP machinery -----------------------------------------

    def _headers(self) -> dict[str, str]:
        """RapidAPI requires two headers: the key AND the product host."""
        return {
            "x-rapidapi-key": self._api_key,
            "x-rapidapi-host": self._host,
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        """Internal helper: one HTTP GET, returns parsed JSON."""
        url = f"{self._base_url}/{path.lstrip('/')}"
        try:
            response = self._session.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise APIClientError(f"Network error calling {url}: {exc}") from exc

        if response.status_code in (401, 403):
            raise APIAuthError(
                f"API rejected the key (HTTP {response.status_code}). "
                "Check RAPIDAPI_KEY in your .env file."
            )
        if response.status_code == 429:
            raise APIClientError("API rate limit hit (HTTP 429). Wait a bit before retrying.")
        if not response.ok:
            raise APIClientError(
                f"Unexpected HTTP {response.status_code} from {url}: {response.text[:200]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise APIResponseError(
                f"API returned non-JSON content for {url}: {response.text[:200]}"
            ) from exc

    # -- shared pagination -----------------------------------------------

    def _fetch_all_pages(
        self,
        path: str,
        params_template: dict[str, Any],
        parser: Callable[[dict], _TItem | None],
    ) -> list[_TItem]:
        """Iterate pages until the server returns an empty list.

        ``parser`` turns one raw dict from the response into either a typed
        result (RawGame, RawFixture, ...) or None for malformed rows. None
        results are logged and skipped — a single bad row doesn't kill
        the whole import.
        """
        all_items: list[_TItem] = []
        for page in range(1, _MAX_PAGES + 1):
            payload = self._get(path, {**params_template, "page": page})

            # FlashScore always returns a naked JSON array. If that ever
            # changes (dict with "error" or similar), we want to fail
            # loudly, not silently produce zero results.
            if not isinstance(payload, list):
                raise APIResponseError(
                    f"Expected a JSON list from /{path}, got "
                    f"{type(payload).__name__}: {str(payload)[:200]}"
                )
            if not payload:
                # Empty page = pagination complete. This is the termination
                # signal the API gives us (no total_pages field exists).
                return all_items

            for raw in payload:
                item = parser(raw)
                if item is None:
                    # One bad row skipped, with a warning so the user knows
                    # something was filtered out, not silently lost.
                    print(f"  WARN: skipping malformed item (id={raw.get('match_id', '?')})")
                    continue
                all_items.append(item)

        # If we reach here, the server returned _MAX_PAGES of data. That's
        # well above a real basketball season — treat as a server bug
        # rather than silently truncating.
        raise APIClientError(
            f"Pagination exceeded {_MAX_PAGES} pages. "
            "This almost certainly indicates an API-side issue; please investigate."
        )

    # -- parsers ---------------------------------------------------------

    @staticmethod
    def _parse_datetime(raw: dict) -> tuple[str, str]:
        """Unix timestamp (UTC) -> (YYYY-MM-DD, HH:MM) in Athens local time.

        Converting once here means everything downstream — CSV storage,
        Fixture dataclass, UI rendering — deals in the user's natural
        timezone instead of UTC.
        """
        dt_utc = datetime.fromtimestamp(int(raw["timestamp"]), tz=timezone.utc)
        dt_local = dt_utc.astimezone(_ATHENS_TZ)
        return dt_local.strftime("%Y-%m-%d"), dt_local.strftime("%H:%M")

    def _parse_game(self, raw: dict) -> RawGame | None:
        try:
            home_score = raw["scores"]["home"]
            away_score = raw["scores"]["away"]
            # Guard: /results can occasionally return postponed matches
            # with null scores. Skip those — we want truly finished games.
            if home_score is None or away_score is None:
                return None
            date_str, time_str = self._parse_datetime(raw)
            return RawGame(
                date=date_str,
                time=time_str,
                home_team_api_name=raw["home_team"]["name"],
                away_team_api_name=raw["away_team"]["name"],
                home_score=int(home_score),
                away_score=int(away_score),
                match_id=str(raw.get("match_id", "")),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _parse_fixture(self, raw: dict) -> RawFixture | None:
        # Fixtures have no "scores" field — we don't require it.
        try:
            date_str, time_str = self._parse_datetime(raw)
            return RawFixture(
                date=date_str,
                time=time_str,
                home_team_api_name=raw["home_team"]["name"],
                away_team_api_name=raw["away_team"]["name"],
            )
        except (KeyError, TypeError, ValueError):
            return None

    # -- public ----------------------------------------------------------

    def fetch_all_results(
        self,
        tournament_template_id: str,
        season_id: str,
    ) -> list[RawGame]:
        """Fetch EVERY completed result for a tournament + season."""
        return self._fetch_all_pages(
            path=self._RESULTS_PATH,
            params_template={
                "tournament_template_id": tournament_template_id,
                "season_id": season_id,
            },
            parser=self._parse_game,
        )

    def fetch_all_fixtures(
        self,
        tournament_template_id: str,
        season_id: str,
    ) -> list[RawFixture]:
        """Fetch EVERY scheduled (unplayed) fixture for a tournament + season."""
        return self._fetch_all_pages(
            path=self._FIXTURES_PATH,
            params_template={
                "tournament_template_id": tournament_template_id,
                "season_id": season_id,
            },
            parser=self._parse_fixture,
        )

    def fetch_final_score(self, match_id: str) -> tuple[int, int] | None:
        """Return the FINAL (home, away) score of one match, overtime included.

        /results reports the regulation-time score, so an overtime game shows
        up as a tie (e.g. 69-69 instead of 93-86). /matches/details carries
        the full score in ``home_total`` / ``away_total``. One request per
        call — only use it for games that look tied.

        Returns None if the payload has no usable totals.
        """
        payload = self._get(self._DETAILS_PATH, {"match_id": match_id})
        try:
            scores = payload["scores"]
            return int(scores["home_total"]), int(scores["away_total"])
        except (KeyError, TypeError, ValueError):
            return None
