"""
Converts stored Markdown (project docs) into safe-to-render HTML.

Two-stage pipeline: markdown -> raw HTML -> sanitized HTML. The
sanitizer is the security boundary -- everything downstream (Jinja's
`| safe` filter in docs/view.html) trusts its output completely, so it
must never let a <script>, an event handler attribute, or a
javascript:/data: URL through.

Prefers `nh3` (Rust-based, actively maintained, the bleach team's
recommended successor) when it's installed -- add it to requirements.txt
and it's used automatically, no code change needed. Falls back to a
small hand-rolled allowlist sanitizer built on Python's stdlib
`html.parser` when nh3 isn't available, so this still works with zero
extra dependencies. The fallback is deliberately conservative (strips
anything not explicitly allowlisted rather than trying to detect and
remove specific attack patterns) and is exercised by a dedicated XSS
test battery in tests/test_sanitize.py -- if you're touching either
implementation, run those tests against a wide range of payloads
before trusting a change here.
"""
from __future__ import annotations

from html.parser import HTMLParser

import markdown as _markdown

try:
    import nh3 as _nh3
except ImportError:
    _nh3 = None

ALLOWED_TAGS = {
    "p", "br", "hr", "strong", "b", "em", "i", "u", "s", "del", "code", "pre",
    "blockquote", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "a", "table", "thead", "tbody", "tr", "th", "td", "span",
}
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "span": {"class"},
    "code": {"class"},  # fenced-code-block language hint, e.g. class="language-python"
}
ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}


def _safe_url(value: str) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    # Relative/fragment links (#section, /path) have no scheme -- allowed.
    if ":" not in value.split("/", 1)[0]:
        return value
    scheme = value.split(":", 1)[0].strip().lower()
    return value if scheme in ALLOWED_URL_SCHEMES else None


class _AllowlistSanitizer(HTMLParser):
    """Stdlib fallback used when nh3 isn't installed. Strips any tag not
    in ALLOWED_TAGS entirely (including its content, for tags like
    <script>/<style> where the content itself is dangerous), and drops
    any attribute not explicitly allowlisted for that tag -- href/src
    values additionally go through _safe_url()."""

    _CONTENT_STRIPPED_TAGS = {"script", "style", "iframe", "object", "embed", "form"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._skip_depth = 0  # >0 while inside a fully-stripped tag's content

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self._CONTENT_STRIPPED_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag not in ALLOWED_TAGS:
            return  # unknown/disallowed tag: drop the tag, keep its text content
        allowed_attrs = ALLOWED_ATTRIBUTES.get(tag, set())
        kept = []
        for name, value in attrs:
            name = name.lower()
            if name not in allowed_attrs:
                continue
            if name == "href":
                safe = _safe_url(value)
                if safe is None:
                    continue
                value = safe
            kept.append(f'{name}="{_escape_attr(value or "")}"')
        attr_str = (" " + " ".join(kept)) if kept else ""
        self.out.append(f"<{tag}{attr_str}>")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self._CONTENT_STRIPPED_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag in ALLOWED_TAGS:
            self.out.append(f"</{tag}>")

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if self._skip_depth or tag in self._CONTENT_STRIPPED_TAGS:
            return
        if tag in ("br", "hr") :
            self.out.append(f"<{tag}>")

    def handle_data(self, data):
        if self._skip_depth:
            return
        self.out.append(_escape_text(data))

    def handle_comment(self, data):
        pass  # comments are never emitted -- closes off <!--<script>--> style bypass tricks

    def get_html(self) -> str:
        return "".join(self.out)


def _escape_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_attr(text: str) -> str:
    return _escape_text(text).replace('"', "&quot;")


def sanitize_html(raw_html: str) -> str:
    """The security boundary. Returns HTML safe to render with `| safe`."""
    if _nh3 is not None:
        return _nh3.clean(
            raw_html,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            url_schemes=ALLOWED_URL_SCHEMES,
            link_rel="noopener noreferrer",
        )
    parser = _AllowlistSanitizer()
    parser.feed(raw_html or "")
    parser.close()
    return parser.get_html()


def render_markdown_safe(raw_markdown: str) -> str:
    """Markdown -> sanitized HTML. This is the only function the rest of
    the app should call -- it guarantees the sanitization step always
    runs, so a caller can never accidentally render unsanitized HTML."""
    if not raw_markdown or not raw_markdown.strip():
        return ""
    raw_html = _markdown.markdown(
        raw_markdown,
        extensions=["fenced_code", "tables", "sane_lists"],
        output_format="html",
    )
    return sanitize_html(raw_html)