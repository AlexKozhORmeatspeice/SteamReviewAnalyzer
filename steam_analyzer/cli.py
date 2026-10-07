from __future__ import annotations

import os
import re
import sys
from collections import Counter
from pathlib import Path

from steam_analyzer.analysis import format_overview, format_percent, format_playtime, sample_stats, word_frequencies
from steam_analyzer.settings import (
    KEY_PATH,
    STEAM_LANGUAGES,
    Settings,
    default_data_dir,
    delete_settings,
    load_settings,
    save_settings,
)
from steam_analyzer.steam_client import SteamClient, SteamError
from steam_analyzer.storage import (
    delete_app_data,
    delete_generated_data,
    games_path,
    load_games,
    load_reviews,
    prepare_data_dir,
    replace_app_reviews,
    reviews_path,
    upsert_game,
    wordcloud_dir,
)
from steam_analyzer.wordmap import save_word_map

APP_URL_RE = re.compile(r"steampowered\.com/(?:app|agecheck/app)/(\d{1,10})", re.IGNORECASE)
FILENAME_RE = re.compile(r"[^\w\-]+", re.UNICODE)


class App:
    def __init__(self) -> None:
        self.client = SteamClient()
        self.settings = Settings(language="english", data_dir=default_data_dir())

    def run(self) -> None:
        _configure_stdio()
        self.ensure_settings()
        self._pause()
        while True:
            _clear_screen()
            choice = self._ask(
                f"Data folder: {self.settings.data_dir}\n"
                "1. Create a review table for a game\n"
                "2. Update settings\n"
                "3. Analyze data\n"
                "4. Game details\n"
                "5. Delete game data\n"
                "6. Exit\n"
                "Choose an option: "
            )
            if choice == "1":
                self._safe(self.create_reviews)
                self._pause()
            elif choice == "2":
                if not self.update_settings():
                    return
            elif choice == "3":
                self.analysis_menu()
            elif choice == "4":
                self._safe(self.show_game)
                self._pause()
            elif choice == "5":
                self._safe(self.delete_game)
                self._pause()
            elif choice == "6":
                print("Exit.")
                return
            elif choice:
                print("Unknown option.")
                self._pause()

    def ensure_settings(self) -> None:
        loaded = load_settings()
        if loaded is None:
            print("First launch. Settings need to be saved.")
            print(f"They are stored in the registry at HKEY_CURRENT_USER\\{KEY_PATH}.")
            self._wizard()
            return
        try:
            prepare_data_dir(loaded.data_dir)
        except OSError as exc:
            print(f"Data folder is not available: {exc}")
            self._wizard()
            return
        self.settings = loaded
        print(f"Settings loaded. Game title language: {loaded.language}.")

    def update_settings(self) -> bool:
        while True:
            _clear_screen()
            choice = self._ask(
                "Current settings:\n"
                f"  Title and genre language: {self.settings.language}\n"
                f"  Data folder: {self.settings.data_dir}\n"
                "1. Change title language\n"
                "2. Change data folder\n"
                "3. Delete settings and data\n"
                "0. Back\n"
                "Choose an option: "
            )
            if choice == "1":
                language = self._ask_language(self.settings.language)
                self.settings = Settings(language=language, data_dir=self.settings.data_dir)
                save_settings(self.settings)
                print("Language saved. Already downloaded titles update the next time you fetch that game.")
                self._pause()
            elif choice == "2":
                data_dir = self._ask_data_dir(self.settings.data_dir)
                prepare_data_dir(data_dir)
                self.settings = Settings(language=self.settings.language, data_dir=data_dir)
                save_settings(self.settings)
                print("Folder saved. Existing CSV files were left in the previous folder.")
                self._pause()
            elif choice == "3":
                exiting = self._delete_user_data()
                self._pause()
                if exiting:
                    return False
            elif choice in {"0", ""}:
                return True
            elif choice:
                print("Unknown option.")
                self._pause()

    def analysis_menu(self) -> None:
        while True:
            _clear_screen()
            choice = self._ask(
                "Data analysis:\n"
                "3.1 Review summary\n"
                "3.2 Word map\n"
                "0. Back\n"
                "Choose an option: "
            )
            if choice in {"1", "3.1"}:
                self._safe(self.show_overview)
                self._pause()
            elif choice in {"2", "3.2"}:
                self._safe(self.show_word_map)
                self._pause()
            elif choice in {"0", ""}:
                return
            elif choice:
                print("Unknown option.")
                self._pause()

    def show_game(self) -> None:
        _clear_screen()
        rows = self._print_saved_games("Saved games:", numbered=True)
        if not rows:
            return
        selected = self._ask_game_number(rows)
        if selected is None:
            print("Cancelled.")
            return
        app_id, name, review_count = selected
        games = load_games(games_path(self.settings.data_dir))
        game = next((row for row in games if row.get("app_id") == app_id), None)
        reviews = [
            row
            for row in load_reviews(reviews_path(self.settings.data_dir))
            if row.get("app_id") == app_id
        ]
        stats = sample_stats(reviews)
        title = game.get("name") if game and game.get("name") else name
        print()
        print(title)
        print(f"AppID: {app_id}")
        if game is None:
            print("This game has no row in the games table.")
        else:
            print(f"Genres: {game.get('genres') or '—'}")
            print(f"Tags: {game.get('tags') or '—'}")
            print(f"Positive Steam reviews: {game.get('positive_reviews') or '0'}")
            print(f"Total Steam reviews: {game.get('total_reviews') or '0'}")
        print(f"Downloaded reviews: {review_count}")
        print(f"Positive among downloaded: {format_percent(stats.positive, stats.count)}")
        print(f"Median lifetime playtime: {format_playtime(stats.median_minutes)}")

    def delete_game(self) -> None:
        _clear_screen()
        rows = self._print_saved_games("Delete game data:", numbered=True)
        if not rows:
            return
        selected = self._ask_game_number(rows)
        if selected is None:
            print("Cancelled.")
            return
        app_id, name, review_count = selected
        print(f"This will delete “{name}” and {review_count} reviews.")
        if not self._ask_yes_no("Delete?"):
            print("Deletion cancelled.")
            return
        removed_reviews, game_removed, removed_files = delete_app_data(self.settings.data_dir, app_id)
        if game_removed:
            print("Game row deleted.")
        print(f"Reviews deleted: {removed_reviews}.")
        for path in removed_files:
            print(f"File deleted: {path}")

    def create_reviews(self) -> None:
        rows = self._print_saved_games("Saved games:", numbered=True)
        app_id = self._ask_loaded_or_new_game(rows)
        if app_id is None:
            return
        print("Fetching game details...")
        details = self.client.fetch_game(app_id, self.settings.language)
        summary = self.client.fetch_summary(app_id)
        print(f"{details.name} ({details.app_id})")
        if summary.score_label:
            print(f"Steam score: {summary.score_label}")
        print(f"Steam has {summary.positive} positive reviews out of {summary.total}.")
        limit = self._ask_limit()
        planned = summary.total if limit is None else min(limit, summary.total)
        existing = sum(
            1
            for row in load_reviews(reviews_path(self.settings.data_dir))
            if row.get("app_id") == details.app_id
        )
        if existing:
            print(f"The table already has {existing} reviews for this game. They will be replaced.")
        if planned > 2000:
            pages = max(1, (planned + 99) // 100)
            print(f"About {pages} requests are required. A large game can take many minutes.")
            if not self._ask_yes_no("Continue?"):
                print("Cancelled.")
                return
        if planned == 0:
            reviews = []
        else:
            print("Downloading reviews...")
            try:
                reviews = self.client.fetch_reviews(
                    app_id,
                    limit,
                    on_progress=lambda count: print(
                        f"\rReviews downloaded: {count}",
                        end="",
                        flush=True,
                    ),
                )
            finally:
                print()
        print("Fetching tags...")
        tags, tag_error = self.client.fetch_tags(app_id)
        if tag_error:
            print(f"Tags were not loaded: {tag_error}")
        game_row = {
            "app_id": details.app_id,
            "name": details.name,
            "genres": details.genres,
            "tags": tags,
            "positive_reviews": str(summary.positive),
            "total_reviews": str(summary.total),
        }
        data_dir = self.settings.data_dir
        replace_app_reviews(
            reviews_path(data_dir),
            details.app_id,
            [review.as_row() for review in reviews],
        )
        upsert_game(games_path(data_dir), game_row)
        print(f"Done. Reviews saved: {len(reviews)}.")
        print(f"Genres: {details.genres or '—'}")
        print(f"Tags: {tags or '—'}")
        print(f"Reviews: {reviews_path(data_dir)}")
        print(f"Games: {games_path(data_dir)}")

    def show_overview(self) -> None:
        selected = self._choose_reviews()
        if selected is None:
            return
        label, reviews, breakdown = selected
        games = load_games(games_path(self.settings.data_dir))
        if breakdown:
            title = "All downloaded games"
        else:
            name = next((row.get("name") or label for row in games if row.get("app_id") == label), label)
            title = f"{name} ({label})"
        print()
        print(format_overview(reviews, games, title=title, breakdown=breakdown))

    def show_word_map(self) -> None:
        selected = self._choose_reviews()
        if selected is None:
            return
        label, reviews, _breakdown = selected
        frequencies = word_frequencies([row.get("review_text", "") for row in reviews])
        if not frequencies:
            print("No words were left for the map after common words were filtered out.")
            return
        title, path = self._word_map_target(label)
        save_word_map(frequencies, path, title)
        if label != "all" and path.parent.is_dir():
            for old in path.parent.glob(f"{label}_*.png"):
                if old != path:
                    old.unlink()
        print()
        print("Most frequent words:")
        for word, count in Counter(frequencies).most_common(10):
            print(f"  {word}: {count}")
        print(f"Word map saved: {path}")
        _open_file(path)

    def _wizard(self) -> None:
        print("A Steam API key is not required: reviews come from the public store.")
        print("Language affects titles and genres. Review text is downloaded in every language.")
        language = self._ask_language("english")
        data_dir = self._ask_data_dir(default_data_dir())
        prepare_data_dir(data_dir)
        self.settings = Settings(language=language, data_dir=data_dir)
        save_settings(self.settings)
        print(f"Settings saved to HKEY_CURRENT_USER\\{KEY_PATH}.")

    def _delete_user_data(self) -> bool:
        print(f"Settings are stored in HKEY_CURRENT_USER\\{KEY_PATH}.")
        if not self._ask_yes_no("Delete saved settings?"):
            print("Deletion cancelled.")
            return False
        remove_files = self._ask_yes_no("Also delete CSV files and word maps from the data folder?")
        removed: list[str] = []
        if remove_files:
            removed = delete_generated_data(self.settings.data_dir)
        delete_settings()
        print("Settings were removed from the registry.")
        for path in removed:
            print(f"Deleted: {path}")
        if not self._ask_yes_no("Set up settings again?"):
            print("Exit.")
            return True
        self._wizard()
        return False

    def _choose_reviews(self) -> tuple[str, list[dict[str, str]], bool] | None:
        data_dir = self.settings.data_dir
        reviews = load_reviews(reviews_path(data_dir))
        games = load_games(games_path(data_dir))
        if not reviews and not games:
            print("No downloaded data yet. Create a review table in option 1 first.")
            return None
        while True:
            choice = self._ask(
                "1. One game\n"
                "2. All downloaded games\n"
                "0. Back\n"
                "Choose a scope: "
            )
            if choice in {"0", ""}:
                return None
            if choice == "2":
                if not reviews:
                    print("reviews.csv has no reviews.")
                    return None
                return "all", reviews, True
            if choice != "1":
                print("Unknown option.")
                continue
            rows = self._print_saved_games("Downloaded games:", numbered=True)
            if not rows:
                return None
            picked = self._ask_game_number(rows)
            if picked is None:
                return None
            app_id_value = picked[0]
            selected = [row for row in reviews if row.get("app_id") == app_id_value]
            if not selected:
                print("This game has no reviews in the table. Download them in option 1 first.")
                return None
            return str(app_id_value), selected, False

    def _word_map_target(self, label: str) -> tuple[str, Path]:
        folder = wordcloud_dir(self.settings.data_dir)
        if label == "all":
            return "All downloaded reviews", folder / "all.png"
        games = {row["app_id"]: row.get("name", "") for row in load_games(games_path(self.settings.data_dir))}
        name = games.get(label) or label
        title = f"{name} ({label})"
        slug = FILENAME_RE.sub("_", name).strip("_")[:40] or "game"
        return title, folder / f"{label}_{slug}.png"

    def _ask_language(self, current: str) -> str:
        examples = "russian, english, schinese, german, french"
        while True:
            raw = self._ask(f"Game title language [{current}]: ").strip().casefold()
            language = raw or current
            if language in STEAM_LANGUAGES:
                return language
            print(f"Unknown language code. For example: {examples}.")

    def _ask_data_dir(self, current: Path) -> Path:
        while True:
            raw = self._ask(f"Folder for CSV files and word maps [{current}]: ").strip().strip('"')
            path = Path(raw).expanduser() if raw else current
            try:
                path = path.resolve()
                if path.exists() and not path.is_dir():
                    print("Enter a folder, not a file.")
                    continue
                path.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                print(f"Could not use that folder: {exc}")
                continue
            return path

    def _ask_limit(self) -> int | None:
        while True:
            raw = self._ask("How many reviews should be downloaded? A number or all: ").strip().casefold()
            if raw in {"all", "все", "*"}:
                return None
            if raw.isdigit() and int(raw) > 0:
                return int(raw)
            print("Enter a positive number or all.")

    def _ask_app_id(self) -> int | None:
        while True:
            raw = self._ask("AppID or store link (empty cancels): ").strip()
            if not raw:
                return None
            if raw.isdigit() and 1 <= len(raw) <= 10:
                return int(raw)
            match = APP_URL_RE.search(raw)
            if match:
                return int(match.group(1))
            print("Enter an AppID, for example 620, or a link like https://store.steampowered.com/app/620/.")

    def _ask_yes_no(self, question: str) -> bool:
        while True:
            answer = self._ask(f"{question} [y/n]: ").strip().casefold()
            if answer in {"y", "yes", "д", "да"}:
                return True
            if answer in {"n", "no", "н", "нет"}:
                return False
            print("Enter y or n.")

    def _print_saved_games(self, title: str, *, numbered: bool = False) -> list[tuple[str, str, int]]:
        data_dir = self.settings.data_dir
        games = load_games(games_path(data_dir))
        reviews = load_reviews(reviews_path(data_dir))
        known = _known_games(games, reviews)
        if not known:
            print("No saved games yet.")
            return []
        counts: dict[str, int] = {}
        for row in reviews:
            app_id = row.get("app_id", "")
            if app_id:
                counts[app_id] = counts.get(app_id, 0) + 1
        rows = [(app_id, name, counts.get(app_id, 0)) for app_id, name in known]
        print(title)
        for index, (app_id, name, count) in enumerate(rows, start=1):
            if numbered:
                print(f"  {index}. {name}  | AppID {app_id} | reviews: {count}")
            else:
                print(f"  {app_id:>8}  {name}  | reviews: {count}")
        return rows

    def _ask_loaded_or_new_game(self, rows: list[tuple[str, str, int]]) -> int | None:
        if not rows:
            return self._ask_app_id()
        print("0. New game")
        while True:
            raw = self._ask("Game number (empty cancels): ")
            if not raw:
                return None
            if raw == "0":
                return self._ask_app_id()
            if raw.isdigit() and 1 <= int(raw) <= len(rows):
                return int(rows[int(raw) - 1][0])
            print(f"Enter a number from 1 to {len(rows)}, or 0 for a new game.")

    def _ask_game_number(self, rows: list[tuple[str, str, int]]) -> tuple[str, str, int] | None:
        while True:
            raw = self._ask("Game number (empty cancels): ")
            if not raw:
                return None
            if raw.isdigit() and 1 <= int(raw) <= len(rows):
                return rows[int(raw) - 1]
            print(f"Enter a number from 1 to {len(rows)}.")

    def _pause(self) -> None:
        self._ask("Press Enter to continue...")

    def _ask(self, text: str) -> str:
        try:
            return input(text).strip()
        except EOFError:
            print()
            raise SystemExit(0) from None

    def _safe(self, action) -> None:
        try:
            action()
        except SteamError as exc:
            print(f"Error: {exc}")
        except OSError as exc:
            print(f"File error: {exc}")
        except ValueError as exc:
            print(f"Error: {exc}")


def main() -> None:
    try:
        App().run()
    except KeyboardInterrupt:
        print("\nExit.")


def _clear_screen() -> None:
    if not sys.stdout.isatty():
        return
    os.system("cls" if os.name == "nt" else "clear")


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _known_games(games: list[dict[str, str]], reviews: list[dict[str, str]]) -> list[tuple[str, str]]:
    names = {row["app_id"]: row.get("name") or "untitled" for row in games if row.get("app_id")}
    app_ids = set(names) | {row.get("app_id", "") for row in reviews}
    app_ids.discard("")
    return sorted(((app_id, names.get(app_id) or "untitled") for app_id in app_ids), key=lambda item: item[1].casefold())


def _open_file(path: Path) -> None:
    startfile = getattr(os, "startfile", None)
    if startfile is None:
        return
    try:
        startfile(path)
    except OSError as exc:
        print(f"The file was saved, but it could not be opened: {exc}")
