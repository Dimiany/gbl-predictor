"""Tests for FlashScoreClient — using a mocked HTTP session.

The key teaching point here: we NEVER actually hit the real API in tests.
Unit tests that touch the network are slow, flaky, and require live
credentials — three things tests should never be. Instead we pass a fake
Session object into the client and control exactly what "HTTP responses"
it sees. This is the mock / dependency-injection pattern.

Also demonstrated: how to test pagination logic. We return a sequence of
mock responses — two non-empty pages followed by an empty one — and
verify the client stitches them together and stops correctly.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.api_client import (
    APIAuthError,
    APIClientError,
    APIResponseError,
    FlashScoreClient,
    RawFixture,
    RawGame,
)

# ---------------------------------------------------------------------------
# Fake-response factory
# ---------------------------------------------------------------------------


def _fake_response(
    status_code: int = 200,
    json_data=None,
    text: str = "",
):
    """Return a MagicMock that quacks like a ``requests.Response``.

    Duck typing: we only stub the attributes our client actually reads.
    """
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 300
    resp.text = text
    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = ValueError("No JSON body")
    return resp


def _match_with_score(
    match_id="abc", timestamp=1776870000, home="Peristeri", away="Aris", hs=78, as_=75
):
    """Build a FlashScore-shaped finished-match dict for /results responses."""
    return {
        "match_id": match_id,
        "timestamp": timestamp,
        "home_team": {"team_id": "h", "name": home, "short_name": None, "small_image_path": ""},
        "away_team": {"team_id": "a", "name": away, "short_name": None, "small_image_path": ""},
        "scores": {"home": hs, "away": as_},
    }


def _match_without_score(
    match_id="abc", timestamp=1777122000, home="Panathinaikos", away="Mykonos"
):
    """Build a FlashScore-shaped unplayed match dict for /fixtures responses."""
    return {
        "match_id": match_id,
        "timestamp": timestamp,
        "home_team": {"team_id": "h", "name": home, "short_name": None, "small_image_path": ""},
        "away_team": {"team_id": "a", "name": away, "short_name": None, "small_image_path": ""},
        # NOTE: no "scores" key — this is what /fixtures returns.
    }


def _make_client(session) -> FlashScoreClient:
    return FlashScoreClient(
        api_key="TEST_KEY",
        base_url="https://test.example/",
        host="test.example",
        session=session,
    )


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


def test_client_rejects_empty_api_key():
    # Fail fast on the obvious misconfig — better than a confusing 401 later.
    with pytest.raises(APIAuthError):
        FlashScoreClient(api_key="", base_url="x", host="y")


# ---------------------------------------------------------------------------
# fetch_all_results — happy paths
# ---------------------------------------------------------------------------


def test_fetch_all_results_parses_finished_game():
    session = MagicMock()
    session.get.side_effect = [
        _fake_response(json_data=[_match_with_score()]),
        _fake_response(json_data=[]),  # end
    ]
    client = _make_client(session)
    games = client.fetch_all_results("xn32I3T4", "187")

    assert len(games) == 1
    g = games[0]
    assert isinstance(g, RawGame)
    # Unix timestamp 1776870000 = 2026-04-22 UTC.
    assert g.date == "2026-04-22"
    assert g.home_team_api_name == "Peristeri"
    assert g.home_score == 78
    assert g.away_score == 75


def test_fetch_all_results_skips_games_without_scores():
    # /results can occasionally include postponed games with None scores.
    # We want those silently skipped — we only care about truly finished games.
    session = MagicMock()
    session.get.side_effect = [
        _fake_response(
            json_data=[
                _match_with_score(match_id="played"),
                {**_match_with_score(match_id="pending"), "scores": {"home": None, "away": None}},
            ]
        ),
        _fake_response(json_data=[]),
    ]
    client = _make_client(session)
    games = client.fetch_all_results("t", "s")
    assert len(games) == 1
    assert games[0].home_team_api_name == "Peristeri"


def test_fetch_all_results_sends_correct_headers_and_params():
    session = MagicMock()
    session.get.return_value = _fake_response(json_data=[])
    client = _make_client(session)

    client.fetch_all_results("xn32I3T4", "187")

    _, kwargs = session.get.call_args
    assert kwargs["headers"]["x-rapidapi-key"] == "TEST_KEY"
    assert kwargs["headers"]["x-rapidapi-host"] == "test.example"
    # First call should request page 1.
    assert kwargs["params"] == {
        "tournament_template_id": "xn32I3T4",
        "season_id": "187",
        "page": 1,
    }


# ---------------------------------------------------------------------------
# fetch_all_results — pagination (the core teaching test)
# ---------------------------------------------------------------------------


def test_fetch_all_results_stitches_pages_until_empty():
    """The pagination invariant: keep requesting until the server returns
    an empty list, then return the union of all pages.
    """
    session = MagicMock()
    session.get.side_effect = [
        _fake_response(
            json_data=[
                _match_with_score(match_id="a"),
                _match_with_score(match_id="b", home="PAOK", away="Aris"),
            ]
        ),
        _fake_response(
            json_data=[
                _match_with_score(match_id="c", home="Mykonos", away="Peristeri"),
            ]
        ),
        _fake_response(json_data=[]),  # empty -> pagination ends
    ]
    client = _make_client(session)

    games = client.fetch_all_results("t", "s")

    assert len(games) == 3
    assert session.get.call_count == 3
    # Pages must have been fetched in order, starting at 1.
    pages_requested = [c.kwargs["params"]["page"] for c in session.get.call_args_list]
    assert pages_requested == [1, 2, 3]


def test_fetch_all_results_returns_empty_list_if_first_page_empty():
    # Brand-new season with no results yet, or a bad ID combo.
    session = MagicMock()
    session.get.return_value = _fake_response(json_data=[])
    client = _make_client(session)
    assert client.fetch_all_results("t", "s") == []
    assert session.get.call_count == 1


# ---------------------------------------------------------------------------
# fetch_all_results — failure modes
# ---------------------------------------------------------------------------


def test_fetch_all_results_raises_auth_error_on_401():
    session = MagicMock()
    session.get.return_value = _fake_response(status_code=401, text="unauthorized")
    client = _make_client(session)
    with pytest.raises(APIAuthError):
        client.fetch_all_results("t", "s")


def test_fetch_all_results_raises_on_rate_limit():
    # 429 = Too Many Requests. Distinct exception so callers can back off.
    session = MagicMock()
    session.get.return_value = _fake_response(status_code=429)
    client = _make_client(session)
    with pytest.raises(APIClientError) as exc:
        client.fetch_all_results("t", "s")
    assert "rate limit" in str(exc.value).lower()


def test_fetch_all_results_raises_on_non_list_payload():
    # FlashScore always returns a naked JSON array. If that ever changes,
    # we want to fail loudly, not silently produce zero games.
    session = MagicMock()
    session.get.return_value = _fake_response(json_data={"error": "unexpected"})
    client = _make_client(session)
    with pytest.raises(APIResponseError):
        client.fetch_all_results("t", "s")


def test_fetch_all_results_skips_malformed_match():
    # One bad apple shouldn't prevent us from importing the good ones.
    session = MagicMock()
    session.get.side_effect = [
        _fake_response(
            json_data=[
                _match_with_score(match_id="good"),
                {"match_id": "bad"},  # missing everything else
            ]
        ),
        _fake_response(json_data=[]),
    ]
    client = _make_client(session)
    games = client.fetch_all_results("t", "s")
    assert len(games) == 1


# ---------------------------------------------------------------------------
# fetch_all_fixtures — parallel to results but no scores
# ---------------------------------------------------------------------------


def test_fetch_all_fixtures_parses_unplayed_match():
    session = MagicMock()
    session.get.side_effect = [
        _fake_response(json_data=[_match_without_score()]),
        _fake_response(json_data=[]),
    ]
    client = _make_client(session)
    fx = client.fetch_all_fixtures("xn32I3T4", "187")

    assert len(fx) == 1
    f = fx[0]
    assert isinstance(f, RawFixture)
    # Unix timestamp 1777122000 = 2026-04-25 UTC.
    assert f.date == "2026-04-25"
    assert f.home_team_api_name == "Panathinaikos"
    assert f.away_team_api_name == "Mykonos"


def test_fetch_all_fixtures_hits_fixtures_endpoint_not_results():
    # Defensive: the path used must be /fixtures, not /results. Otherwise
    # we'd get back completed games and misinterpret them as upcoming.
    session = MagicMock()
    session.get.return_value = _fake_response(json_data=[])
    client = _make_client(session)
    client.fetch_all_fixtures("t", "s")
    # The URL is passed as the first positional arg to session.get().
    url = session.get.call_args[0][0]
    assert "/tournaments/fixtures" in url
    assert "/tournaments/results" not in url


def test_fetch_all_fixtures_paginates_like_results():
    # Same pagination contract as /results — empty list means done.
    session = MagicMock()
    session.get.side_effect = [
        _fake_response(json_data=[_match_without_score(match_id="a")]),
        _fake_response(json_data=[_match_without_score(match_id="b")]),
        _fake_response(json_data=[]),
    ]
    client = _make_client(session)
    fx = client.fetch_all_fixtures("t", "s")
    assert len(fx) == 2
    assert session.get.call_count == 3
