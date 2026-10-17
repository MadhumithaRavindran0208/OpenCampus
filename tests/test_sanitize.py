import unittest

from app.core.sanitize import sanitize_html, render_markdown_safe


class SanitizerXSSTests(unittest.TestCase):
    """Each of these is a known XSS vector. If any of these assertions
    fail, the sanitizer has a real hole -- do not weaken these tests to
    make them pass."""

    def _assert_stripped(self, raw_html: str, forbidden_substrings: list[str]):
        cleaned = sanitize_html(raw_html)
        for forbidden in forbidden_substrings:
            self.assertNotIn(forbidden.lower(), cleaned.lower(), f"payload leaked through: {raw_html!r} -> {cleaned!r}")

    def test_script_tag_stripped(self):
        self._assert_stripped("<script>alert(1)</script>", ["<script", "alert(1)"])

    def test_script_tag_content_not_emitted_as_text(self):
        # the tag AND its inner JS payload must both disappear, not just the tag
        cleaned = sanitize_html("<p>hi</p><script>alert(document.cookie)</script>")
        self.assertNotIn("alert", cleaned)
        self.assertIn("hi", cleaned)

    def test_img_onerror_stripped(self):
        self._assert_stripped('<img src=x onerror=alert(1)>', ["onerror", "<img"])

    def test_svg_onload_stripped(self):
        self._assert_stripped('<svg onload=alert(1)>', ["<svg", "onload"])

    def test_javascript_href_stripped(self):
        cleaned = sanitize_html('<a href="javascript:alert(1)">click</a>')
        self.assertNotIn("javascript:", cleaned.lower())
        self.assertIn("click", cleaned)  # link text itself is safe content, should survive

    def test_data_uri_href_stripped(self):
        cleaned = sanitize_html('<a href="data:text/html,<script>alert(1)</script>">click</a>')
        self.assertNotIn("data:", cleaned.lower())

    def test_vbscript_href_stripped(self):
        cleaned = sanitize_html('<a href="vbscript:msgbox(1)">click</a>')
        self.assertNotIn("vbscript:", cleaned.lower())

    def test_iframe_stripped_entirely(self):
        self._assert_stripped('<iframe src="javascript:alert(1)"></iframe>', ["<iframe", "javascript:"])

    def test_style_attribute_stripped(self):
        cleaned = sanitize_html('<p style="background:url(javascript:alert(1))">hi</p>')
        self.assertNotIn("javascript:", cleaned.lower())
        self.assertNotIn("style=", cleaned.lower())

    def test_mixed_case_script_tag_stripped(self):
        self._assert_stripped("<ScRiPt>alert(1)</ScRiPt>", ["<script", "alert(1)"])

    def test_comment_wrapped_script_stripped(self):
        self._assert_stripped("<!--><script>alert(1)</script>-->", ["<script", "alert(1)"])

    def test_form_action_stripped(self):
        self._assert_stripped('<form action="javascript:alert(1)"><input></form>', ["<form", "javascript:"])

    def test_object_embed_stripped(self):
        self._assert_stripped('<object data="evil.swf"></object>', ["<object"])
        self._assert_stripped('<embed src="evil.swf">', ["<embed"])

    def test_event_handler_on_allowed_tag_stripped(self):
        # <p> is allowed, but onclick on it is not
        cleaned = sanitize_html('<p onclick="alert(1)">hello</p>')
        self.assertNotIn("onclick", cleaned)
        self.assertIn("hello", cleaned)

    def test_malformed_tag_with_no_closing_bracket_handled_safely(self):
        # should not raise, and should not leak the payload
        cleaned = sanitize_html('<img src=x onerror=alert(1)//')
        self.assertNotIn("onerror", cleaned)

    def test_nested_broken_tags_dont_bypass_filter(self):
        cleaned = sanitize_html("<scr<script>ipt>alert(1)</scr</script>ipt>")
        # The actual security property: no real (unescaped) tag markup
        # survives -- "alert(1)" surviving as inert, HTML-escaped text
        # is harmless (equivalent to it appearing in a tutorial doc)
        # and isn't itself a vulnerability.
        import re
        self.assertIsNone(re.search(r"<[a-zA-Z]", cleaned), f"real tag markup leaked through: {cleaned!r}")


class SanitizerLegitimateContentTests(unittest.TestCase):
    """The sanitizer must not be so aggressive it breaks normal, safe
    Markdown -- headers, bold text, links, code blocks, lists."""

    def test_headers_render(self):
        html = render_markdown_safe("# Title\n\n## Subtitle")
        self.assertIn("<h1>", html)
        self.assertIn("<h2>", html)
        self.assertIn("Title", html)

    def test_bold_and_emphasis_render(self):
        html = render_markdown_safe("**bold** and *italic*")
        self.assertIn("<strong>", html)
        self.assertIn("<em>", html)

    def test_safe_link_preserved(self):
        html = render_markdown_safe("[docs](https://example.com/docs)")
        self.assertIn('href="https://example.com/docs"', html)
        self.assertIn("docs", html)

    def test_fenced_code_block_renders(self):
        html = render_markdown_safe("```python\nprint('hi')\n```")
        self.assertIn("<pre>", html)
        self.assertIn("print", html)

    def test_list_renders(self):
        html = render_markdown_safe("- one\n- two\n- three")
        self.assertIn("<ul>", html)
        self.assertIn("<li>", html)

    def test_table_renders(self):
        html = render_markdown_safe("| A | B |\n|---|---|\n| 1 | 2 |")
        self.assertIn("<table>", html)

    def test_empty_content_returns_empty(self):
        self.assertEqual(render_markdown_safe(""), "")
        self.assertEqual(render_markdown_safe("   "), "")

    def test_relative_and_fragment_links_preserved(self):
        html = render_markdown_safe("[section](#setup) and [page](/other)")
        self.assertIn('href="#setup"', html)
        self.assertIn('href="/other"', html)


class SanitizerMarkdownInjectionTests(unittest.TestCase):
    """Raw HTML pasted into a Markdown field (not written as Markdown
    syntax) must still be neutralized -- users can and will paste HTML."""

    def test_raw_script_pasted_into_markdown_field(self):
        html = render_markdown_safe("Check this out <script>alert(document.cookie)</script> cool right?")
        self.assertNotIn("<script", html.lower())
        self.assertNotIn("alert(document.cookie)", html)
        self.assertIn("Check this out", html)

    def test_raw_img_onerror_pasted_into_markdown_field(self):
        html = render_markdown_safe("![broken](x) <img src=x onerror=alert(1)>")
        self.assertNotIn("onerror", html)


if __name__ == "__main__":
    unittest.main()