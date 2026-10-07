from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from wordcloud import WordCloud


def save_word_map(frequencies: dict[str, int], path: Path, title: str) -> None:
    if not frequencies:
        raise ValueError("There are no words for the map.")
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = dict(sorted(frequencies.items(), key=lambda item: (-item[1], item[0])))
    cloud = WordCloud(
        width=1600,
        height=900,
        background_color="white",
        font_path=_font_path(),
        max_words=200,
        collocations=False,
        normalize_plurals=False,
        prefer_horizontal=0.85,
        min_font_size=12,
        random_state=1,
        colormap="viridis",
    ).generate_from_frequencies(ordered)
    figure = plt.figure(figsize=(16, 9), dpi=100)
    try:
        plt.imshow(cloud.to_array(), interpolation="bilinear")
        plt.axis("off")
        figure.suptitle(title, fontsize=18)
        figure.savefig(path, bbox_inches="tight", facecolor="white")
    finally:
        plt.close(figure)


def _font_path() -> str:
    bundled = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"
    if bundled.is_file():
        return str(bundled)
    windows_font = Path(r"C:\Windows\Fonts\arial.ttf")
    if windows_font.is_file():
        return str(windows_font)
    from matplotlib import font_manager

    return font_manager.findfont("DejaVu Sans")
