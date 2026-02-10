#!/usr/bin/env python3
"""
LinguaLibre → Malayalam Wiktionary Pronunciation Bot
=====================================================

A standalone pywikibot script that transfers audio pronunciation recordings
from Wikimedia Commons (recorded via LinguaLibre) to Malayalam Wiktionary
(ml.wiktionary.org).

Usage:
    # Dry-run mode (default) — preview changes without editing
    python lingualibre_ml_wikt_bot.py

    # Live mode — actually edit Malayalam Wiktionary pages
    python lingualibre_ml_wikt_bot.py --live

    # Process only specific words
    python lingualibre_ml_wikt_bot.py --words അമ്മ പശു ഇന്ത്യ

    # Limit batch size
    python lingualibre_ml_wikt_bot.py --limit 50

    # Filter by speaker
    python lingualibre_ml_wikt_bot.py --speaker "Vis M"

Requirements:
    pip install pywikibot requests

Configuration:
    Create a user-config.py file for pywikibot (see README).

Based on the LinguaLibre Bot project (https://github.com/lingua-libre/Lingua-Libre-Bot)
by WikiMedia France / LinguaLibre contributors, licensed under GPL-3.0.

Bot request: https://lingualibre.org/wiki/LinguaLibre:Bot/Requests
Original bot request by: Akbarali, Vis M (2023)
Script by: Netha Hussain
License: GPL-3.0 (to match the original LinguaLibre Bot)
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from typing import Optional

import requests

try:
    import pywikibot
    from pywikibot import pagegenerators
except ImportError:
    print("ERROR: pywikibot is required. Install with: pip install pywikibot")
    sys.exit(1)


# =============================================================================
# Constants
# =============================================================================

# LinguaLibre identifiers for Malayalam
LANG_QITEM = "Q36236"         # Wikidata QID for Malayalam
LANG_ISO639_3 = "mal"         # ISO 639-3 code
LANG_WM_CODE = "ml"           # Wikimedia language code
LL_FILE_PREFIX = f"LL-Q{LANG_QITEM[1:]} ({LANG_ISO639_3})"  # "LL-Q36236 (mal)"

# Malayalam Wiktionary section and template configuration
PRONUNCIATION_HEADER = "ഉച്ചാരണം"        # "Pronunciation" in Malayalam
AUDIO_TEMPLATE = "audio"                   # Template name
AUDIO_LABEL = "ശബ്ദം"                     # "Sound" in Malayalam

# Etymology section names (to detect and place pronunciation before)
ETYMOLOGY_HEADERS = {"നിരുക്തം", "പദോല്പത്തി", "പദോത്പത്തി"}

# Edit summary template (Malayalam)
# Translation: "Adding pronunciation from LinguaLibre."
EDIT_SUMMARY_TEMPLATE = "{filename}, LinguaLibre-യിൽ നിന്ന് ഉച്ചാരണം ചേർക്കുന്നു."

# LinguaLibre SPARQL endpoint (try multiple known URLs)
SPARQL_ENDPOINTS = [
    "https://lingualibre.org/sparql",
    "https://lingualibre.org/bigdata/namespace/wdq/sparql",
    "https://lingualibre.org/query/sparql",
]

# Regex to parse LinguaLibre filenames
# Format: LL-Q36236 (mal)-SPEAKER-WORD.wav
LL_FILENAME_REGEX = re.compile(
    r"^LL-Q\d+\s*\([a-z]{3}\)-(.+?)-(.+)\.(wav|ogg|mp3|flac)$"
)

# Rate limiting
EDIT_DELAY_SECONDS = 10  # Seconds between edits (be nice to the wiki)
SPARQL_DELAY_SECONDS = 2  # Seconds between SPARQL requests


# =============================================================================
# Logging setup
# =============================================================================

def setup_logging(log_file: Optional[str] = None, verbose: bool = False) -> logging.Logger:
    """Configure logging with both console and optional file output."""
    logger = logging.getLogger("ll_ml_bot")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    # File handler
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_fmt)
        logger.addHandler(file_handler)

    return logger


# =============================================================================
# SPARQL Queries
# =============================================================================

def query_lingualibre_recordings(
    logger: logging.Logger,
    speaker: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[dict]:
    """
    Query the LinguaLibre SPARQL endpoint for all Malayalam pronunciation
    recordings. Returns a list of dicts with keys: word, filename, speaker, date.
    """

    # Build the SPARQL query
    # Properties used by LinguaLibre:
    #   llp:P2  = "instance of" (Q2 = record)
    #   llp:P4  = "language" (Q36236 = Malayalam)
    #   llp:P5  = "speaker"
    #   llp:P7  = "transcription" (the word)
    #   llp:P3  = "media file name" (filename on Commons)
    sparql_query = """
    SELECT ?record ?word ?filename ?speakerLabel ?date WHERE {
      ?record prop:P2 entity:Q2 .
      ?record prop:P4 entity:Q36236 .
      ?record prop:P7 ?word .
      ?record prop:P3 ?filename .
      ?record prop:P5 ?speaker .
      OPTIONAL { ?record prop:P6 ?date . }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "ml,en" . }
    }
    ORDER BY ?word
    """

    if limit:
        sparql_query += f"\nLIMIT {limit}"

    logger.info("Querying LinguaLibre SPARQL endpoint for Malayalam recordings...")
    logger.debug(f"SPARQL query:\n{sparql_query}")

    # Try each known SPARQL endpoint URL
    data = None
    for endpoint in SPARQL_ENDPOINTS:
        try:
            logger.info(f"Trying SPARQL endpoint: {endpoint}")
            response = requests.get(
                endpoint,
                params={"query": sparql_query, "format": "json"},
                headers={
                    "User-Agent": "LinguaLibre-MalayalamWiktBot/1.0 (Malayalam Wiktionary pronunciation bot)",
                    "Accept": "application/sparql-results+json",
                },
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            logger.info(f"Successfully connected to {endpoint}")
            break
        except requests.exceptions.RequestException as e:
            logger.warning(f"Endpoint {endpoint} failed: {e}")
            continue

    if data is None:
        logger.error(
            "All SPARQL endpoints failed. Try --source commons to use "
            "the Wikimedia Commons API instead."
        )
        return []

    results = []
    bindings = data.get("results", {}).get("bindings", [])
    logger.info(f"SPARQL returned {len(bindings)} recording(s)")

    for binding in bindings:
        word = binding.get("word", {}).get("value", "").strip()
        filename = binding.get("filename", {}).get("value", "").strip()
        speaker_label = binding.get("speakerLabel", {}).get("value", "").strip()
        date = binding.get("date", {}).get("value", "")

        if not word or not filename:
            logger.warning(f"Skipping incomplete record: word={word!r}, filename={filename!r}")
            continue

        # Filter by speaker if requested
        if speaker and speaker.lower() not in speaker_label.lower():
            continue

        results.append({
            "word": word,
            "filename": filename,
            "speaker": speaker_label,
            "date": date,
        })

    logger.info(f"Found {len(results)} valid recording(s) after filtering")
    return results


def query_commons_for_files(
    logger: logging.Logger,
    limit: Optional[int] = None,
) -> list[dict]:
    """
    Query Wikimedia Commons for LinguaLibre Malayalam audio files.
    Uses the category 'Lingua Libre pronunciation-mal' for reliable results.
    """
    logger.info("Querying Wikimedia Commons for Malayalam LinguaLibre files...")

    category = f"Category:Lingua Libre pronunciation-{LANG_ISO639_3}"
    results = []
    api_url = "https://commons.wikimedia.org/w/api.php"
    continue_token = None
    count = 0

    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category,
            "cmlimit": min(500, limit - count if limit else 500),
            "cmtype": "file",
            "cmprop": "title|timestamp",
            "format": "json",
        }
        if continue_token:
            params["cmcontinue"] = continue_token

        try:
            logger.debug(f"Fetching batch from {category} (offset: {count})...")
            response = requests.get(
                api_url,
                params=params,
                headers={
                    "User-Agent": "LinguaLibre-MalayalamWiktBot/1.0",
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Commons API query failed: {e}")
            break

        members = data.get("query", {}).get("categorymembers", [])
        logger.debug(f"  Got {len(members)} file(s) in this batch")

        for member in members:
            # Title comes as "File:LL-Q36236 (mal)-Speaker-Word.wav"
            title = member.get("title", "")
            # Strip the "File:" prefix to get the bare filename
            filename = title.replace("File:", "", 1) if title.startswith("File:") else title

            match = LL_FILENAME_REGEX.match(filename)
            if match:
                speaker = match.group(1)
                word = match.group(2)
                results.append({
                    "word": word,
                    "filename": filename,
                    "speaker": speaker,
                    "date": member.get("timestamp", ""),
                })
                count += 1
            else:
                logger.debug(f"  Skipping non-matching file: {filename}")

        # Handle pagination
        if "continue" in data and (limit is None or count < limit):
            continue_token = data["continue"].get("cmcontinue")
            time.sleep(SPARQL_DELAY_SECONDS)
        else:
            break

        if limit and count >= limit:
            break

    logger.info(f"Found {len(results)} files on Commons")
    return results


def search_commons_for_words(
    logger: logging.Logger,
    words: list[str],
) -> list[dict]:
    """
    Search Wikimedia Commons for specific Malayalam words' audio files.
    Much faster than fetching the full category when you only need a few words.
    """
    logger.info(f"Searching Commons for {len(words)} specific word(s)...")

    results = []
    api_url = "https://commons.wikimedia.org/w/api.php"
    regex = LL_FILENAME_REGEX

    for word in words:
        # Search for files matching this word
        search_term = f"{LL_FILE_PREFIX}-*-{word}"
        logger.debug(f"  Searching for: {search_term}")

        try:
            response = requests.get(
                api_url,
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": f'"{LL_FILE_PREFIX}" "{word}"',
                    "srnamespace": 6,  # File namespace
                    "srlimit": 10,
                    "format": "json",
                },
                headers={
                    "User-Agent": "LinguaLibre-MalayalamWiktBot/1.0",
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"  Search failed for '{word}': {e}")
            continue

        search_results = data.get("query", {}).get("search", [])
        for sr in search_results:
            title = sr.get("title", "")
            filename = title.replace("File:", "", 1) if title.startswith("File:") else title
            match = regex.match(filename)
            if match and match.group(2) == word:
                speaker = match.group(1)
                results.append({
                    "word": word,
                    "filename": filename,
                    "speaker": speaker,
                    "date": "",
                })
                logger.info(f"  Found: {filename}")
                break  # One recording per word is enough
        else:
            logger.info(f"  No recording found for '{word}'")

        time.sleep(SPARQL_DELAY_SECONDS)

    logger.info(f"Found recordings for {len(results)} of {len(words)} word(s)")
    return results


# =============================================================================
# Wikitext parsing and editing
# =============================================================================

def parse_sections(wikitext: str) -> list[dict]:
    """
    Parse wikitext into a list of sections.
    Each section is a dict with: level, title, content, start_pos, end_pos.
    """
    # Match level-2 headers: ==Title==
    header_pattern = re.compile(r"^(={2,6})\s*(.+?)\s*\1\s*$", re.MULTILINE)

    sections = []
    last_end = 0

    for match in header_pattern.finditer(wikitext):
        level = len(match.group(1))
        title = match.group(2).strip()
        start = match.start()

        # Close the previous section
        if sections:
            sections[-1]["end_pos"] = start
            sections[-1]["content"] = wikitext[sections[-1]["content_start"]:start]

        sections.append({
            "level": level,
            "title": title,
            "header_text": match.group(0),
            "start_pos": start,
            "content_start": match.end(),
            "end_pos": len(wikitext),  # Will be updated
            "content": "",  # Will be updated
        })

    # Finalize last section
    if sections:
        sections[-1]["content"] = wikitext[sections[-1]["content_start"]:]
        sections[-1]["end_pos"] = len(wikitext)

    return sections


def page_has_audio(wikitext: str) -> bool:
    """Check if the page already contains any audio template."""
    # Match {{audio|...}} with any casing
    audio_pattern = re.compile(r"\{\{\s*audio\s*\|", re.IGNORECASE)
    return bool(audio_pattern.search(wikitext))


def find_pronunciation_section(sections: list[dict]) -> Optional[dict]:
    """Find the existing pronunciation section (==ഉച്ചാരണം==)."""
    for section in sections:
        if section["title"] == PRONUNCIATION_HEADER:
            return section
    return None


def find_first_section_index(sections: list[dict]) -> int:
    """
    Find the index where the pronunciation section should be inserted.
    Per the bot request, pronunciation goes as the first section.
    Returns 0 if no sections exist.
    """
    return 0  # Always insert at the beginning as per the request


def build_audio_line(filename: str) -> str:
    """Build the audio template line in the Malayalam Wiktionary format."""
    return f"* {AUDIO_LABEL}: {{{{audio|{filename}}}}}"


def add_pronunciation_to_page(
    wikitext: str,
    filename: str,
    logger: logging.Logger,
) -> Optional[str]:
    """
    Add a pronunciation audio entry to a Malayalam Wiktionary page.

    Returns the modified wikitext, or None if no modification is needed.

    Logic:
    1. If the page already has an audio file → skip (return None)
    2. If ==ഉച്ചാരണം== section exists → add audio line under it
    3. If no pronunciation section exists → create it as the first section
    """

    # Check if audio already exists
    if page_has_audio(wikitext):
        logger.info("  Page already has audio — skipping")
        return None

    audio_line = build_audio_line(filename)
    sections = parse_sections(wikitext)
    pron_section = find_pronunciation_section(sections)

    if pron_section:
        # === Case A: Pronunciation section exists, add audio to it ===
        logger.info("  Found existing pronunciation section — adding audio")

        insert_pos = pron_section["content_start"]
        # Find the end of the header line (after the newline)
        # We want to insert right after the header
        remaining = wikitext[insert_pos:]

        # Skip any leading whitespace/newlines after the header
        stripped = remaining.lstrip("\n")
        skip_count = len(remaining) - len(stripped)
        insert_pos += skip_count

        # Insert the audio line
        new_wikitext = (
            wikitext[:insert_pos]
            + audio_line + "\n"
            + wikitext[insert_pos:]
        )
        return new_wikitext

    else:
        # === Case B: No pronunciation section — create one ===
        logger.info("  No pronunciation section found — creating one")

        new_section = f"\n=={PRONUNCIATION_HEADER}==\n{audio_line}\n"

        if not sections:
            # Page has no sections at all — append the pronunciation section
            # after any leading content
            new_wikitext = wikitext.rstrip("\n") + "\n" + new_section + "\n"
        else:
            # Insert before the first section
            first_section_pos = sections[0]["start_pos"]

            # Get everything before the first section
            preamble = wikitext[:first_section_pos].rstrip("\n")
            rest = wikitext[first_section_pos:]

            if preamble:
                new_wikitext = preamble + "\n" + new_section + "\n" + rest
            else:
                new_wikitext = new_section + "\n" + rest

        return new_wikitext


# =============================================================================
# Bot core logic
# =============================================================================

class MalayalamPronunciationBot:
    """
    Bot that adds LinguaLibre pronunciation recordings to Malayalam Wiktionary.
    Uses the MediaWiki API directly for reliable BotPassword authentication.
    """

    API_URL = f"https://{LANG_WM_CODE}.wiktionary.org/w/api.php"
    USER_AGENT = "LinguaLibre-MalayalamWiktBot/1.0"

    def __init__(
        self,
        dry_run: bool = True,
        edit_delay: int = EDIT_DELAY_SECONDS,
        logger: Optional[logging.Logger] = None,
    ):
        self.dry_run = dry_run
        self.edit_delay = edit_delay
        self.logger = logger or logging.getLogger("ll_ml_bot")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.USER_AGENT})

        if not dry_run:
            self._login()
        else:
            self.logger.info("DRY RUN mode — no edits will be made")

        # Statistics
        self.stats = {
            "total_recordings": 0,
            "pages_checked": 0,
            "pages_edited": 0,
            "pages_skipped_has_audio": 0,
            "pages_skipped_not_found": 0,
            "pages_skipped_redirect": 0,
            "pages_skipped_error": 0,
            "pages_created_section": 0,
            "pages_added_to_existing": 0,
        }

    def _read_credentials(self) -> tuple:
        """Read bot credentials from user-password.py."""
        pw_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user-password.py")
        if not os.path.exists(pw_file):
            raise FileNotFoundError(f"Password file not found: {pw_file}")

        with open(pw_file, "r") as f:
            content = f.read()

        # Try BotPassword format: ("User", BotPassword("botname", "password"))
        m = re.search(r'BotPassword\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)', content)
        if m:
            # Read base username from user-config.py
            cfg_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user-config.py")
            base_user = "Netha Hussain"  # default
            if os.path.exists(cfg_file):
                with open(cfg_file, "r") as f:
                    for line in f:
                        um = re.search(r"usernames\[.*\]\[.*\]\s*=\s*['\"](.+?)['\"]", line)
                        if um:
                            base_user = um.group(1)
                            break
            return f"{base_user}@{m.group(1)}", m.group(2)

        # Try simple tuple format: ("user@bot", "password")
        m = re.search(r'\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)', content)
        if m:
            return m.group(1), m.group(2)

        raise ValueError("Cannot parse credentials from user-password.py")

    def _login(self):
        """Login using BotPassword via the MediaWiki action=login API."""
        username, password = self._read_credentials()
        self.logger.info(f"Logging in as {username}...")

        # Step 1: Get login token
        r = self.session.get(self.API_URL, params={
            "action": "query", "meta": "tokens", "type": "login", "format": "json"
        }, timeout=30)
        token = r.json()["query"]["tokens"]["logintoken"]

        # Step 2: Login
        r = self.session.post(self.API_URL, data={
            "action": "login", "lgname": username, "lgpassword": password,
            "lgtoken": token, "format": "json"
        }, timeout=30)

        result = r.json().get("login", {})
        if result.get("result") != "Success":
            raise RuntimeError(f"Login failed: {result}")

        self.logger.info(f"Logged in as {result.get('lgusername', username)}")

    def _get_csrf_token(self) -> str:
        """Get a CSRF edit token."""
        r = self.session.get(self.API_URL, params={
            "action": "query", "meta": "tokens", "format": "json"
        }, timeout=30)
        return r.json()["query"]["tokens"]["csrftoken"]

    def _get_page(self, title: str) -> Optional[dict]:
        """
        Get page content from the API.
        Returns dict with 'content', 'exists', 'redirect' keys, or None on error.
        """
        r = self.session.get(self.API_URL, params={
            "action": "query", "titles": title,
            "prop": "revisions|info", "rvprop": "content",
            "rvslots": "main", "format": "json"
        }, timeout=30)

        pages = r.json().get("query", {}).get("pages", {})
        page_data = list(pages.values())[0]

        if "missing" in page_data:
            return {"exists": False, "redirect": False, "content": ""}

        if "redirect" in page_data:
            return {"exists": True, "redirect": True, "content": ""}

        try:
            content = page_data["revisions"][0]["slots"]["main"]["*"]
            # Check if it's a redirect by content
            is_redirect = content.strip().lower().startswith("#redirect") or \
                          content.strip().startswith("#തിരിച്ചുവിടുക")
            return {"exists": True, "redirect": is_redirect, "content": content}
        except (KeyError, IndexError):
            return None

    def _edit_page(self, title: str, text: str, summary: str) -> bool:
        """Edit a page via the API. Returns True on success."""
        token = self._get_csrf_token()
        r = self.session.post(self.API_URL, data={
            "action": "edit", "title": title, "text": text,
            "summary": summary, "bot": "1",
            "token": token, "format": "json"
        }, timeout=60)

        result = r.json()
        if "edit" in result and result["edit"].get("result") == "Success":
            return True

        self.logger.error(f"  Edit API error: {result}")
        return False

    def process_recording(self, recording: dict) -> bool:
        """
        Process a single recording: check the target page and add audio if appropriate.
        Returns True if the page was edited (or would be in dry-run mode).
        """
        word = recording["word"]
        filename = recording["filename"]
        speaker = recording["speaker"]

        self.logger.info(f"Processing: '{word}' (file: {filename}, speaker: {speaker})")
        self.stats["pages_checked"] += 1

        # 1. Get page content
        page_data = self._get_page(word)
        if page_data is None:
            self.logger.error(f"  Error reading page '{word}'")
            self.stats["pages_skipped_error"] += 1
            return False

        if not page_data["exists"]:
            self.logger.info(f"  Page '{word}' does not exist — skipping")
            self.stats["pages_skipped_not_found"] += 1
            return False

        if page_data["redirect"]:
            self.logger.info(f"  Page '{word}' is a redirect — skipping")
            self.stats["pages_skipped_redirect"] += 1
            return False

        current_text = page_data["content"]

        # 2. Attempt to add pronunciation
        new_text = add_pronunciation_to_page(current_text, filename, self.logger)

        if new_text is None:
            self.stats["pages_skipped_has_audio"] += 1
            return False

        # 3. Determine what changed
        sections = parse_sections(current_text)
        had_pron_section = find_pronunciation_section(sections) is not None

        if had_pron_section:
            self.stats["pages_added_to_existing"] += 1
        else:
            self.stats["pages_created_section"] += 1

        # 4. Build edit summary
        edit_summary = EDIT_SUMMARY_TEMPLATE.format(filename=filename)

        # 5. Perform the edit
        if self.dry_run:
            self.logger.info(f"  [DRY RUN] Would edit '{word}' with summary: {edit_summary}")
            self.logger.debug(f"  [DRY RUN] New text preview:\n{new_text[:500]}...")
            self.stats["pages_edited"] += 1
            return True
        else:
            if self._edit_page(word, new_text, edit_summary):
                self.logger.info(f"  Successfully edited '{word}'")
                self.stats["pages_edited"] += 1
                time.sleep(self.edit_delay)
                return True
            else:
                self.logger.error(f"  Failed to save '{word}'")
                self.stats["pages_skipped_error"] += 1
                return False

    def run(
        self,
        recordings: list[dict],
        words_filter: Optional[list[str]] = None,
    ):
        """
        Process a batch of recordings.

        Args:
            recordings: List of recording dicts from SPARQL/Commons query
            words_filter: Optional list of specific words to process
        """
        self.stats["total_recordings"] = len(recordings)

        # Filter by specific words if requested
        if words_filter:
            words_set = set(words_filter)
            recordings = [r for r in recordings if r["word"] in words_set]
            self.logger.info(
                f"Filtered to {len(recordings)} recording(s) matching requested words"
            )

        # De-duplicate: keep only one recording per word (prefer the first/earliest)
        seen_words = set()
        unique_recordings = []
        for rec in recordings:
            if rec["word"] not in seen_words:
                seen_words.add(rec["word"])
                unique_recordings.append(rec)
            else:
                self.logger.debug(
                    f"  Duplicate recording for '{rec['word']}' — using first occurrence"
                )

        self.logger.info(
            f"Processing {len(unique_recordings)} unique word(s) "
            f"(from {len(recordings)} total recording(s))"
        )

        # Process each recording
        for i, recording in enumerate(unique_recordings, 1):
            self.logger.info(f"\n--- [{i}/{len(unique_recordings)}] ---")
            try:
                self.process_recording(recording)
            except KeyboardInterrupt:
                self.logger.warning("\nInterrupted by user — stopping")
                break
            except Exception as e:
                self.logger.error(
                    f"Unexpected error processing '{recording['word']}': {e}",
                    exc_info=True,
                )
                self.stats["pages_skipped_error"] += 1

        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print a summary of the bot run."""
        s = self.stats
        mode = "DRY RUN" if self.dry_run else "LIVE"

        self.logger.info("\n" + "=" * 60)
        self.logger.info(f"  Bot Run Summary ({mode})")
        self.logger.info("=" * 60)
        self.logger.info(f"  Total recordings found:        {s['total_recordings']}")
        self.logger.info(f"  Pages checked:                 {s['pages_checked']}")
        self.logger.info(f"  Pages edited/would edit:       {s['pages_edited']}")
        self.logger.info(f"    - New section created:       {s['pages_created_section']}")
        self.logger.info(f"    - Added to existing section: {s['pages_added_to_existing']}")
        self.logger.info(f"  Pages skipped (has audio):     {s['pages_skipped_has_audio']}")
        self.logger.info(f"  Pages skipped (not found):     {s['pages_skipped_not_found']}")
        self.logger.info(f"  Pages skipped (redirect):      {s['pages_skipped_redirect']}")
        self.logger.info(f"  Pages skipped (error):         {s['pages_skipped_error']}")
        self.logger.info("=" * 60)


# =============================================================================
# CLI entry point
# =============================================================================

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="LinguaLibre → Malayalam Wiktionary Pronunciation Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry-run (preview changes, no edits):
  python lingualibre_ml_wikt_bot.py

  # Live mode (actually edit pages):
  python lingualibre_ml_wikt_bot.py --live

  # Process specific words only:
  python lingualibre_ml_wikt_bot.py --words അമ്മ പശു ഇന്ത്യ

  # Limit to 20 recordings:
  python lingualibre_ml_wikt_bot.py --limit 20

  # Filter by speaker:
  python lingualibre_ml_wikt_bot.py --speaker "Vis M"

  # Use Commons API instead of SPARQL:
  python lingualibre_ml_wikt_bot.py --source commons

  # Verbose logging to file:
  python lingualibre_ml_wikt_bot.py --verbose --log-file bot_run.log
        """,
    )

    parser.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Enable live editing (default: dry-run mode)",
    )
    parser.add_argument(
        "--words",
        nargs="+",
        help="Process only these specific words (space-separated Malayalam words)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of recordings to process",
    )
    parser.add_argument(
        "--speaker",
        type=str,
        default=None,
        help="Filter recordings by speaker name",
    )
    parser.add_argument(
        "--source",
        choices=["sparql", "commons"],
        default="commons",
        help="Data source: 'commons' (Wikimedia Commons API, default) or 'sparql' (LinguaLibre endpoint)",
    )
    parser.add_argument(
        "--edit-delay",
        type=int,
        default=EDIT_DELAY_SECONDS,
        help=f"Seconds to wait between edits (default: {EDIT_DELAY_SECONDS})",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose/debug logging",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Write logs to this file",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    # Setup logging
    log_file = args.log_file or f"ll_ml_bot_{datetime.now():%Y%m%d_%H%M%S}.log"
    logger = setup_logging(log_file=log_file, verbose=args.verbose)

    logger.info("=" * 60)
    logger.info("  LinguaLibre → Malayalam Wiktionary Pronunciation Bot")
    logger.info("=" * 60)
    logger.info(f"  Mode:       {'LIVE' if args.live else 'DRY RUN'}")
    logger.info(f"  Source:     {args.source}")
    logger.info(f"  Limit:      {args.limit or 'unlimited'}")
    logger.info(f"  Speaker:    {args.speaker or 'all'}")
    logger.info(f"  Words:      {args.words or 'all'}")
    logger.info(f"  Edit delay: {args.edit_delay}s")
    logger.info(f"  Log file:   {log_file}")
    logger.info("")

    # Safety confirmation for live mode
    if args.live:
        logger.warning("⚠ LIVE MODE: This will edit Malayalam Wiktionary pages!")
        confirm = input("Type 'yes' to confirm: ").strip().lower()
        if confirm != "yes":
            logger.info("Aborted by user")
            sys.exit(0)

    # Fetch recordings
    # Use targeted search when specific words are given (much faster)
    if args.words and args.source == "commons":
        recordings = search_commons_for_words(
            logger=logger,
            words=args.words,
        )
    elif args.source == "sparql":
        recordings = query_lingualibre_recordings(
            logger=logger,
            speaker=args.speaker,
            limit=args.limit,
        )
    else:
        recordings = query_commons_for_files(
            logger=logger,
            limit=args.limit,
        )

    if not recordings:
        logger.warning("No recordings found — nothing to do")
        sys.exit(0)

    # Run the bot
    bot = MalayalamPronunciationBot(
        dry_run=not args.live,
        edit_delay=args.edit_delay,
        logger=logger,
    )
    bot.run(recordings, words_filter=args.words)

    logger.info("\nDone!")


if __name__ == "__main__":
    main()
