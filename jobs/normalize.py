"""Turn whatever a job board sends into comparable, markup-free values.

Every source hands back a differently shaped description: Remotive sends HTML,
Greenhouse sends escaped HTML, some send plain text with Windows line endings.
Normalising once here means dedup, scoring and the UI only ever see clean text.
"""

import hashlib
import re
from html.parser import HTMLParser

# Paragraph-like tags get a blank line around them; list items and line breaks
# get a single newline, so bullet lists do not come out double spaced.
BLOCK_TAGS = {
    "p", "div", "ul", "ol", "table", "section", "article",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre",
}
LINE_TAGS = {"br", "li", "tr"}
DROP_TAGS = {"script", "style", "head", "noscript"}

LEGAL_SUFFIXES = {
    "inc", "inc.", "llc", "l.l.c", "ltd", "ltd.", "limited", "gmbh", "ag", "bv", "b.v",
    "nv", "n.v", "plc", "co", "co.", "corp", "corp.", "corporation", "company",
    "sa", "s.a", "srl", "s.r.l", "oy", "ab", "as", "aps", "pte", "pty", "kk", "sas",
}

REMOTE_HINTS = (
    "remote",
    "work from home",
    "wfh",
    "anywhere",
    "distributed",
    "telecommute",
)
ONSITE_HINTS = ("on-site", "onsite", "in office", "in-office")
HYBRID_HINTS = ("hybrid",)

# "(m/w/d)", "(f/m/x)" and friends are German/EU gender markers in the title.
GENDER_MARKER_RE = re.compile(r"\(?\b[mfdwxa](?:\s*[/|]\s*[mfdwxa]){1,3}\b\)?", re.IGNORECASE)
BRACKETS_RE = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")
NON_ALNUM_RE = re.compile(r"[^a-z0-9+#. ]+")
MULTISPACE_RE = re.compile(r"\s+")


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in DROP_TAGS:
            self._skip_depth += 1
        elif tag in BLOCK_TAGS or tag in LINE_TAGS:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag):
        if tag in DROP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)

    def text(self):
        return "".join(self.parts)


def strip_html(value):
    """Plain text from an HTML fragment. Unclosed tags and stray < are tolerated."""
    if not value:
        return ""
    parser = _TextExtractor()
    # HTMLParser never raises on malformed markup, it just produces odd tokens,
    # which is exactly the behaviour we want for third-party job descriptions.
    parser.feed(value)
    parser.close()
    return collapse_whitespace(parser.text())


def collapse_whitespace(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_company(name):
    """Fold "Acme, Inc." and "ACME Limited" onto the same key."""
    if not name:
        return ""
    lowered = name.casefold().replace("&", " and ")
    lowered = BRACKETS_RE.sub(" ", lowered)
    lowered = NON_ALNUM_RE.sub(" ", lowered)
    words = [word for word in lowered.split() if word]
    while words and words[-1].strip(".") in LEGAL_SUFFIXES:
        words.pop()
    return " ".join(words)


def normalize_title(title):
    """Strip the decoration boards add so two postings of one role match."""
    if not title:
        return ""
    lowered = title.casefold()
    lowered = GENDER_MARKER_RE.sub(" ", lowered)
    lowered = BRACKETS_RE.sub(" ", lowered)
    # Everything after a dash is usually a location or department, not the role.
    lowered = re.split(r"\s+[-–—|]\s+", lowered)[0]
    lowered = NON_ALNUM_RE.sub(" ", lowered)
    return MULTISPACE_RE.sub(" ", lowered).strip()


def detect_remote(*values):
    """True, False, or None when the posting genuinely does not say."""
    haystack = " ".join(value for value in values if value).casefold()
    if not haystack:
        return None
    if any(hint in haystack for hint in HYBRID_HINTS):
        return False
    if any(hint in haystack for hint in REMOTE_HINTS):
        return True
    if any(hint in haystack for hint in ONSITE_HINTS):
        return False
    return None


def fingerprint(company, title):
    """Stable exact-match key. Fuzzy matching happens in dedup, not here."""
    basis = f"{normalize_company(company)}|{normalize_title(title)}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()
