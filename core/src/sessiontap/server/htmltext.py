import io
import re
from typing import Any
from cssselect import SelectorError
from lxml.cssselect import CSSSelector
from lxml import etree, html as lxml_html
from sessiontap.server.sensitive import is_secret_key, mask

SKIP = frozenset({"script", "style", "noscript", "template", "svg", "head"})
BLOCK = frozenset(
    {
        "address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt",
        "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4",
        "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section",
        "table", "td", "th", "title", "tr", "ul",
    }
)  # fmt: skip
SPACES = re.compile(r"[ \t\r\f\v]+")
WHITESPACE = re.compile(r"\s+")
TEXT_CHARS = 1000
ATTR_CHARS = 300
HTML_CHARS = 3000


class _TextTarget:
    def __init__(self) -> None:
        self.buffer = io.StringIO()
        self.skipped: list[str] = []
        self.title = False

    def start(self, tag: str, attrib: dict[str, str]) -> None:
        if tag == "title":
            self.title = set(self.skipped) <= {"head"}
        elif tag in SKIP:
            self.skipped.append(tag)
        if tag in BLOCK and (self.title or not self.skipped):
            self.buffer.write("\n")

    def end(self, tag: str) -> None:
        if tag in BLOCK and (self.title or not self.skipped):
            self.buffer.write("\n")
        if tag == "title":
            self.title = False
        elif tag in SKIP and self.skipped:
            self.skipped.pop()

    def data(self, data: str) -> None:
        if self.title or not self.skipped:
            self.buffer.write(data)

    def close(self) -> io.StringIO:
        self.buffer.seek(0)
        return self.buffer


def html_to_text(html: str) -> str:
    target = _TextTarget()
    parser = etree.HTMLParser(target=target, encoding="utf-8", no_network=True)  # type: ignore[arg-type]
    parser.feed(html.encode("utf-8"))
    parser.close()
    out = io.StringIO()
    for line in target.close():
        line = SPACES.sub(" ", line).strip()
        if line:
            out.write(line if out.tell() == 0 else "\n" + line)
    return out.getvalue()


class InvalidSelector(ValueError):
    pass


def _trim(value: str, limit: int) -> str:
    return value[:limit] + "…" if len(value) > limit else value


def _mask_secrets(doc: lxml_html.HtmlElement) -> None:
    for el in doc.iter("meta", "input"):
        attr = "content" if el.tag == "meta" else "value"
        name = el.get("name") or el.get("property") or el.get("id") or ""
        if is_secret_key(name) and el.get(attr):
            el.set(attr, mask(el.get(attr)) or "")


def _parse(html: str) -> lxml_html.HtmlElement:
    parser = lxml_html.HTMLParser(encoding="utf-8", no_network=True)
    return lxml_html.document_fromstring(html.encode("utf-8"), parser=parser)


def select(html: str, selector: str, limit: int, include_html: bool) -> dict[str, Any]:
    try:
        query = CSSSelector(selector, translator="html")
    except SelectorError as e:
        raise InvalidSelector(str(e)) from e
    try:
        doc = _parse(html)
    except etree.ParserError:
        return {"total": 0, "matches": []}
    _mask_secrets(doc)
    result = query(doc)
    nodes = result if isinstance(result, list) else []
    found = [el for el in nodes if isinstance(el, lxml_html.HtmlElement)]
    matches = []
    for el in found[:limit]:
        match: dict[str, Any] = {
            "tag": el.tag,
            "text": _trim(WHITESPACE.sub(" ", " ".join(el.itertext())).strip(), TEXT_CHARS),
            "attrs": {k: _trim(v, ATTR_CHARS) for k, v in el.attrib.items()},
        }
        if include_html:
            raw = lxml_html.tostring(el, encoding="unicode", with_tail=False)
            match["html"] = _trim(raw, HTML_CHARS)
        matches.append(match)
    return {"total": len(found), "matches": matches}
