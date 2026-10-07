# Steam Data Analyzer

A Windows console app that downloads Steam game reviews and stores them for later analysis. It does not need a Steam API key. Review text, playtime, and scores come from the public Steam store. Game titles and genres use the language you choose at setup.

## Setup

You need Python 3.9 or newer on Windows. You can download it from the official Python website: https://www.python.org/downloads/

From the project folder:

```powershell
python -m pip install -r requirements.txt
python main.py
```

On the first launch the app asks for two settings:

1. **Game title language.** A Steam language code such as `english` or `russian`. This affects game titles and genres. Review text is always downloaded in every language.
2. **Data folder.** Where CSV files and word maps are saved. Press Enter to use the `data` folder in the project directory.

Those settings are stored in the Windows registry at `HKEY_CURRENT_USER\Software\SteamDataAnalyzer`. The next launch loads them and opens the menu.

## What the program does

The menu has six options:

1. **Create a review table for a game.** Pick a saved game by its number, or choose `0` to add a new game by AppID or Steam store link. The app asks how many reviews to download (`all` downloads every review). Existing reviews for that game are replaced. The game row is updated with the title, genres, tags, positive review count, and total review count.
2. **Update settings.** Change the title language or the data folder, or delete the saved settings. You can also delete the CSV files and word maps.
3. **Analyze data.** Review summary for one game or for every downloaded game: review count, percentage of positive reviews, and median lifetime playtime. The word map saves a PNG of the most common words in the review text.
4. **Game details.** Show the saved record for one game: genres, tags, Steam review totals, downloaded review count, and median playtime.
5. **Delete game data.** Remove one game, all of its reviews, and its word map. Other games stay in place.
6. **Exit.**

After each command the result stays on screen until you press Enter. The window is then cleared and the menu is shown again.

## Saved files

Inside the data folder:

| File | Contents |
| --- | --- |
| `games.csv` | AppID, title, genres, tags, positive Steam reviews, total Steam reviews |
| `reviews.csv` | Review id, text, lifetime playtime in minutes, language, AppID, and whether the review is positive |
| `wordclouds/` | PNG word maps. A new map for the same game replaces the previous file |

The positive percentage in `games.csv` is Steam's total for the whole game. The percentage and median playtime in analysis are calculated only from the reviews that were downloaded.
