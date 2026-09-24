"""Integration tests for URL handlers.

These tests hit real websites and will fail when sites change their structure.
That's the point — they detect when handlers break.

Run with: pytest tests/test_urlhandlers.py -v
Skip with: pytest -m "not integration"
"""

import http.cookiejar
import shutil
import urllib.parse
import urllib.request

import pytest
from fake_useragent import UserAgent

from citationkeys.urlhandlers import (
    handle_url,
    arxiv_handler,
    dlacm_handler,
    epubssiam_handler,
    github_handler,
    github_parse_file_url,
    iacreprint_handler,
    ieeexplore_handler,
    springerlink_handler,
    url_needs_manual_bib,
    usenix_handler,
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
    "www.usenix.org": usenix_handler,
    "github.com": github_handler,
}

BABYSNARK_URL = "https://github.com/initc3/babySNARK/blob/master/babysnark.pdf"

# A pre-2013 USENIX paper, whose URL points straight at the PDF (no landing page)
KLEE_LEGACY_URL = "https://www.usenix.org/legacy/event/osdi08/tech/full_papers/cadar/cadar.pdf"


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

    def test_pdf_url_format_no_extension(self, opener, user_agent):
        """/pdf/ URL format without a .pdf extension should work."""
        is_handled, bib_data, pdf_data = handle_url(
            "https://arxiv.org/pdf/2403.06634",
            HANDLERS, opener, user_agent, 0,
            bib_downl=True, pdf_downl=True,
        )
        assert is_handled is True
        assert bib_data is not None
        assert pdf_data is not None
        assert pdf_data[:5] == b"%PDF-"

    def test_pdf_url_format_with_extension(self, opener, user_agent):
        """/pdf/ URL format with a .pdf extension should work."""
        is_handled, bib_data, pdf_data = handle_url(
            "https://arxiv.org/pdf/2403.06634.pdf",
            HANDLERS, opener, user_agent, 0,
            bib_downl=True, pdf_downl=True,
        )
        assert is_handled is True
        assert bib_data is not None
        assert pdf_data is not None
        assert pdf_data[:5] == b"%PDF-"


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

    def test_download_postscript_only_paper_as_pdf(self, opener, user_agent):
        """Old papers are often only on the archive as PostScript; we convert them to a PDF."""
        # NOTE: Deliberately a failure, not a skip: 'ps2pdf' is a dependency (see install-deps.sh),
        # so if it is missing we want to hear about it rather than quietly lose the coverage.
        assert shutil.which("ps2pdf") is not None, \
            "Ghostscript's 'ps2pdf' is not installed; run ./install-deps.sh"

        is_handled, _, pdf_data = handle_url(
            "https://eprint.iacr.org/2002/047",
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

    def test_download_bib_unregistered_doi_skipped_exits_cleanly(self, opener, user_agent, monkeypatch):
        # 10.5555-prefixed "Guide Proceedings" DOIs (e.g. USENIX Security papers
        # listed on dl.acm.org) are frequently never registered with Crossref, so
        # doi.org 404s on the content-negotiation trick. This must not surface as
        # an uncaught HTTPError/traceback to the user; declining the USENIX-URL
        # fallback prompt should just exit(1) cleanly.
        monkeypatch.setattr("citationkeys.urlhandlers.click.prompt", lambda *a, **k: "")
        with pytest.raises(SystemExit) as exc_info:
            handle_url(
                "https://dl.acm.org/doi/10.5555/3698900.3698984",
                HANDLERS, opener, user_agent, 0,
                bib_downl=True, pdf_downl=False,
            )
        assert exc_info.value.code == 1

    def test_download_bib_unregistered_doi_falls_back_to_usenix(self, opener, user_agent, monkeypatch):
        # Same unregistered DOI as above, but this time supply the paper's USENIX
        # URL when prompted, and expect ck to scrape the official BibTeX from there.
        usenix_url = "https://www.usenix.org/conference/usenixsecurity24/presentation/bailey"
        monkeypatch.setattr("citationkeys.urlhandlers.click.prompt", lambda *a, **k: usenix_url)
        is_handled, bib_data, _ = handle_url(
            "https://dl.acm.org/doi/10.5555/3698900.3698984",
            HANDLERS, opener, user_agent, 0,
            bib_downl=True, pdf_downl=False,
        )
        assert is_handled is True
        assert bib_data is not None
        bib_str = bib_data.decode("utf-8")
        assert "@inproceedings" in bib_str
        assert "Bailey" in bib_str


class TestUSENIX:
    def test_download_bib(self, opener, user_agent):
        is_handled, bib_data, _ = handle_url(
            "https://www.usenix.org/conference/usenixsecurity24/presentation/bailey",
            HANDLERS, opener, user_agent, 0,
            bib_downl=True, pdf_downl=False,
        )
        assert is_handled is True
        assert bib_data is not None
        bib_str = bib_data.decode("utf-8")
        assert "@inproceedings" in bib_str
        assert "Bailey" in bib_str

    def test_download_pdf(self, opener, user_agent):
        is_handled, _, pdf_data = handle_url(
            "https://www.usenix.org/conference/usenixsecurity24/presentation/bailey",
            HANDLERS, opener, user_agent, 0,
            bib_downl=False, pdf_downl=True,
        )
        assert is_handled is True
        assert pdf_data is not None
        assert pdf_data[:5] == b"%PDF-"

    def test_legacy_download_pdf(self, opener, user_agent):
        # USENIX's legacy site links straight to the PDF: there is no landing page
        # to scrape, so the handler must download the URL as-is.
        is_handled, _, pdf_data = handle_url(
            KLEE_LEGACY_URL,
            HANDLERS, opener, user_agent, 0,
            bib_downl=False, pdf_downl=True,
        )
        assert is_handled is True
        assert pdf_data is not None
        assert pdf_data[:5] == b"%PDF-"

    def test_legacy_bib_is_prefilled_entry(self, opener, user_agent):
        # A legacy page has no BibTeX, so the handler hands back a pre-filled entry
        # for the user to complete, rather than erroring out.
        is_handled, bib_data, _ = handle_url(
            KLEE_LEGACY_URL,
            HANDLERS, opener, user_agent, 0,
            bib_downl=True, pdf_downl=False,
        )
        assert is_handled is True
        assert bib_data is not None
        bib_str = bib_data.decode("utf-8")
        assert "@misc{cadar," in bib_str  # citation key guessed from the file name
        assert KLEE_LEGACY_URL in bib_str

    def test_legacy_needs_manual_bib(self):
        assert url_needs_manual_bib(KLEE_LEGACY_URL) is True
        # ...but a modern USENIX paper page has BibTeX of its own
        assert url_needs_manual_bib(
            "https://www.usenix.org/conference/usenixsecurity24/presentation/bailey") is False


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


class TestGitHub:
    def test_download_pdf(self, opener, user_agent):
        """The 'blob' HTML viewer URL must be rewritten to the raw file URL."""
        is_handled, _, pdf_data = handle_url(
            BABYSNARK_URL,
            HANDLERS, opener, user_agent, 0,
            bib_downl=False, pdf_downl=True,
        )
        assert is_handled is True
        assert pdf_data is not None
        assert pdf_data[:5] == b"%PDF-"

    def test_prefilled_bib(self, opener, user_agent):
        """GitHub has no BibTeX, so we pre-fill a @misc entry with the URL and the
           year the PDF was last committed, for the user to complete."""
        is_handled, bib_data, _ = handle_url(
            BABYSNARK_URL,
            HANDLERS, opener, user_agent, 0,
            bib_downl=True, pdf_downl=False,
        )
        assert is_handled is True
        bib_str = bib_data.decode("utf-8")
        assert "@misc{babysnark," in bib_str  # citation key guessed from the file name
        assert BABYSNARK_URL in bib_str
        assert "year = {2020}" in bib_str

    def test_needs_manual_bib(self):
        assert url_needs_manual_bib(BABYSNARK_URL) is True
        assert url_needs_manual_bib("https://arxiv.org/abs/1906.07221") is False

    def test_parse_file_url(self):
        assert github_parse_file_url(urllib.parse.urlparse(BABYSNARK_URL)) == \
            ("initc3", "babySNARK", "master", "babysnark.pdf")
        # 'raw' URLs and nested file paths work too
        assert github_parse_file_url(urllib.parse.urlparse(
            "https://github.com/foo/bar/raw/main/docs/paper.pdf")) == \
            ("foo", "bar", "main", "docs/paper.pdf")
        # ...but a URL that does not point to a file in a repo does not
        assert github_parse_file_url(urllib.parse.urlparse(
            "https://github.com/initc3/babySNARK")) is None

    def test_non_file_url_exits_cleanly(self, opener, user_agent):
        with pytest.raises(SystemExit) as exc_info:
            handle_url(
                "https://github.com/initc3/babySNARK",
                HANDLERS, opener, user_agent, 0,
                bib_downl=True, pdf_downl=True,
            )
        assert exc_info.value.code == 1


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
