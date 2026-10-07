from __future__ import annotations

import csv
from pathlib import Path

REVIEW_FIELDS = (
    "review_id",
    "review_text",
    "playtime_forever_minutes",
    "language",
    "app_id",
    "voted_up",
)

GAME_FIELDS = (
    "app_id",
    "name",
    "genres",
    "tags",
    "positive_reviews",
    "total_reviews",
)


def reviews_path(data_dir: Path) -> Path:
    return data_dir / "reviews.csv"


def games_path(data_dir: Path) -> Path:
    return data_dir / "games.csv"


def wordcloud_dir(data_dir: Path) -> Path:
    return data_dir / "wordclouds"


def prepare_data_dir(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    reviews = reviews_path(data_dir)
    games = games_path(data_dir)
    if not reviews.exists():
        _write_rows(reviews, REVIEW_FIELDS, [])
    if not games.exists():
        _write_rows(games, GAME_FIELDS, [])


def load_reviews(path: Path) -> list[dict[str, str]]:
    return _read_rows(path)


def load_games(path: Path) -> list[dict[str, str]]:
    return _read_rows(path)


def replace_app_reviews(path: Path, app_id: str, reviews: list[dict[str, str]]) -> None:
    kept = [row for row in load_reviews(path) if row.get("app_id") != app_id]
    _write_rows(path, REVIEW_FIELDS, kept + reviews)


def delete_app_data(data_dir: Path, app_id: str) -> tuple[int, bool, list[str]]:
    reviews_file = reviews_path(data_dir)
    games_file = games_path(data_dir)
    reviews = load_reviews(reviews_file)
    kept_reviews = [row for row in reviews if row.get("app_id") != app_id]
    removed_reviews = len(reviews) - len(kept_reviews)
    if removed_reviews:
        _write_rows(reviews_file, REVIEW_FIELDS, kept_reviews)

    games = load_games(games_file)
    kept_games = [row for row in games if row.get("app_id") != app_id]
    game_removed = len(kept_games) != len(games)
    if game_removed:
        _write_rows(games_file, GAME_FIELDS, kept_games)

    removed_files: list[str] = []
    clouds = wordcloud_dir(data_dir)
    if clouds.is_dir():
        targets = list(clouds.glob(f"{app_id}_*.png"))
        combined = clouds / "all.png"
        if combined.is_file():
            targets.append(combined)
        for path in targets:
            path.unlink()
            removed_files.append(str(path))
        if not any(clouds.iterdir()):
            clouds.rmdir()
    return removed_reviews, game_removed, removed_files


def upsert_game(path: Path, game: dict[str, str]) -> None:
    games = [row for row in load_games(path) if row.get("app_id") != game["app_id"]]
    games.append(game)
    games.sort(key=lambda row: int(row["app_id"]) if str(row.get("app_id", "")).isdigit() else 0)
    _write_rows(path, GAME_FIELDS, games)


def delete_generated_data(data_dir: Path) -> list[str]:
    removed: list[str] = []
    for path in (reviews_path(data_dir), games_path(data_dir)):
        if path.is_file():
            path.unlink()
            removed.append(str(path))
    clouds = wordcloud_dir(data_dir)
    if clouds.is_dir():
        for png in clouds.glob("*.png"):
            png.unlink()
            removed.append(str(png))
        if not any(clouds.iterdir()):
            clouds.rmdir()
            removed.append(str(clouds))
    return removed


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, str]] = []
        for raw in reader:
            row = {key: (value or "").strip() if key != "review_text" else (value or "") for key, value in raw.items() if key}
            if not any(value.strip() for value in row.values()):
                continue
            rows.append(row)
        return rows


def _write_rows(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fieldnames})
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
