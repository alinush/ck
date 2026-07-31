"""Unit tests for citationkeys/misc.py"""

import os
import time

import pytest

from citationkeys.misc import (
    ck_to_pdf,
    ck_to_bib,
    ck_exists,
    list_cks,
    is_cwd_in_tagdir,
    cks_from_tags,
    wait_for_browser_pdf,
)


class TestCkToPdf:
    def test_basic(self):
        assert ck_to_pdf("/papers", "KZG10") == "/papers/KZG10.pdf"

    def test_empty_ck_raises(self):
        with pytest.raises(ValueError):
            ck_to_pdf("/papers", "")

    def test_none_ck_raises(self):
        with pytest.raises(ValueError):
            ck_to_pdf("/papers", None)


class TestCkToBib:
    def test_basic(self):
        assert ck_to_bib("/papers", "KZG10") == "/papers/KZG10.bib"

    def test_empty_ck_raises(self):
        with pytest.raises(ValueError):
            ck_to_bib("/papers", "")


class TestCkExists:
    def test_exists_with_pdf(self, ck_dirs):
        bib_dir, _ = ck_dirs
        with open(os.path.join(bib_dir, "X.pdf"), "wb") as f:
            f.write(b"%PDF")
        assert ck_exists(bib_dir, "X") is True

    def test_exists_with_bib(self, ck_dirs):
        bib_dir, _ = ck_dirs
        with open(os.path.join(bib_dir, "X.bib"), "w") as f:
            f.write("@article{X, author={A}, title={T}, year={2000}}")
        assert ck_exists(bib_dir, "X") is True

    def test_not_exists(self, ck_dirs):
        bib_dir, _ = ck_dirs
        assert ck_exists(bib_dir, "NoSuchPaper") is False


class TestListCks:
    def test_lists_from_bib_dir(self, populated_library):
        bib_dir, _ = populated_library
        cks = list_cks(bib_dir, False)
        assert "KZG10" in cks
        assert "BLS01" in cks
        assert "GMR85" in cks

    def test_sorted_output(self, populated_library):
        bib_dir, _ = populated_library
        cks = list_cks(bib_dir, False)
        assert cks == sorted(cks)

    def test_lists_from_tag_dir(self, populated_library):
        _, tag_dir = populated_library
        cks = list_cks(os.path.join(tag_dir, "sigs"), False)
        assert "BLS01" in cks

    def test_recursive(self, populated_library):
        _, tag_dir = populated_library
        cks = list_cks(tag_dir, True)
        assert "BLS01" in cks
        assert "KZG10" in cks

    def test_skips_dotted_filenames(self, ck_dirs):
        """Files like paper.slides.pdf should be skipped."""
        bib_dir, _ = ck_dirs
        with open(os.path.join(bib_dir, "X.pdf"), "wb") as f:
            f.write(b"%PDF")
        with open(os.path.join(bib_dir, "X.slides.pdf"), "wb") as f:
            f.write(b"%PDF")
        cks = list_cks(bib_dir, False)
        assert "X" in cks
        assert len(cks) == 1  # X.slides should not appear


class TestWaitForBrowserPdf:
    @pytest.fixture
    def dirs(self, tmp_path):
        downloads = tmp_path / "Downloads"
        downloads.mkdir()
        dest = tmp_path / "Papers" / "KZG10.pdf"
        dest.parent.mkdir()
        return str(downloads), str(dest)

    def _write(self, path, data=b"%PDF-fake", mtime=None):
        with open(path, "wb") as f:
            f.write(data)
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return str(path)

    def test_finds_fresh_pdf(self, dirs):
        downloads, dest = dirs
        pdf = self._write(os.path.join(downloads, "721.pdf"))
        found = wait_for_browser_pdf(downloads, dest, newer_than=time.time() - 10, timeout=2)
        assert found == pdf

    def test_ignores_old_pdfs(self, dirs):
        downloads, dest = dirs
        self._write(os.path.join(downloads, "old.pdf"), mtime=time.time() - 3600)
        found = wait_for_browser_pdf(downloads, dest, newer_than=time.time() - 10, timeout=0.2, poll_interval=0.05)
        assert found is None

    def test_ignores_partial_and_empty_files(self, dirs):
        downloads, dest = dirs
        self._write(os.path.join(downloads, "721.pdf.crdownload"))
        self._write(os.path.join(downloads, "empty.pdf"), data=b"")
        found = wait_for_browser_pdf(downloads, dest, newer_than=time.time() - 10, timeout=0.2, poll_interval=0.05)
        assert found is None

    def test_prefers_dest_if_saved_directly(self, dirs):
        downloads, dest = dirs
        self._write(os.path.join(downloads, "721.pdf"))
        self._write(dest)
        found = wait_for_browser_pdf(downloads, dest, newer_than=time.time() - 10, timeout=2)
        assert found == dest

    def test_picks_newest_of_multiple(self, dirs):
        downloads, dest = dirs
        now = time.time()
        self._write(os.path.join(downloads, "first.pdf"), mtime=now - 5)
        newest = self._write(os.path.join(downloads, "second.pdf"), mtime=now)
        found = wait_for_browser_pdf(downloads, dest, newer_than=now - 10, timeout=2)
        assert found == newest

    def test_times_out_on_empty_dir(self, dirs):
        downloads, dest = dirs
        found = wait_for_browser_pdf(downloads, dest, newer_than=time.time(), timeout=0.2, poll_interval=0.05)
        assert found is None

    def test_missing_downloads_dir(self, dirs):
        _, dest = dirs
        found = wait_for_browser_pdf("/nonexistent/dir", dest, newer_than=time.time(), timeout=0.2, poll_interval=0.05)
        assert found is None


class TestCksFromTags:
    def test_single_tag(self, populated_library):
        _, tag_dir = populated_library
        cks = cks_from_tags(tag_dir, ["sigs"])
        assert "BLS01" in cks

    def test_multiple_tags(self, populated_library):
        _, tag_dir = populated_library
        cks = cks_from_tags(tag_dir, ["sigs", "commitments"])
        assert "BLS01" in cks
        assert "KZG10" in cks

    def test_recursive_default(self, populated_library):
        _, tag_dir = populated_library
        cks = cks_from_tags(tag_dir, ["sigs"], recursive=True)
        assert "BLS01" in cks  # tagged directly and via sigs/bls
