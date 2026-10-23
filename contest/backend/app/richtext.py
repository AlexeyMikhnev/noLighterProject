"""Форматированный текст рассказа: очистка HTML по белому списку.

Автор присылает HTML из редактора, а в базе и в ответах API живёт только результат очистки.
Это одновременно защита от XSS и от раскрытия автора: у разрешённых тегов нет атрибутов,
ссылок, картинок и стилей, поэтому в тексте нельзя спрятать подпись или внешний ресурс.

Разрешено: абзац, заголовок (h2), цитата, маркированный и нумерованный списки, горизонтальный
разделитель, перенос строки, а также жирный, курсив, подчёркнутый и зачёркнутый текст.
Всё остальное либо заменяется близким тегом (b -> strong, div -> p ...), либо «разворачивается»
(остаётся только текст), либо вырезается вместе с содержимым (script, style ...).
Выход канонический: повторная очистка своего же результата ничего не меняет.

Только стандартная библиотека.
"""
from __future__ import annotations

import re
from functools import lru_cache
from html import escape
from html.parser import HTMLParser

INLINE = ("strong", "em", "u", "s")  # порядок вложенности при выводе
ALIAS = {
    "b": "strong",
    "i": "em",
    "ins": "u",
    "strike": "s",
    "del": "s",
    "h1": "h2",
    "h3": "h2",
    "h4": "h2",
    "h5": "h2",
    "h6": "h2",
    "div": "p",
}
KNOWN = {"p", "h2", "blockquote", "ul", "ol", "li", "br", "hr", *INLINE}
VOID = {"br", "hr"}
# Эти теги вырезаются вместе с содержимым.
DROP = {
    "script", "style", "iframe", "object", "embed", "template", "noscript", "head", "title",
    "svg", "math", "textarea", "select", "button", "form", "audio", "video", "canvas", "applet",
}
MAX_DEPTH = 24
_WS = re.compile(r"[ \t\r\n\f\v ]+")


class _Node:
    __slots__ = ("tag", "children")

    def __init__(self, tag: str):
        self.tag = tag
        self.children: list = []


class _Tree(HTMLParser):
    """Разбирает HTML в дерево, оставляя только известные теги."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root")
        self.stack = [self.root]
        self.skip: str | None = None  # имя вырезаемого тега, внутри которого мы находимся
        self.skip_depth = 0

    def _tag(self, tag: str) -> str:
        return ALIAS.get(tag, tag)

    def handle_starttag(self, tag, attrs):
        if self.skip:
            if tag == self.skip:
                self.skip_depth += 1
            return
        if tag in DROP:
            self.skip, self.skip_depth = tag, 1
            return
        tag = self._tag(tag)
        if tag not in KNOWN:
            return  # неизвестный тег прозрачен: его содержимое останется
        node = _Node(tag)
        self.stack[-1].children.append(node)
        if tag not in VOID and len(self.stack) < MAX_DEPTH:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        if self.skip or tag in DROP:
            return
        tag = self._tag(tag)
        if tag in VOID:
            self.stack[-1].children.append(_Node(tag))

    def handle_endtag(self, tag):
        if self.skip:
            if tag == self.skip:
                self.skip_depth -= 1
                if self.skip_depth == 0:
                    self.skip = None
            return
        tag = self._tag(tag)
        if tag in VOID or tag not in KNOWN:
            return
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if not self.skip:
            self.stack[-1].children.append(data)


# Токены строки: ("t", текст, формат) или ("br",), формат — frozenset тегов INLINE.
_BR = ("br",)


def _trim(run: list) -> list:
    """Убирает пустые токены и пробелы/переносы по краям."""
    run = [t for t in run if t[0] == "br" or t[1]]
    while run and (run[0][0] == "br" or not run[0][1].strip()):
        run.pop(0)
    while run and (run[-1][0] == "br" or not run[-1][1].strip()):
        run.pop()
    if run and run[0][0] == "t":
        run[0] = ("t", run[0][1].lstrip(), run[0][2])
    if run and run[-1][0] == "t":
        run[-1] = ("t", run[-1][1].rstrip(), run[-1][2])
    return run


class _Builder:
    def __init__(self):
        self.blocks: list = []  # ("p"|"h2", run) | ("blockquote", [..]) | ("ul"|"ol", [run]) | ("hr",)
        self.run: list = []

    def flush(self, tag: str):
        run = _trim(self.run)
        self.run = []
        if run:
            self.blocks.append((tag, run))

    def text(self, s: str, fmt: frozenset):
        s = _WS.sub(" ", s)
        if not s:
            return
        prev = self.run[-1] if self.run else None
        if s.startswith(" ") and (prev is None or prev[0] == "br" or prev[1].endswith(" ")):
            s = s[1:]
        if s:
            self.run.append(("t", s, fmt))

    def feed(self, nodes, fmt: frozenset, tag: str):
        for n in nodes:
            if isinstance(n, str):
                self.text(n, fmt)
                continue
            t = n.tag
            if t == "br":
                self.run.append(_BR)
            elif t == "hr":
                self.flush(tag)
                self.blocks.append(("hr",))
            elif t in INLINE:
                self.feed(n.children, fmt | {t}, tag)
            elif t in ("p", "h2"):
                self.flush(tag)
                self.feed(n.children, fmt, t)
                self.flush(t)
            elif t == "blockquote":
                self.flush(tag)
                sub = _Builder()
                sub.feed(n.children, fmt, "p")
                sub.flush("p")
                self.blocks.append(("blockquote", _quote_blocks(sub.blocks)))
            elif t in ("ul", "ol"):
                self.flush(tag)
                items = _list_items(n, fmt)
                if items:
                    self.blocks.append((t, items))
            else:  # li вне списка и прочее: прозрачно
                self.feed(n.children, fmt, tag)


def _lines(blocks: list) -> list[list]:
    """Строки (списки токенов) блоков: нужно, чтобы вложенное внутри пункта списка не потерялось."""
    out: list[list] = []
    for b in blocks:
        if b[0] in ("p", "h2"):
            out.append(b[1])
        elif b[0] == "blockquote":
            out.extend(_lines(b[1]))
        elif b[0] in ("ul", "ol"):
            out.extend(b[1])
    return out


def _quote_blocks(blocks: list) -> list:
    """Внутри цитаты остаются только абзацы (заголовки, списки, разделители и вложенные цитаты — как абзацы)."""
    return [("p", line) for line in _lines(blocks)]


def _list_items(node: _Node, fmt: frozenset) -> list[list]:
    items: list[list] = []
    loose = _Builder()

    def close_loose():
        loose.flush("p")
        items.extend(_lines(loose.blocks))
        loose.blocks = []

    for child in node.children:
        if isinstance(child, _Node) and child.tag == "li":
            close_loose()
            sub = _Builder()
            sub.feed(child.children, fmt, "p")
            sub.flush("p")
            joined: list = []
            for line in _lines(sub.blocks):
                if joined:
                    joined.append(_BR)
                joined.extend(line)
            joined = _trim(joined)
            if joined:
                items.append(joined)
        else:
            loose.feed([child], fmt, "p")
    close_loose()
    return items


def _inline_html(run: list) -> str:
    out: list[str] = []
    for tok in run:
        if tok[0] == "br":
            out.append("<br>")
            continue
        s = escape(tok[1], quote=False)
        for tag in reversed(INLINE):
            if tag in tok[2]:
                s = f"<{tag}>{s}</{tag}>"
        out.append(s)
    return "".join(out)


def _block_html(b: tuple) -> str:
    kind = b[0]
    if kind == "hr":
        return "<hr>"
    if kind in ("p", "h2"):
        return f"<{kind}>{_inline_html(b[1])}</{kind}>"
    if kind == "blockquote":
        return "<blockquote>" + "".join(_block_html(x) for x in b[1]) + "</blockquote>"
    return f"<{kind}>" + "".join(f"<li>{_inline_html(i)}</li>" for i in b[1]) + f"</{kind}>"


def _text_len(run: list) -> int:
    return sum(len(t[1]) for t in run if t[0] == "t")


def _block_chars(b: tuple) -> int:
    kind = b[0]
    if kind == "hr":
        return 0
    if kind in ("p", "h2"):
        return _text_len(b[1])
    if kind == "blockquote":
        return sum(_block_chars(x) for x in b[1])
    return sum(_text_len(i) for i in b[1])


def _plain_lines(b: tuple) -> list[str]:
    kind = b[0]
    if kind == "hr":
        return ["***"]
    if kind in ("p", "h2"):
        return ["".join("\n" if t[0] == "br" else t[1] for t in b[1])]
    if kind == "blockquote":
        return [line for x in b[1] for line in _plain_lines(x)]
    return ["".join("\n" if t[0] == "br" else t[1] for t in i) for i in b[1]]


def _parse(html: str) -> list:
    tree = _Tree()
    tree.feed(html)
    tree.close()
    b = _Builder()
    b.feed(tree.root.children, frozenset(), "p")
    b.flush("p")
    return b.blocks


def clean(html: str) -> str:
    """Очищенный канонический HTML (пустая строка, если текста нет)."""
    return "".join(_block_html(b) for b in _parse(html))


def analyze(html: str) -> tuple[str, int]:
    """(очищенный HTML, число знаков текста без служебных символов)."""
    blocks = _parse(html)
    return "".join(_block_html(b) for b in blocks), sum(_block_chars(b) for b in blocks)


@lru_cache(maxsize=1024)
def plain_text(html: str) -> str:
    """Текст без разметки; абзацы разделены переводом строки."""
    return "\n".join(line for b in _parse(html) for line in _plain_lines(b))


def word_count(html: str) -> int:
    return len(plain_text(html).split())
