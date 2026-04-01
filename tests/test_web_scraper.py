from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dngine.core.commands import CommandRegistry
from dngine.core.plugin_manager import _parse_plugin_specs
from first_party_packages.web_dev.plugins.web_scraper import WebScraperPlugin, scrape_web_pages


PAGE_ONE = """
<html>
  <body>
    <article class="entry">
      <h2 class="title">Alpha</h2>
      <a class="more" href="/items/alpha">Read Alpha</a>
      <p class="summary">Alpha summary</p>
    </article>
    <article class="entry">
      <h2 class="title">Beta</h2>
      <a class="more" href="https://example.com/beta">Read Beta</a>
      <p class="summary">Beta summary</p>
    </article>
    <a class="next" href="/page2.html">Next</a>
  </body>
</html>
"""

PAGE_TWO = """
<html>
  <body>
    <article class="entry">
      <h2 class="title">Gamma</h2>
      <a class="more" href="/items/gamma">Read Gamma</a>
      <p class="summary">Gamma summary</p>
    </article>
  </body>
</html>
"""

EMPTY_PAGE = """
<html>
  <body>
    <p>No matching entries here.</p>
  </body>
</html>
"""

LOOP_PAGE = """
<html>
  <body>
    <article class="entry">
      <h2 class="title">Loop</h2>
      <a class="more" href="/items/loop">Loop Item</a>
      <p class="summary">Loop summary</p>
    </article>
    <a class="next" href="/loop.html">Next</a>
  </body>
</html>
"""

MALFORMED_PAGE = """
<html>
  <body>
    <div class="entry">
      <h2 class="title">Broken
      <a class="more" href="/items/broken">Open</a>
      <p class="summary">Malformed summary
    </div>
  </body>
</html>
"""


class _FakeContext:
    def __init__(self):
        self.logs: list[tuple[str, str]] = []
        self.progress_updates: list[float] = []

    def log(self, message: str, level: str = "INFO") -> None:
        self.logs.append((level, str(message)))

    def progress(self, value: float) -> None:
        self.progress_updates.append(float(value))


class _DummyServices:
    def __init__(self, output_dir: Path):
        self._output_dir = Path(output_dir)
        self.logged: list[tuple[str, str]] = []
        self.runs: list[tuple[str, str, str]] = []

    def log(self, message: str, level: str = "INFO") -> None:
        self.logged.append((level, str(message)))

    def record_run(self, plugin_id: str, status: str, details: str = "") -> None:
        self.runs.append((plugin_id, status, details))

    def default_output_path(self) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        return self._output_dir


SCRAPER_DEPS_AVAILABLE = all(
    importlib.util.find_spec(module_name) is not None
    for module_name in ("requests", "bs4")
)

if SCRAPER_DEPS_AVAILABLE:
    import requests
else:  # pragma: no cover - exercised only when optional deps are missing
    requests = None


class _FakeResponse:
    def __init__(self, url: str, status_code: int, text: str):
        self.url = url
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            error = requests.exceptions.HTTPError(f"HTTP {self.status_code} for {self.url}")
            error.response = self
            raise error


class _FakeSession:
    def __init__(self, routes: dict[str, tuple[int, str, float]]):
        self.routes = routes
        self.headers: dict[str, str] = {}

    def get(self, url: str, timeout: float):
        status, body, delay = self.routes.get(url, (404, "Not Found", 0.0))
        if delay > float(timeout):
            raise requests.exceptions.Timeout(f"Timed out after {timeout} seconds")
        response = _FakeResponse(url, status, body)
        return response


def _requests_session_patch(routes: dict[str, tuple[int, str, float]]):
    return patch("requests.Session", return_value=_FakeSession(routes))


@unittest.skipUnless(SCRAPER_DEPS_AVAILABLE, "Web Scraper tests require optional requests and beautifulsoup4 dependencies.")
class WebScraperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base_url = "https://fixture.test"
        self.routes = {
            f"{self.base_url}/page1.html": (200, PAGE_ONE, 0.0),
            f"{self.base_url}/page2.html": (200, PAGE_TWO, 0.0),
            f"{self.base_url}/empty.html": (200, EMPTY_PAGE, 0.0),
            f"{self.base_url}/loop.html": (200, LOOP_PAGE, 0.0),
            f"{self.base_url}/malformed.html": (200, MALFORMED_PAGE, 0.0),
            f"{self.base_url}/slow.html": (200, PAGE_ONE, 0.35),
            f"{self.base_url}/status500.html": (500, "Server Error", 0.0),
        }

    def test_single_page_scrape_extracts_rows(self) -> None:
        context = _FakeContext()
        with _requests_session_patch(self.routes):
            payload = scrape_web_pages(
                context,
                url=f"{self.base_url}/page1.html",
                item_selector="article.entry",
                title_selector=".title",
                link_selector="a.more",
                text_selector=".summary",
                max_pages=1,
            )
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["pages_visited"], 1)
        self.assertEqual(payload["rows"][0]["title"], "Alpha")
        self.assertEqual(payload["rows"][0]["link"], f"{self.base_url}/items/alpha")

    def test_pagination_collects_multiple_pages(self) -> None:
        context = _FakeContext()
        with _requests_session_patch(self.routes):
            payload = scrape_web_pages(
                context,
                url=f"{self.base_url}/page1.html",
                item_selector="article.entry",
                title_selector=".title",
                link_selector="a.more",
                text_selector=".summary",
                next_selector="a.next",
                max_pages=2,
            )
        self.assertEqual(payload["count"], 3)
        self.assertEqual(payload["pages_visited"], 2)
        self.assertEqual(payload["stop_reason"], "no_next_link")

    def test_repeated_pagination_url_stops_loop(self) -> None:
        context = _FakeContext()
        with _requests_session_patch(self.routes):
            payload = scrape_web_pages(
                context,
                url=f"{self.base_url}/loop.html",
                item_selector="article.entry",
                title_selector=".title",
                link_selector="a.more",
                text_selector=".summary",
                next_selector="a.next",
                max_pages=5,
            )
        self.assertEqual(payload["pages_visited"], 1)
        self.assertEqual(payload["stop_reason"], "repeated_url")

    def test_missing_next_selector_stops_after_first_page(self) -> None:
        context = _FakeContext()
        with _requests_session_patch(self.routes):
            payload = scrape_web_pages(
                context,
                url=f"{self.base_url}/page1.html",
                item_selector="article.entry",
                title_selector=".title",
                link_selector="a.more",
                text_selector=".summary",
                next_selector=".missing-next",
                max_pages=4,
            )
        self.assertEqual(payload["pages_visited"], 1)
        self.assertEqual(payload["stop_reason"], "no_next_link")

    def test_empty_results_are_allowed(self) -> None:
        context = _FakeContext()
        with _requests_session_patch(self.routes):
            payload = scrape_web_pages(
                context,
                url=f"{self.base_url}/empty.html",
                item_selector="article.entry",
                max_pages=1,
            )
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["pages_visited"], 1)

    def test_malformed_html_is_still_parsed(self) -> None:
        context = _FakeContext()
        with _requests_session_patch(self.routes):
            payload = scrape_web_pages(
                context,
                url=f"{self.base_url}/malformed.html",
                item_selector=".entry",
                title_selector=".title",
                link_selector="a.more",
                text_selector=".summary",
                max_pages=1,
            )
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["rows"][0]["link"], f"{self.base_url}/items/broken")

    def test_invalid_url_raises_value_error(self) -> None:
        context = _FakeContext()
        with self.assertRaises(ValueError):
            scrape_web_pages(context, url="not a valid url", item_selector=".entry")

    def test_timeout_raises_value_error(self) -> None:
        context = _FakeContext()
        with _requests_session_patch(self.routes):
            with self.assertRaises(ValueError):
                scrape_web_pages(
                    context,
                    url=f"{self.base_url}/slow.html",
                    item_selector="article.entry",
                    timeout_seconds=0.1,
                )

    def test_http_error_raises_value_error(self) -> None:
        context = _FakeContext()
        with _requests_session_patch(self.routes):
            with self.assertRaises(ValueError):
                scrape_web_pages(
                    context,
                    url=f"{self.base_url}/status500.html",
                    item_selector="article.entry",
                )

    def test_headless_command_exports_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            services = _DummyServices(Path(temp_dir))
            registry = CommandRegistry()
            WebScraperPlugin().register_commands(registry, services)
            with _requests_session_patch(self.routes):
                result = registry.execute(
                    "tool.web_scraper.run",
                    url=f"{self.base_url}/page1.html",
                    item_selector="article.entry",
                    title_selector=".title",
                    link_selector="a.more",
                    text_selector=".summary",
                    max_pages=1,
                    output_format="json",
                    output_dir=temp_dir,
                )
            output_path = Path(result["output_path"])
            self.assertTrue(output_path.exists())
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(len(payload), 2)
            self.assertEqual(payload[0]["title"], "Alpha")

    def test_plugin_spec_is_discoverable(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        plugins_root = project_root / "first_party_packages" / "web_dev" / "plugins"
        plugin_file = plugins_root / "web_scraper.py"
        specs = _parse_plugin_specs(plugin_file, plugins_root, source_type="imported")
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].plugin_id, "web_scraper")
        self.assertEqual(specs[0].localized_category("en"), "Web Dev")


if __name__ == "__main__":
    unittest.main()
