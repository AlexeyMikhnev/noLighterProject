"""Очистка форматированного текста: белый список тегов, лимиты, подсчёт слов."""
from app.richtext import analyze, clean, plain_text, word_count


def test_script_and_attributes_are_removed():
    html = '<p onclick="x()">a</p><script>alert(1)</script><img src=x onerror=alert(1)><a href="javascript:1">b</a>'
    assert clean(html) == "<p>a</p><p>b</p>"


def test_allowed_formatting_is_kept():
    html = "<h2>H</h2><p><strong>a</strong> <em>b</em> <u>c</u> <s>d</s></p><blockquote><p>q</p></blockquote><ul><li>1</li></ul><hr>"
    assert clean(html) == html


def test_clean_is_idempotent_and_canonical():
    raw = "<div><b>x</b><i>y</i></div><ol><li><p>one</p></li></ol>"
    once = clean(raw)
    assert once == "<p><strong>x</strong><em>y</em></p><ol><li>one</li></ol>"
    assert clean(once) == once


def test_markup_does_not_count_towards_length():
    html, chars = analyze("<p><strong>раз</strong> <em>два</em></p>")
    assert chars == 7
    assert word_count(html) == 2
    assert plain_text("<p>a<br>b</p><p>c</p>") == "a\nb\nc"


def test_empty_and_whitespace_only():
    assert analyze("<p></p><p> </p>") == ("", 0)
