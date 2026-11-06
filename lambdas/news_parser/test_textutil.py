from textutil import clean_text


def test_unescapes_numeric_entities_in_title() -> None:
    assert (
        clean_text("TikTok&#8217;s For You page needs to change, says the EU")
        == "TikTok’s For You page needs to change, says the EU"
    )


def test_strips_html_tags_from_summary() -> None:
    raw = "<p>Diplomats signal <em>progress</em> after talks.</p>"
    assert clean_text(raw) == "Diplomats signal progress after talks."


def test_strips_superscript_to_plain_text() -> None:
    assert clean_text("ESC (DC)<sup>2</sup>") == "ESC (DC) 2"


def test_collapses_whitespace_and_handles_empty() -> None:
    assert clean_text("  a   <br/>  b\n\nc  ") == "a b c"
    assert clean_text(None) == ""
    assert clean_text("") == ""


def test_unescapes_nested_amp_entities() -> None:
    assert clean_text("TikTok&amp;#8217;s") == "TikTok’s"
