"""Tests for Layer A text Unicode scrub."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "remove-ai-marks" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from text_unicode import clean_text, inspect_text  # noqa: E402


def test_strips_zero_width_and_soft_hyphen():
    raw = "Hello\u200bWorld\u00ad!"
    cleaned, stats = clean_text(raw)
    assert cleaned == "HelloWorld!"
    assert stats["removed_count"] >= 2


def test_normalizes_exotic_spaces():
    raw = "a\u2003b\u3000c"  # em space, ideographic space
    cleaned, stats = clean_text(raw)
    assert cleaned == "a b c"
    assert stats["replaced_count"] >= 2


def test_inspect_finds_zwsp():
    report = inspect_text("x\u200by")
    assert report.suspicious_total >= 1
    kinds = {h.kind for h in report.hits}
    assert "zwj_family" in kinds or "strip" in kinds


def test_inspect_tag_chars():
    # Language tag character U+E0041 (TAG LATIN CAPITAL LETTER A)
    raw = "hi" + chr(0xE0041) + "there"
    report = inspect_text(raw)
    assert report.suspicious_total >= 1
    assert any(h.kind == "tag_chars" for h in report.hits)
    cleaned, stats = clean_text(raw)
    assert chr(0xE0041) not in cleaned
    assert stats["removed_count"] >= 1


def test_inspect_bidi():
    raw = "ab\u202eef"  # RLO
    report = inspect_text(raw)
    assert any(h.kind == "bidi" for h in report.hits)
    cleaned, _ = clean_text(raw)
    assert "\u202e" not in cleaned


def test_clean_preserves_normal_text():
    raw = "Normal ASCII and café — fine."
    cleaned, stats = clean_text(raw)
    assert cleaned == raw
    assert stats["removed_count"] == 0


def test_aggressive_confusable():
    # Cyrillic 'а' (U+0430) looks like Latin 'a'
    raw = "p\u0430y"  # p + cyrillic a + y
    cleaned, _ = clean_text(raw, aggressive_homoglyphs=True)
    assert cleaned == "pay"


def test_clean_preserves_emoji_vs16():
    raw = "Balance returns. \u2696\ufe0f"  # ⚖️
    cleaned, stats = clean_text(raw)
    assert cleaned == raw
    assert stats["removed_count"] == 0


def test_clean_preserves_zwj_family():
    raw = "Family time: \U0001F468\u200D\U0001F469\u200D\U0001F467"  # 👨‍👩‍👧
    cleaned, stats = clean_text(raw)
    assert cleaned == raw
    assert stats["removed_count"] == 0


def test_clean_preserves_zwj_chain():
    raw = "\u2764\ufe0f\u200d\U0001F525"  # ❤️‍🔥
    cleaned, stats = clean_text(raw)
    assert cleaned == raw
    assert stats["removed_count"] == 0


def test_clean_strips_floating_emoji_glue():
    raw = "a\u200db\ufe0f"
    cleaned, stats = clean_text(raw)
    assert cleaned == "ab"
    assert stats["removed_count"] == 2


def test_inspect_emoji_glue_not_suspicious_by_default():
    raw = "Balance returns. \u2696\ufe0f Family time: \U0001F468\u200D\U0001F469\u200D\U0001F467"
    report = inspect_text(raw)
    assert report.suspicious_total == 0


def test_inspect_floating_emoji_glue_is_suspicious():
    raw = "a\u200d"
    report = inspect_text(raw)
    assert report.suspicious_total >= 1


def test_clean_strip_emoji_glue_flag():
    raw = "\u2696\ufe0f"
    cleaned, stats = clean_text(raw, strip_emoji_glue=True)
    assert cleaned == "\u2696"
    assert stats["removed_count"] == 1


def test_inspect_strip_emoji_glue_flag():
    raw = "\u2696\ufe0f"
    report = inspect_text(raw, strip_emoji_glue=True)
    assert report.suspicious_total >= 1


def test_clean_preserves_script_joiners():
    # Persian mi-ravam (ZWNJ) and a Devanagari conjunct (ZWJ) \u2014 orthographic.
    for raw in ("\u0645\u06cc\u200c\u0631\u0648\u0645", "\u0915\u094d\u200d\u0937"):
        cleaned, _ = clean_text(raw)
        assert cleaned == raw


def test_clean_preserves_flag_tag_sequence():
    # Scotland flag: emoji base U+1F3F4 + tag chars ending in U+E007F.
    raw = "\U0001F3F4\U000E0067\U000E0062\U000E0073\U000E0063\U000E0074\U000E007F"
    cleaned, _ = clean_text(raw)
    assert cleaned == raw


def test_clean_preserves_orthographic_arabic_cf():
    raw = "x\u0600y\u06ddz"  # ARABIC NUMBER SIGN, END OF AYAH
    cleaned, _ = clean_text(raw)
    assert cleaned == raw


def test_clean_still_strips_joiners_between_latin():
    # ZWJ/ZWNJ next to ASCII is a carrier, not orthography \u2014 still removed.
    for raw in ("a\u200db", "a\u200cb", "ab\u200c"):
        cleaned, _ = clean_text(raw)
        assert "\u200c" not in cleaned and "\u200d" not in cleaned


def test_strip_emoji_glue_flag_restores_blanket_strip():
    cleaned, _ = clean_text("\u0645\u06cc\u200c\u0631", strip_emoji_glue=True)
    assert "\u200c" not in cleaned
    assert clean_text("x\u0600y", strip_emoji_glue=True)[0] == "xy"


# ---------------------------------------------------------------------------
# Hangul fillers, line separators, private use, dense-run signal
# ---------------------------------------------------------------------------


def test_hangul_fillers_detected_and_stripped():
    # U+3164 HANGUL FILLER and U+FFA0 HALFWIDTH HANGUL FILLER render blank
    # but are Lo (not Cf), so they need explicit entries — the Cf catch-all
    # cannot see them.
    raw = "a\u3164b\uffa0c"
    report = inspect_text(raw)
    assert any(h.kind == "hangul_filler" for h in report.hits)
    assert report.suspicious_total == 2
    cleaned, stats = clean_text(raw)
    assert cleaned == "abc"
    assert stats["removed_count"] == 2


def test_line_separators_replaced_with_newline():
    raw = "one\u2028two\u2029three"
    report = inspect_text(raw)
    assert any(h.kind == "line_separator" for h in report.hits)
    cleaned, stats = clean_text(raw)
    assert cleaned == "one\ntwo\nthree"
    assert stats["replaced_count"] == 2


def test_private_use_detected_but_kept_by_default():
    # PUA is a stego channel but also where icon fonts live: flag always,
    # strip only in aggressive mode.
    raw = "icon:\ue900\uf8ff:end"
    report = inspect_text(raw)
    kinds = {h.kind for h in report.hits}
    assert "private_use" in kinds
    assert report.suspicious_total == 2
    cleaned, stats = clean_text(raw)
    assert cleaned == raw  # kept
    assert stats["removed_count"] == 0


def test_private_use_stripped_in_aggressive_mode():
    raw = "icon:\ue900\U000F0000:end"
    cleaned, stats = clean_text(raw, aggressive_homoglyphs=True)
    assert "\ue900" not in cleaned and "\U000F0000" not in cleaned
    assert cleaned == "icon::end"
    assert stats["removed_count"] == 2


def test_private_use_note_mentions_opt_in():
    report = inspect_text("x\ue901y")
    assert any("aggressive" in n for n in report.notes)


def test_dense_zero_width_run_note():
    # A long uninterrupted run is the shape of encoded payload carriers.
    payload = "\u200b\u200c\u200b\u200d\u200b\u2060\ufeff"
    report = inspect_text("front " + payload + " back")
    assert any("dense zero-width run" in n for n in report.notes)
    # Isolated marks must NOT trip the dense-run note.
    quiet = inspect_text("a\u200bb\u200cc\u200dd")
    assert not any("dense zero-width run" in n for n in quiet.notes)
