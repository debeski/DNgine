"""Pure-function clipboard content and text formatting transforms.

No Qt dependency so the module can be reused from commands, tests,
and the headless command runtime.
"""

from __future__ import annotations

import csv
import io
import json
import re
import textwrap
from dataclasses import dataclass
from html.parser import HTMLParser


@dataclass(frozen=True)
class TransformResult:
    text: str
    content_type: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._pieces: list[str] = []

    def handle_data(self, data: str) -> None:
        self._pieces.append(data)

    def get_text(self) -> str:
        return "".join(self._pieces)


_WORD_SPLIT_RE = re.compile(r"[\s_\-]+")
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_URL_RE = re.compile(
    r"https?://[^\s<>\"'\)\]]+",
    re.IGNORECASE,
)
_HREF_RE = re.compile(
    r'href\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def _split_words(text: str) -> list[str]:
    """Split text into word tokens by spaces, underscores, hyphens, and camelCase boundaries."""
    expanded = _CAMEL_BOUNDARY_RE.sub(" ", text)
    return [w for w in _WORD_SPLIT_RE.split(expanded) if w]


# ---------------------------------------------------------------------------
# Content transforms
# ---------------------------------------------------------------------------

def to_plain_text(content: str, html: str = "") -> TransformResult:
    """Strip HTML tags and return plain text."""
    source = html.strip() if html and html.strip() else content
    if not source:
        return TransformResult(text="", content_type="text")
    extractor = _HTMLTextExtractor()
    try:
        extractor.feed(source)
        plain = extractor.get_text()
    except Exception:
        plain = content
    return TransformResult(text=plain.strip(), content_type="text")


def to_json_csv(content: str) -> TransformResult:
    """Convert JSON arrays/objects to CSV, or tabular CSV lines to JSON."""
    stripped = content.strip()
    if not stripped:
        return TransformResult(text="", content_type="text")

    # Try JSON → CSV
    try:
        data = json.loads(stripped)
        if isinstance(data, list) and data and isinstance(data[0], dict):
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=list(data[0].keys()))
            writer.writeheader()
            for row in data:
                writer.writerow(row)
            return TransformResult(text=output.getvalue().strip(), content_type="table")
        if isinstance(data, dict):
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=list(data.keys()))
            writer.writeheader()
            writer.writerow(data)
            return TransformResult(text=output.getvalue().strip(), content_type="table")
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Try CSV → JSON
    try:
        reader = csv.DictReader(io.StringIO(stripped))
        rows = list(reader)
        if rows and reader.fieldnames:
            result = json.dumps(rows, indent=2, ensure_ascii=False)
            return TransformResult(text=result, content_type="code")
    except Exception:
        pass

    return TransformResult(text=stripped, content_type="text")


def extract_links(content: str, html: str = "") -> TransformResult:
    """Extract URLs from plain text and HTML href attributes."""
    urls: list[str] = []
    seen: set[str] = set()

    for source in (content, html):
        if not source:
            continue
        for match in _URL_RE.finditer(source):
            url = match.group(0).rstrip(".,;:!?)")
            if url not in seen:
                seen.add(url)
                urls.append(url)
        for match in _HREF_RE.finditer(source):
            url = match.group(1).strip()
            if url not in seen:
                seen.add(url)
                urls.append(url)

    text = "\n".join(urls) if urls else ""
    return TransformResult(text=text, content_type="url" if urls else "text")


def clipboard_to_image_paths(image_path: str) -> list[str]:
    """Return a list containing the image path if it is non-empty."""
    if image_path and image_path.strip():
        return [image_path.strip()]
    return []


# ---------------------------------------------------------------------------
# Text formatting transforms
# ---------------------------------------------------------------------------

def to_upper(text: str) -> TransformResult:
    return TransformResult(text=text.upper(), content_type="text")


def to_lower(text: str) -> TransformResult:
    return TransformResult(text=text.lower(), content_type="text")


def to_capitalize(text: str) -> TransformResult:
    """Capitalize the first letter of each sentence."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    result = " ".join(s[:1].upper() + s[1:] if s else s for s in sentences)
    return TransformResult(text=result, content_type="text")


def to_title_case(text: str) -> TransformResult:
    return TransformResult(text=text.title(), content_type="text")


def to_pascal_case(text: str) -> TransformResult:
    words = _split_words(text)
    result = "".join(w.capitalize() for w in words)
    return TransformResult(text=result, content_type="text")


def to_snake_case(text: str) -> TransformResult:
    words = _split_words(text)
    result = "_".join(w.lower() for w in words)
    return TransformResult(text=result, content_type="text")


def to_camel_case(text: str) -> TransformResult:
    words = _split_words(text)
    if not words:
        return TransformResult(text="", content_type="text")
    result = words[0].lower() + "".join(w.capitalize() for w in words[1:])
    return TransformResult(text=result, content_type="text")


def to_kebab_case(text: str) -> TransformResult:
    words = _split_words(text)
    result = "-".join(w.lower() for w in words)
    return TransformResult(text=result, content_type="text")


def trim_whitespace(text: str) -> TransformResult:
    """Strip leading/trailing whitespace from each line."""
    lines = text.splitlines()
    result = "\n".join(line.strip() for line in lines)
    return TransformResult(text=result, content_type="text")


def remove_indent(text: str) -> TransformResult:
    """Remove common leading indentation."""
    result = textwrap.dedent(text)
    return TransformResult(text=result, content_type="text")


def collapse_blank_lines(text: str) -> TransformResult:
    """Collapse consecutive blank lines into a single blank line."""
    result = re.sub(r"\n{3,}", "\n\n", text)
    return TransformResult(text=result.strip(), content_type="text")


def reverse_lines(text: str) -> TransformResult:
    """Reverse the order of lines."""
    lines = text.splitlines()
    lines.reverse()
    return TransformResult(text="\n".join(lines), content_type="text")


# ---------------------------------------------------------------------------
# Registry for UI consumption
# ---------------------------------------------------------------------------

CONTENT_TRANSFORMS: list[tuple[str, str, str]] = [
    ("plain_text", "transform.plain_text", "Plain Text"),
    ("json_csv", "transform.json_csv", "JSON ↔ CSV"),
    ("extract_links", "transform.extract_links", "Extract Links"),
]

TEXT_FORMATTING_TRANSFORMS: list[tuple[str, str, str]] = [
    ("upper", "transform.upper", "UPPERCASE"),
    ("lower", "transform.lower", "lowercase"),
    ("capitalize", "transform.capitalize", "Capitalize"),
    ("title_case", "transform.title_case", "Title Case"),
    ("pascal_case", "transform.pascal_case", "PascalCase"),
    ("snake_case", "transform.snake_case", "snake_case"),
    ("camel_case", "transform.camel_case", "camelCase"),
    ("kebab_case", "transform.kebab_case", "kebab-case"),
    ("trim", "transform.trim", "Trim Whitespace"),
    ("remove_indent", "transform.remove_indent", "Remove Indent"),
    ("collapse_blank", "transform.collapse_blank", "Collapse Blank Lines"),
    ("reverse_lines", "transform.reverse_lines", "Reverse Lines"),
]


def apply_transform(transform_id: str, content: str, html: str = "") -> TransformResult:
    """Apply a transform by its registry ID. Returns unchanged text on unknown ID."""
    dispatch = {
        "plain_text": lambda: to_plain_text(content, html),
        "json_csv": lambda: to_json_csv(content),
        "extract_links": lambda: extract_links(content, html),
        "upper": lambda: to_upper(content),
        "lower": lambda: to_lower(content),
        "capitalize": lambda: to_capitalize(content),
        "title_case": lambda: to_title_case(content),
        "pascal_case": lambda: to_pascal_case(content),
        "snake_case": lambda: to_snake_case(content),
        "camel_case": lambda: to_camel_case(content),
        "kebab_case": lambda: to_kebab_case(content),
        "trim": lambda: trim_whitespace(content),
        "remove_indent": lambda: remove_indent(content),
        "collapse_blank": lambda: collapse_blank_lines(content),
        "reverse_lines": lambda: reverse_lines(content),
    }
    fn = dispatch.get(transform_id)
    if fn is None:
        return TransformResult(text=content, content_type="text")
    return fn()
