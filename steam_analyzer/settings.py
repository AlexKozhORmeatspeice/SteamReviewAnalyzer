from __future__ import annotations

import winreg
from dataclasses import dataclass
from pathlib import Path

KEY_PATH = r"Software\SteamDataAnalyzer"

STEAM_LANGUAGES = frozenset(
    {
        "arabic",
        "brazilian",
        "bulgarian",
        "czech",
        "danish",
        "dutch",
        "english",
        "finnish",
        "french",
        "german",
        "greek",
        "hungarian",
        "indonesian",
        "italian",
        "japanese",
        "koreana",
        "latam",
        "norwegian",
        "polish",
        "portuguese",
        "romanian",
        "russian",
        "schinese",
        "spanish",
        "swedish",
        "tchinese",
        "thai",
        "turkish",
        "ukrainian",
        "vietnamese",
    }
)


@dataclass(frozen=True)
class Settings:
    language: str
    data_dir: Path


def default_data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


def load_settings() -> Settings | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY_PATH) as key:
            language = winreg.QueryValueEx(key, "language")[0]
            data_dir = winreg.QueryValueEx(key, "data_dir")[0]
    except OSError:
        return None
    if not isinstance(language, str) or not isinstance(data_dir, str):
        return None
    language = language.strip().casefold()
    if language not in STEAM_LANGUAGES or not data_dir.strip():
        return None
    return Settings(language=language, data_dir=Path(data_dir))


def save_settings(settings: Settings) -> None:
    if settings.language not in STEAM_LANGUAGES:
        raise ValueError(f"Unknown Steam language: {settings.language}")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY_PATH) as key:
        winreg.SetValueEx(key, "language", 0, winreg.REG_SZ, settings.language)
        winreg.SetValueEx(key, "data_dir", 0, winreg.REG_SZ, str(settings.data_dir))


def delete_settings() -> None:
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, KEY_PATH)
    except FileNotFoundError:
        return
