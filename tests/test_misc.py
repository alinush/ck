"""Unit tests for citationkeys/misc.py"""

import os

import pytest

from citationkeys.misc import (
    ck_to_pdf,
    ck_to_bib,
    ck_exists,
    list_cks,
    is_cwd_in_tagdir,
    cks_from_tags,
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
