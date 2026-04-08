"""Integration tests for URL handlers.

These tests hit real websites and will fail when sites change their structure.
That's the point — they detect when handlers break.

Run with: pytest tests/test_urlhandlers.py -v
Skip with: pytest -m "not integration"
"""

import http.cookiejar
import urllib.request

import pytest
from fake_useragent import UserAgent

from citationkeys.urlhandlers import (
    handle_url,
    arxiv_handler,
    dlacm_handler,
    epubssiam_handler,
    iacreprint_handler,
    ieeexplore_handler,
    springerlink_handler,
)

# All URL handler tests are integration tests (they hit the network)
pytestmark = pytest.mark.integration


HANDLERS = {
    "link.springer.com": springerlink_handler,
    "arxiv.org": arxiv_handler,
    "rd.springer.com": springerlink_handler,
    "eprint.iacr.org": iacreprint_handler,
    "dl.acm.org": dlacm_handler,
    "epubs.siam.org": epubssiam_handler,
    "ieeexplore.ieee.org": ieeexplore_handler,
}


@pytest.fixture(scope="module")
def opener():
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


@pytest.fixture(scope="module")
def user_agent():
    return UserAgent().random


class TestArxiv:
    def test_download_bib(self, opener, user_agent):
        is_handled, bib_data, pdf_data = handle_url(
            "https://arxiv.org/abs/1906.07221",
            HANDLERS, opener, user_agent, 0,
            bib_downl=True, pdf_downl=False,
        )
        assert is_handled is True
        assert bib_data is not None
        bib_str = bib_data.decode("utf-8")
        assert "@" in bib_str  # valid bibtex

    def test_download_pdf(self, opener, user_agent):
        is_handled, bib_data, pdf_data = handle_url(
            "https://arxiv.org/abs/1906.07221",
            HANDLERS, opener, user_agent, 0,
            bib_downl=False, pdf_downl=True,
        )
        assert is_handled is True
        assert pdf_data is not None
        assert pdf_data[:5] == b"%PDF-"

    def test_abs_url_format(self, opener, user_agent):
        """Both /abs/ URL format should work."""
        is_handled, bib_data, _ = handle_url(
            "https://arxiv.org/abs/2103.01587",
            HANDLERS, opener, user_agent, 0,
            bib_downl=True, pdf_downl=False,
        )
        assert is_handled is True
        assert bib_data is not None


class TestIACR:
    def test_download_bib(self, opener, user_agent):
        is_handled, bib_data, pdf_data = handle_url(
            "https://eprint.iacr.org/2018/721",
            HANDLERS, opener, user_agent, 0,
            bib_downl=True, pdf_downl=False,
        )
        assert is_handled is True
        assert bib_data is not None
        assert b"@" in bib_data

    def test_download_pdf(self, opener, user_agent):
        is_handled, _, pdf_data = handle_url(
            "https://eprint.iacr.org/2018/721",
            HANDLERS, opener, user_agent, 0,
            bib_downl=False, pdf_downl=True,
        )
        assert is_handled is True
        assert pdf_data is not None
        assert pdf_data[:5] == b"%PDF-"

    def test_pdf_url_stripped(self, opener, user_agent):
        """URLs ending in .pdf should be handled by stripping the suffix."""
        is_handled, bib_data, _ = handle_url(
            "https://eprint.iacr.org/2018/721.pdf",
            HANDLERS, opener, user_agent, 0,
            bib_downl=True, pdf_downl=False,
        )
        assert is_handled is True
        assert bib_data is not None


class TestACM:
    def test_download_bib(self, opener, user_agent):
        is_handled, bib_data, _ = handle_url(
            "https://dl.acm.org/doi/10.1145/62212.62225",
            HANDLERS, opener, user_agent, 0,
            bib_downl=True, pdf_downl=False,
        )
        assert is_handled is True
        assert bib_data is not None
        bib_str = bib_data.decode("utf-8")
        assert "@" in bib_str


class TestSpringerLink:
    def test_download_bib(self, opener, user_agent):
        is_handled, bib_data, _ = handle_url(
            "https://link.springer.com/chapter/10.1007/11818175_27",
            HANDLERS, opener, user_agent, 0,
            bib_downl=True, pdf_downl=False,
        )
        assert is_handled is True
        assert bib_data is not None

    def test_download_pdf(self, opener, user_agent):
        is_handled, _, pdf_data = handle_url(
            "https://link.springer.com/chapter/10.1007/11818175_27",
            HANDLERS, opener, user_agent, 0,
            bib_downl=False, pdf_downl=True,
        )
        assert is_handled is True
        assert pdf_data is not None
        assert pdf_data[:5] == b"%PDF-"


class TestSIAM:
    @pytest.mark.xfail(reason="SIAM blocks automated requests with 403")
    def test_download_bib(self, opener, user_agent):
        is_handled, bib_data, _ = handle_url(
            "https://epubs.siam.org/doi/10.1137/S0097539790187084",
            HANDLERS, opener, user_agent, 0,
            bib_downl=True, pdf_downl=False,
        )
        assert is_handled is True
        assert bib_data is not None


class TestIEEE:
    @pytest.mark.xfail(reason="IEEE uses bot detection that blocks urllib")
    def test_download_bib(self, opener, user_agent):
        is_handled, bib_data, _ = handle_url(
            "https://ieeexplore.ieee.org/document/7958589",
            HANDLERS, opener, user_agent, 0,
            bib_downl=True, pdf_downl=False,
        )
        assert is_handled is True
        assert bib_data is not None
        # IEEE serves bibtex with <br> tags that get cleaned
        bib_str = bib_data.replace(b"<br>", b"").decode("utf-8")
        assert "@" in bib_str


class TestUnhandledUrl:
    def test_unknown_domain(self, opener, user_agent):
        is_handled, bib_data, pdf_data = handle_url(
            "https://example.com/paper.pdf",
            HANDLERS, opener, user_agent, 0,
            bib_downl=True, pdf_downl=True,
        )
        assert is_handled is False
        assert bib_data is None
        assert pdf_data is None
