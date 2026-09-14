"""Offline tests for the HTTP plumbing in citationkeys.urlhandlers.

Unlike tests/test_urlhandlers.py, these never touch the network: they drive
get_url()/handle_url() with a fake opener, so they can assert *which* requests we
make and how we react to a site that rate-limits us.
"""

import urllib.error

import pytest

from citationkeys.urlhandlers import arxiv_handler, get_url, handle_url

HANDLERS = {"arxiv.org": arxiv_handler}


class FakeResponse:
    def __init__(self, body, content_type):
        self.body = body
        self.content_type = content_type

    def getheader(self, name):
        assert name == "Content-Type"
        return self.content_type

    def getcode(self):
        return 200

    def read(self):
        return self.body


class FakeOpener:
    """Records every request and replays a canned response (or error) per URL."""

    def __init__(self, responses=None, errors=None):
        self.responses = responses if responses is not None else {}
        self.errors = errors if errors is not None else {}
        self.requests = []

    def open(self, req):
        self.requests.append(req)
        url = req.full_url

        if url in self.errors and self.errors[url]:
            code = self.errors[url].pop(0)
            raise urllib.error.HTTPError(url, code, "Throttled", {}, None)

        if url.endswith(".bib") or "/bibtex/" in url:
            return FakeResponse(b"@misc{foo,}", "text/plain; charset=utf-8")
        return FakeResponse(b"%PDF-1.5 fake", "application/pdf")

    @property
    def urls(self):
        return [r.full_url for r in self.requests]


class TestArxivRequests:
    def test_pdf_url_has_no_dot_pdf_suffix(self):
        """arxiv.org 301-redirects /pdf/<id>.pdf to /pdf/<id>, so ask for the latter."""
        opener = FakeOpener()
        handle_url("https://arxiv.org/abs/2401.15041", HANDLERS, opener, "UA", 0, True, True)

        assert "https://arxiv.org/pdf/2401.15041" in opener.urls
        assert not any(u.endswith(".pdf") for u in opener.urls)

    @pytest.mark.parametrize("url", [
        "https://arxiv.org/abs/2401.15041",
        "https://arxiv.org/pdf/2401.15041",
        "https://arxiv.org/pdf/2401.15041.pdf",
    ])
    def test_landing_page_is_not_fetched(self, url):
        """The handler derives both URLs from the paper ID, so fetching the page the
           user gave us is wasted traffic. (For a /pdf/ URL it used to download the
           whole PDF twice, which is a great way to get rate-limited by arxiv.org.)"""
        opener = FakeOpener()
        handle_url(url, HANDLERS, opener, "UA", 0, True, True)

        assert opener.urls == [
            "https://arxiv.org/bibtex/2401.15041",
            "https://arxiv.org/pdf/2401.15041",
        ]


class TestThrottleRetries:
    def test_retries_on_406_then_succeeds(self, monkeypatch):
        """arxiv.org answers a burst of requests with a bare HTTP 406 for a little
           while; backing off and retrying should get us the file."""
        slept = []
        monkeypatch.setattr("citationkeys.urlhandlers.time.sleep", slept.append)

        url = "https://arxiv.org/bibtex/2401.15041"
        opener = FakeOpener(errors={url: [406, 406]})

        assert get_url(opener, url, 0, "UA") == b"@misc{foo,}"
        assert len(opener.urls) == 3
        assert slept == [2, 5]

    def test_gives_up_after_the_last_retry(self, monkeypatch):
        monkeypatch.setattr("citationkeys.urlhandlers.time.sleep", lambda _: None)

        url = "https://arxiv.org/bibtex/2401.15041"
        opener = FakeOpener(errors={url: [406, 406, 406, 406]})

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            get_url(opener, url, 0, "UA")
        assert exc_info.value.code == 406

    def test_does_not_retry_other_http_errors(self, monkeypatch):
        """A 404 (or a Cloudflare 403) is permanent; retrying it just wastes the
           user's time, and some handlers rely on catching it promptly."""
        monkeypatch.setattr("citationkeys.urlhandlers.time.sleep", lambda _: None)

        url = "https://doi.org/10.5555/nonexistent"
        opener = FakeOpener(errors={url: [404]})

        with pytest.raises(urllib.error.HTTPError):
            get_url(opener, url, 0, "UA")
        assert len(opener.urls) == 1


class TestGetUrlHeaders:
    def test_extra_headers_do_not_leak_into_later_calls(self):
        """get_url() used to have a mutable {} default for extra_headers."""
        opener = FakeOpener()
        get_url(opener, "https://x.org/a.bib", 0, "UA", None, {"Accept": "application/x-bibtex"})
        get_url(opener, "https://x.org/b.bib", 0, "UA")

        assert opener.requests[0].get_header("Accept") == "application/x-bibtex"
        assert opener.requests[1].get_header("Accept") is None

    def test_callers_dict_is_not_mutated(self):
        opener = FakeOpener()
        extra = {"Accept": "application/x-bibtex"}
        get_url(opener, "https://x.org/a.bib", 0, "UA", None, extra)

        assert extra == {"Accept": "application/x-bibtex"}
