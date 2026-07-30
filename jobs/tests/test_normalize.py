from jobs.normalize import (
    collapse_whitespace,
    detect_remote,
    fingerprint,
    normalize_company,
    normalize_title,
    strip_html,
)


class TestStripHtml:
    def test_paragraphs_are_separated_by_a_blank_line(self):
        html = "<p>First line</p><p>Second line</p>"
        assert strip_html(html) == "First line\n\nSecond line"

    def test_list_items_are_bulleted_on_single_lines(self):
        html = "<ul><li>Python</li><li>Django</li></ul>"
        assert strip_html(html) == "- Python\n- Django"

    def test_br_breaks_a_line_without_a_blank_line(self):
        assert strip_html("Line one<br>Line two") == "Line one\nLine two"

    def test_entities_are_decoded(self):
        assert strip_html("<p>R&amp;D at Acme&nbsp;Ltd</p>") == "R&D at Acme Ltd"

    def test_script_and_style_content_is_dropped(self):
        html = "<div>Real text<script>alert('x')</script><style>.a{color:red}</style></div>"
        assert strip_html(html) == "Real text"

    def test_unclosed_tags_do_not_raise(self):
        assert "Senior Engineer" in strip_html("<div><p>Senior Engineer<div><b>Remote")

    def test_empty_and_none(self):
        assert strip_html("") == ""
        assert strip_html(None) == ""

    def test_plain_text_survives_unchanged(self):
        assert strip_html("No markup here") == "No markup here"


class TestNormalizeCompany:
    def test_legal_suffixes_are_dropped(self):
        assert normalize_company("Acme, Inc.") == "acme"
        assert normalize_company("Acme Limited") == "acme"
        assert normalize_company("ACME GmbH") == "acme"

    def test_multiple_trailing_suffixes(self):
        assert normalize_company("Acme Holdings Co. Ltd") == "acme holdings"

    def test_ampersand_is_spelled_out(self):
        assert normalize_company("Smith & Jones") == "smith and jones"

    def test_bracketed_notes_removed(self):
        assert normalize_company("Acme (EMEA)") == "acme"

    def test_blank(self):
        assert normalize_company("") == ""
        assert normalize_company(None) == ""


class TestNormalizeTitle:
    def test_gender_markers_removed(self):
        assert normalize_title("Backend Engineer (m/f/d)") == "backend engineer"

    def test_trailing_location_removed(self):
        assert normalize_title("Backend Engineer - Berlin") == "backend engineer"

    def test_bracketed_extras_removed(self):
        assert normalize_title("Backend Engineer (Remote)") == "backend engineer"

    def test_case_and_spacing(self):
        assert normalize_title("  Senior   Python   Engineer ") == "senior python engineer"

    def test_dot_and_plus_kept_for_tech_names(self):
        assert normalize_title("Node.js Developer") == "node.js developer"
        assert normalize_title("C++ Developer") == "c++ developer"


class TestDetectRemote:
    def test_remote_words(self):
        assert detect_remote("Remote - Worldwide") is True
        assert detect_remote("", "Work from home role") is True

    def test_hybrid_counts_as_not_remote(self):
        assert detect_remote("Hybrid - Berlin") is False

    def test_onsite(self):
        assert detect_remote("On-site, Munich") is False

    def test_unknown_when_nothing_said(self):
        assert detect_remote("Berlin") is None
        assert detect_remote("") is None
        assert detect_remote(None) is None


class TestFingerprint:
    def test_same_role_written_differently_matches(self):
        assert fingerprint("Acme Inc.", "Backend Engineer (m/f/d)") == fingerprint(
            "ACME", "Backend Engineer"
        )

    def test_different_roles_differ(self):
        assert fingerprint("Acme", "Backend Engineer") != fingerprint("Acme", "Frontend Engineer")


def test_collapse_whitespace_normalises_line_endings():
    assert collapse_whitespace("a\r\n\r\n\r\n\r\nb") == "a\n\nb"
