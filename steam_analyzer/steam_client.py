from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import requests

REQUEST_PAUSE_SECONDS = 1.0
REVIEWS_URL = "https://store.steampowered.com/appreviews/{app_id}"
DETAILS_URL = "https://store.steampowered.com/api/appdetails"
STEAMSPY_URL = "https://steamspy.com/api.php"


class SteamError(Exception):
    """A Steam request failed or the response could not be read."""


@dataclass(frozen=True)
class Review:
    review_id: str
    review_text: str
    playtime_forever_minutes: int
    language: str
    app_id: str
    voted_up: str

    def as_row(self) -> dict[str, str]:
        return {
            "review_id": self.review_id,
            "review_text": self.review_text,
            "playtime_forever_minutes": str(self.playtime_forever_minutes),
            "language": self.language,
            "app_id": self.app_id,
            "voted_up": self.voted_up,
        }


@dataclass(frozen=True)
class GameDetails:
    app_id: str
    name: str
    genres: str


@dataclass(frozen=True)
class ReviewSummary:
    positive: int
    total: int
    score_label: str


class SteamClient:
    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "SteamDataAnalyzer/1.0 (personal review research)",
                "Accept": "application/json",
            }
        )

    def fetch_game(self, app_id: int, language: str) -> GameDetails:
        payload = self._get_json(DETAILS_URL, {"appids": app_id, "l": language, "cc": "us"})
        node = payload.get(str(app_id)) or {}
        data = node.get("data") if isinstance(node, dict) else None
        if not isinstance(node, dict) or not node.get("success") or not isinstance(data, dict):
            raise SteamError(
                f"No game found for AppID {app_id}. Check the number on the Steam store page."
            )
        genres: list[str] = []
        for genre in data.get("genres") or []:
            if isinstance(genre, dict) and genre.get("description"):
                genres.append(_one_line(str(genre["description"])))
        return GameDetails(
            app_id=str(app_id),
            name=_one_line(str(data.get("name") or app_id)),
            genres=_join(genres),
        )

    def fetch_summary(self, app_id: int) -> ReviewSummary:
        payload = self._get_json(
            REVIEWS_URL.format(app_id=app_id),
            {
                "json": 1,
                "language": "all",
                "review_type": "all",
                "purchase_type": "all",
                "num_per_page": 0,
            },
        )
        if payload.get("success") != 1:
            raise SteamError("Steam did not return a review summary.")
        summary = payload.get("query_summary") or {}
        if not isinstance(summary, dict) or "total_reviews" not in summary:
            raise SteamError("The Steam response has no total review count.")
        return ReviewSummary(
            positive=_non_negative(summary.get("total_positive")),
            total=_non_negative(summary.get("total_reviews")),
            score_label=_one_line(str(summary.get("review_score_desc") or "")),
        )

    def fetch_tags(self, app_id: int) -> tuple[str, str | None]:
        try:
            payload = self._get_json(STEAMSPY_URL, {"request": "appdetails", "appid": app_id})
        except SteamError as exc:
            return "", str(exc)
        tags = payload.get("tags")
        if not isinstance(tags, dict):
            return "", None
        ranked = sorted(
            (
                (str(name).strip(), count)
                for name, count in tags.items()
                if str(name).strip()
            ),
            key=lambda item: item[1] if isinstance(item[1], (int, float)) else 0,
            reverse=True,
        )
        return _join([name for name, _count in ranked]), None

    def fetch_reviews(
        self,
        app_id: int,
        limit: int | None,
        on_progress: Callable[[int], None] | None = None,
    ) -> list[Review]:
        # filter=recent is required for the cursor to reach the end.
        # filter=all keeps returning a helpful subset and never goes empty.
        reviews: list[Review] = []
        seen: set[str] = set()
        cursor = "*"
        while limit is None or len(reviews) < limit:
            if cursor != "*":
                time.sleep(REQUEST_PAUSE_SECONDS)
            page_size = 100 if limit is None else min(100, limit - len(reviews))
            payload = self._get_json(
                REVIEWS_URL.format(app_id=app_id),
                {
                    "json": 1,
                    "filter": "recent",
                    "language": "all",
                    "review_type": "all",
                    "purchase_type": "all",
                    "num_per_page": page_size,
                    "cursor": cursor,
                },
            )
            if payload.get("success") != 1:
                raise SteamError("Steam rejected the review request.")
            batch = payload.get("reviews") or []
            if not isinstance(batch, list) or not batch:
                break
            added = 0
            for item in batch:
                if not isinstance(item, dict):
                    continue
                review = _parse_review(app_id, item)
                if review is None or review.review_id in seen:
                    continue
                seen.add(review.review_id)
                reviews.append(review)
                added += 1
                if limit is not None and len(reviews) >= limit:
                    break
            if on_progress is not None:
                on_progress(len(reviews))
            next_cursor = payload.get("cursor")
            if not isinstance(next_cursor, str) or not next_cursor or next_cursor == cursor or added == 0:
                break
            cursor = next_cursor
        return reviews

    def _get_json(self, url: str, params: dict[str, object]) -> dict:
        last_status: int | None = None
        for attempt in range(4):
            try:
                response = self._session.get(url, params=params, timeout=30)
            except requests.RequestException as exc:
                if attempt == 3:
                    raise SteamError(f"No response from the server: {exc}") from exc
                time.sleep(2 * (attempt + 1))
                continue
            last_status = response.status_code
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 3:
                    break
                delay = 5 * (attempt + 1) if response.status_code == 429 else 2 * (attempt + 1)
                time.sleep(delay)
                continue
            if response.status_code != 200:
                raise SteamError(f"The server returned status {response.status_code}.")
            try:
                payload = response.json()
            except ValueError as exc:
                raise SteamError("The server did not return JSON.") from exc
            if not isinstance(payload, dict):
                raise SteamError("Unexpected server response.")
            return payload
        raise SteamError(
            f"Steam is limiting requests (last status {last_status}). Try again later."
        )


def _parse_review(app_id: int, item: dict) -> Review | None:
    review_id = str(item.get("recommendationid") or "").strip()
    if not review_id:
        return None
    author = item.get("author") if isinstance(item.get("author"), dict) else {}
    return Review(
        review_id=review_id,
        review_text=str(item.get("review") or "").replace("\x00", "").strip(),
        playtime_forever_minutes=_non_negative(author.get("playtime_forever")),
        language=str(item.get("language") or "").strip(),
        app_id=str(app_id),
        voted_up="1" if item.get("voted_up") else "0",
    )


def _join(values: list[str]) -> str:
    cleaned: list[str] = []
    for value in values:
        item = _one_line(value).replace(";", ",")
        if item and item not in cleaned:
            cleaned.append(item)
    return "; ".join(cleaned)


def _one_line(value: str) -> str:
    return " ".join(value.split())


def _non_negative(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
