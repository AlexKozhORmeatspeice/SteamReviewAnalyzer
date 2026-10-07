from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass

from steam_analyzer.stopwords import STOPWORDS

BBCODE_RE = re.compile(r"\[[^\[\]]{1,80}\]")
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
EMOTICON_RE = re.compile(r":[a-z0-9_]{2,}:", re.IGNORECASE)
TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ]{3,}")


@dataclass(frozen=True)
class SampleStats:
    count: int
    positive: int
    median_minutes: float | None


def sample_stats(reviews: list[dict[str, str]]) -> SampleStats:
    minutes: list[int] = []
    positive = 0
    for row in reviews:
        if row.get("voted_up") == "1":
            positive += 1
        minutes.append(_as_int(row.get("playtime_forever_minutes")))
    median = statistics.median(minutes) if minutes else None
    return SampleStats(count=len(reviews), positive=positive, median_minutes=median)


def word_frequencies(texts: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for text in texts:
        cleaned = EMOTICON_RE.sub(" ", URL_RE.sub(" ", BBCODE_RE.sub(" ", text)))
        cleaned = cleaned.replace("'", "").replace("’", "")
        for token in TOKEN_RE.findall(cleaned):
            word = token.casefold().replace("ё", "е")
            if word in STOPWORDS:
                continue
            counts[word] += 1
    return counts


def format_overview(
    reviews: list[dict[str, str]],
    games: list[dict[str, str]],
    *,
    title: str,
    breakdown: bool,
) -> str:
    games_by_id = {row["app_id"]: row for row in games if row.get("app_id")}
    stats = sample_stats(reviews)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in reviews:
        grouped[row.get("app_id", "")].append(row)

    app_ids = set(grouped) | ({row["app_id"] for row in games if row.get("app_id")} if breakdown else set(grouped))
    steam_positive = 0
    steam_total = 0
    missing: list[str] = []
    for app_id in sorted(app_ids):
        game = games_by_id.get(app_id)
        if game is None:
            if app_id:
                missing.append(app_id)
            continue
        steam_positive += _as_int(game.get("positive_reviews"))
        steam_total += _as_int(game.get("total_reviews"))

    lines = [
        title,
        f"Downloaded reviews: {stats.count}",
        f"Positive among downloaded: {format_percent(stats.positive, stats.count)}",
        f"Positive in the Steam summary: {format_percent(steam_positive, steam_total)}",
        f"Median lifetime playtime: {format_playtime(stats.median_minutes)}",
        "The Steam summary counts every review in the store. The median and the downloaded percentage use only the rows in reviews.csv.",
    ]
    if missing:
        lines.append("No games.csv row for AppID: " + ", ".join(missing))

    if breakdown and app_ids:
        lines.append("")
        lines.append("Per game:")
        ordered = sorted(app_ids, key=lambda app_id: (-len(grouped.get(app_id, [])), app_id))
        for app_id in ordered:
            game = games_by_id.get(app_id)
            name = game["name"] if game else "untitled"
            local = sample_stats(grouped.get(app_id, []))
            steam_part = _as_int(game.get("positive_reviews")) if game else 0
            steam_whole = _as_int(game.get("total_reviews")) if game else 0
            lines.append(
                f"  {app_id} | {name} | reviews: {local.count} | "
                f"downloaded +: {format_percent(local.positive, local.count)} | "
                f"Steam +: {format_percent(steam_part, steam_whole)} | "
                f"median: {format_playtime(local.median_minutes)}"
            )
    return "\n".join(lines)


def format_percent(part: int, whole: int) -> str:
    if whole <= 0:
        return "n/a"
    return f"{part / whole * 100:.1f}% ({part} of {whole})"


def format_playtime(median_minutes: float | None) -> str:
    if median_minutes is None:
        return "n/a"
    if float(median_minutes).is_integer():
        minutes = str(int(median_minutes))
    else:
        minutes = f"{median_minutes:.1f}"
    return f"{median_minutes / 60:.1f} h ({minutes} min)"


def _as_int(value: object) -> int:
    try:
        return max(0, int(str(value or "0")))
    except ValueError:
        return 0
