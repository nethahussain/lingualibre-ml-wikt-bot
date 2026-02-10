#!/usr/bin/env python3
"""
Unit tests for the LinguaLibre Malayalam Wiktionary Bot wikitext logic.
Run with: python -m pytest test_bot_logic.py -v
"""

import pytest

# We test only the wikitext manipulation functions — no pywikibot needed
import importlib.util
import sys
import os

# Import the bot module
spec = importlib.util.spec_from_file_location(
    "bot", os.path.join(os.path.dirname(__file__), "lingualibre_ml_wikt_bot.py")
)
bot = importlib.util.module_from_spec(spec)

# Prevent pywikibot import error during testing
sys.modules["pywikibot"] = type(sys)("pywikibot")
sys.modules["pywikibot.pagegenerators"] = type(sys)("pywikibot.pagegenerators")
sys.modules["pywikibot"].Site = lambda *a, **k: None
sys.modules["pywikibot"].Page = lambda *a, **k: None
sys.modules["pywikibot"].FilePage = lambda *a, **k: None
sys.modules["pywikibot"].exceptions = type(sys)("pywikibot.exceptions")
sys.modules["pywikibot"].exceptions.Error = Exception

spec.loader.exec_module(bot)

import logging
logger = logging.getLogger("test")


# =============================================================================
# Test: page_has_audio
# =============================================================================

class TestPageHasAudio:
    def test_no_audio(self):
        text = "==നാമം==\nഒരു വാക്ക്"
        assert bot.page_has_audio(text) is False

    def test_has_audio_template(self):
        text = "==ഉച്ചാരണം==\n* ശബ്ദം: {{audio|LL-Q36236 (mal)-Vis M-അമ്മ.wav}}"
        assert bot.page_has_audio(text) is True

    def test_has_audio_case_insensitive(self):
        text = "==ഉച്ചാരണം==\n* ശബ്ദം: {{Audio|LL-Q36236 (mal)-Vis M-അമ്മ.wav}}"
        assert bot.page_has_audio(text) is True

    def test_has_audio_with_spaces(self):
        text = "==ഉച്ചാരണം==\n* ശബ്ദം: {{ audio |LL-Q36236 (mal)-Vis M-അമ്മ.wav}}"
        assert bot.page_has_audio(text) is True


# =============================================================================
# Test: parse_sections
# =============================================================================

class TestParseSections:
    def test_empty_page(self):
        sections = bot.parse_sections("")
        assert sections == []

    def test_single_section(self):
        text = "==ഉച്ചാരണം==\nSome content"
        sections = bot.parse_sections(text)
        assert len(sections) == 1
        assert sections[0]["title"] == "ഉച്ചാരണം"
        assert sections[0]["level"] == 2

    def test_multiple_sections(self):
        text = "==ഉച്ചാരണം==\nPron content\n\n==നിരുക്തം==\nEtymology\n\n==നാമം==\nNoun stuff"
        sections = bot.parse_sections(text)
        assert len(sections) == 3
        assert sections[0]["title"] == "ഉച്ചാരണം"
        assert sections[1]["title"] == "നിരുക്തം"
        assert sections[2]["title"] == "നാമം"

    def test_nested_sections(self):
        text = "==നാമം==\nNoun stuff\n===ചേർച്ച===\nDeclension"
        sections = bot.parse_sections(text)
        assert len(sections) == 2
        assert sections[0]["level"] == 2
        assert sections[1]["level"] == 3

    def test_preamble_before_sections(self):
        """Text before the first section header should not create a section."""
        text = "Some preamble text\n\n==നാമം==\nNoun stuff"
        sections = bot.parse_sections(text)
        assert len(sections) == 1
        assert sections[0]["title"] == "നാമം"


# =============================================================================
# Test: build_audio_line
# =============================================================================

class TestBuildAudioLine:
    def test_basic(self):
        result = bot.build_audio_line("LL-Q36236 (mal)-Vis M-അമ്മ.wav")
        assert result == "* ശബ്ദം: {{audio|LL-Q36236 (mal)-Vis M-അമ്മ.wav}}"


# =============================================================================
# Test: add_pronunciation_to_page
# =============================================================================

class TestAddPronunciationToPage:
    filename = "LL-Q36236 (mal)-Vis M-അമ്മ.wav"
    expected_audio_line = "* ശബ്ദം: {{audio|LL-Q36236 (mal)-Vis M-അമ്മ.wav}}"

    def test_skip_if_audio_exists(self):
        """Should return None if audio already present."""
        text = "==ഉച്ചാരണം==\n* ശബ്ദം: {{audio|LL-Q36236 (mal)-Other-അമ്മ.wav}}\n\n==നാമം==\nDef"
        result = bot.add_pronunciation_to_page(text, self.filename, logger)
        assert result is None

    def test_add_to_existing_pronunciation_section(self):
        """Should add audio line to an existing empty pronunciation section."""
        text = "==ഉച്ചാരണം==\n\n==നാമം==\nDefinition here"
        result = bot.add_pronunciation_to_page(text, self.filename, logger)
        assert result is not None
        assert self.expected_audio_line in result
        assert "==ഉച്ചാരണം==" in result
        assert "==നാമം==" in result

    def test_create_pronunciation_section_before_etymology(self):
        """Should create pronunciation section before etymology."""
        text = "==നിരുക്തം==\nEtymology content\n\n==നാമം==\nDefinition"
        result = bot.add_pronunciation_to_page(text, self.filename, logger)
        assert result is not None
        assert f"=={bot.PRONUNCIATION_HEADER}==" in result
        assert self.expected_audio_line in result
        # Pronunciation should come before etymology
        pron_pos = result.index(f"=={bot.PRONUNCIATION_HEADER}==")
        etym_pos = result.index("==നിരുക്തം==")
        assert pron_pos < etym_pos

    def test_create_pronunciation_section_no_sections(self):
        """Should add pronunciation to a page with no sections."""
        text = "Just some content with no sections"
        result = bot.add_pronunciation_to_page(text, self.filename, logger)
        assert result is not None
        assert f"=={bot.PRONUNCIATION_HEADER}==" in result
        assert self.expected_audio_line in result

    def test_create_pronunciation_as_first_section(self):
        """Pronunciation section should always be the first section."""
        text = "==നാമം==\nDefinition\n\n==ക്രിയ==\nVerb stuff"
        result = bot.add_pronunciation_to_page(text, self.filename, logger)
        assert result is not None
        pron_pos = result.index(f"=={bot.PRONUNCIATION_HEADER}==")
        noun_pos = result.index("==നാമം==")
        assert pron_pos < noun_pos

    def test_preamble_preserved(self):
        """Any preamble text before sections should be preserved."""
        text = "{{മലയാളം}}\n\n==നാമം==\nDefinition"
        result = bot.add_pronunciation_to_page(text, self.filename, logger)
        assert result is not None
        assert "{{മലയാളം}}" in result
        assert self.expected_audio_line in result

    def test_pronunciation_section_with_ipa(self):
        """Should add audio to pronunciation section that already has IPA."""
        text = "==ഉച്ചാരണം==\n* {{IPA|ml|/amma/}}\n\n==നാമം==\nDef"
        result = bot.add_pronunciation_to_page(text, self.filename, logger)
        assert result is not None
        assert self.expected_audio_line in result
        assert "{{IPA|ml|/amma/}}" in result


# =============================================================================
# Test: filename regex
# =============================================================================

class TestFilenameRegex:
    def test_standard_filename(self):
        match = bot.LL_FILENAME_REGEX.match("LL-Q36236 (mal)-Vis M-അമ്മ.wav")
        assert match is not None
        assert match.group(1) == "Vis M"
        assert match.group(2) == "അമ്മ"
        assert match.group(3) == "wav"

    def test_ogg_extension(self):
        match = bot.LL_FILENAME_REGEX.match("LL-Q36236 (mal)-Speaker-പശു.ogg")
        assert match is not None
        assert match.group(2) == "പശു"
        assert match.group(3) == "ogg"

    def test_complex_speaker_name(self):
        match = bot.LL_FILENAME_REGEX.match("LL-Q36236 (mal)-Akbar Ali-ഇന്ത്യ.wav")
        assert match is not None
        assert match.group(1) == "Akbar Ali"
        assert match.group(2) == "ഇന്ത്യ"

    def test_non_matching(self):
        match = bot.LL_FILENAME_REGEX.match("some_random_file.wav")
        assert match is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
