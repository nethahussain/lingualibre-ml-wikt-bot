# LinguaLibre → Malayalam Wiktionary Pronunciation Bot

A standalone Python bot that automatically transfers audio pronunciation recordings from [LinguaLibre](https://lingualibre.org) (hosted on Wikimedia Commons) to [Malayalam Wiktionary](https://ml.wiktionary.org) pages.

Based on the [LinguaLibre Bot](https://github.com/lingua-libre/Lingua-Libre-Bot) project by Wikimedia France / LinguaLibre contributors.

## What it does

1. **Queries** the Wikimedia Commons API for all Malayalam (`LL-Q36236 (mal)`) pronunciation recordings
2. **Checks** each corresponding Malayalam Wiktionary page
3. **Adds** the audio template under the `==ഉച്ചാരണം==` (Pronunciation) section — only if no audio file already exists
4. **Creates** the pronunciation section as the first section if it doesn't exist yet

### Example edit

Before:
```wikitext
==നിരുക്തം==
Etymology content...

==നാമം==
Definition here...
```

After:
```wikitext
==ഉച്ചാരണം==
* ശബ്ദം: {{audio|LL-Q36236 (mal)-Vis M-അമ്മ.wav}}

==നിരുക്തം==
Etymology content...

==നാമം==
Definition here...
```

## Setup

### 1. Install dependencies

```bash
pip install pywikibot requests
```

### 2. Configure credentials

Copy the sample config files and fill in your Wikimedia credentials:

```bash
cp user-config.py.sample user-config.py
cp user-password.py.sample user-password.py
```

Edit `user-config.py` and set your username. Edit `user-password.py` with your bot name and password.

To get a bot password, go to: https://ml.wiktionary.org/wiki/Special:BotPasswords

### 3. Get bot approval

Before running in live mode, you need bot approval from the Malayalam Wiktionary community.

## Usage

### Dry-run mode (default — no edits made)

```bash
python lingualibre_ml_wikt_bot.py
```

This will query all Malayalam recordings and show what edits **would** be made, without touching any pages.

### Live mode

```bash
python lingualibre_ml_wikt_bot.py --live
```

You'll be asked to type `yes` to confirm before any edits begin.

### Process specific words only

```bash
python lingualibre_ml_wikt_bot.py --words അമ്മ പശു ഇന്ത്യ
```

### Limit batch size

```bash
python lingualibre_ml_wikt_bot.py --limit 500
```

### Filter by speaker

```bash
python lingualibre_ml_wikt_bot.py --speaker "Vis M"
```

### All options

```
--live            Enable live editing (default: dry-run)
--words W [W ..]  Process only these specific Malayalam words
--limit N         Maximum number of recordings to process
--speaker NAME    Filter recordings by speaker name
--source {sparql,commons}   Data source (default: commons)
--edit-delay N    Seconds between edits (default: 10)
--verbose         Enable debug logging
--log-file FILE   Write logs to this file
```

## Running tests

```bash
pip install pytest
pytest test_bot_logic.py -v
```

## Files

| File | Description |
|------|-------------|
| `lingualibre_ml_wikt_bot.py` | Main bot script |
| `user-config.py.sample` | Pywikibot configuration template (copy to `user-config.py`) |
| `user-password.py.sample` | Password file template (copy to `user-password.py`) |
| `test_bot_logic.py` | Unit tests for wikitext manipulation logic |
| `.gitignore` | Excludes credentials and logs from version control |
| `LICENSE` | GPL-3.0 license |

## Technical details

- **Language code**: `mal` (ISO 639-3), `ml` (Wikimedia), `Q36236` (Wikidata)
- **File prefix**: `LL-Q36236 (mal)-`
- **Target section**: `==ഉച്ചാരണം==`
- **Audio template**: `* ശബ്ദം: {{audio|FILENAME}}`
- **Edit summary**: `FILENAME, LinguaLibre-യിൽ നിന്ന് ഉച്ചാരണം ചേർക്കുന്നു.`
- **Safety**: Only adds audio if none exists on the page; dry-run by default; rate-limited to 1 edit per 10 seconds

## Attribution

This bot was created in response to the [LinguaLibre Bot Request for Malayalam Wiktionary](https://lingualibre.org/wiki/LinguaLibre:Bot/Requests).

- **Original bot request by**: [Akbarali](https://lingualibre.org/wiki/User:Akbarali) and [Vis M](https://lingualibre.org/wiki/User:Vis_M) (2023)
- **Based on**: [LinguaLibre Bot](https://github.com/lingua-libre/Lingua-Libre-Bot) by Wikimedia France / LinguaLibre contributors (GPL-3.0)
- **Script by**: [Netha Hussain](https://ml.wiktionary.org/wiki/User:Netha_Hussain)

## License

This project is licensed under the [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.en.html), to match the original LinguaLibre Bot project.
