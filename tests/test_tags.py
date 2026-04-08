"""Unit tests for citationkeys/tags.py"""

import os

import pytest

from citationkeys.tags import (
    find_tagged_pdfs,
    find_untagged_pdfs,
    get_all_tags,
    tag_paper,
    untag_paper,
    parse_tags,
    tags_filter_whitespace,
)


class TestGetAllTags:
    def test_empty_dir(self, ck_dirs):
        _, tag_dir = ck_dirs
        assert get_all_tags(tag_dir) == []

    def test_flat_tags(self, ck_dirs):
        _, tag_dir = ck_dirs
        os.makedirs(os.path.join(tag_dir, "crypto"))
        os.makedirs(os.path.join(tag_dir, "sigs"))
        tags = get_all_tags(tag_dir)
        assert "crypto" in tags
        assert "sigs" in tags

    def test_hierarchical_tags(self, ck_dirs):
        _, tag_dir = ck_dirs
        os.makedirs(os.path.join(tag_dir, "sigs", "bls"))
        os.makedirs(os.path.join(tag_dir, "sigs", "schnorr"))
        tags = get_all_tags(tag_dir)
        assert "sigs" in tags
        assert "sigs/bls" in tags
        assert "sigs/schnorr" in tags

    def test_ignores_git_dirs(self, ck_dirs):
        _, tag_dir = ck_dirs
        os.makedirs(os.path.join(tag_dir, ".git"))
        os.makedirs(os.path.join(tag_dir, ".gitignore_dir"))
        os.makedirs(os.path.join(tag_dir, "real-tag"))
        tags = get_all_tags(tag_dir)
        assert "real-tag" in tags
        assert ".git" not in tags

    def test_sorted_output(self, ck_dirs):
        _, tag_dir = ck_dirs
        for name in ["z-tag", "a-tag", "m-tag"]:
            os.makedirs(os.path.join(tag_dir, name))
        tags = get_all_tags(tag_dir)
        assert tags == sorted(tags)


class TestTagPaper:
    def test_tag_creates_symlink(self, ck_dirs):
        bib_dir, tag_dir = ck_dirs
        # Create a dummy PDF
        pdf_path = os.path.join(bib_dir, "KZG10.pdf")
        with open(pdf_path, "wb") as f:
            f.write(b"%PDF fake")

        result = tag_paper(tag_dir, bib_dir, "KZG10", "commitments")
        assert result is True

        symlink = os.path.join(tag_dir, "commitments", "KZG10.pdf")
        assert os.path.islink(symlink)
        assert os.readlink(symlink) == pdf_path

    def test_tag_creates_nested_dirs(self, ck_dirs):
        bib_dir, tag_dir = ck_dirs
        with open(os.path.join(bib_dir, "X.pdf"), "wb") as f:
            f.write(b"%PDF")

        tag_paper(tag_dir, bib_dir, "X", "crypto/zk/snarks")
        assert os.path.isdir(os.path.join(tag_dir, "crypto", "zk", "snarks"))

    def test_tag_duplicate_returns_false(self, ck_dirs):
        bib_dir, tag_dir = ck_dirs
        with open(os.path.join(bib_dir, "X.pdf"), "wb") as f:
            f.write(b"%PDF")

        assert tag_paper(tag_dir, bib_dir, "X", "t") is True
        assert tag_paper(tag_dir, bib_dir, "X", "t") is False


class TestUntagPaper:
    def test_untag_specific(self, ck_dirs):
        bib_dir, tag_dir = ck_dirs
        with open(os.path.join(bib_dir, "X.pdf"), "wb") as f:
            f.write(b"%PDF")

        tag_paper(tag_dir, bib_dir, "X", "t1")
        tag_paper(tag_dir, bib_dir, "X", "t2")

        assert untag_paper(tag_dir, "X", "t1") is True
        assert not os.path.exists(os.path.join(tag_dir, "t1", "X.pdf"))
        # t2 should still exist
        assert os.path.islink(os.path.join(tag_dir, "t2", "X.pdf"))

    def test_untag_all(self, ck_dirs):
        bib_dir, tag_dir = ck_dirs
        with open(os.path.join(bib_dir, "X.pdf"), "wb") as f:
            f.write(b"%PDF")

        tag_paper(tag_dir, bib_dir, "X", "t1")
        tag_paper(tag_dir, bib_dir, "X", "t2")

        assert untag_paper(tag_dir, "X") is True
        assert not os.path.exists(os.path.join(tag_dir, "t1", "X.pdf"))
        assert not os.path.exists(os.path.join(tag_dir, "t2", "X.pdf"))

    def test_untag_nonexistent(self, ck_dirs):
        _, tag_dir = ck_dirs
        assert untag_paper(tag_dir, "NoSuchPaper", "t1") is False


class TestFindTaggedPdfs:
    def test_finds_tagged(self, populated_library):
        _, tag_dir = populated_library
        pdfs = find_tagged_pdfs(tag_dir, 0)
        assert "BLS01" in pdfs
        assert "sigs" in pdfs["BLS01"]
        assert "sigs/bls" in pdfs["BLS01"]
        assert "KZG10" in pdfs
        assert "commitments" in pdfs["KZG10"]

    def test_untagged_not_found(self, populated_library):
        _, tag_dir = populated_library
        pdfs = find_tagged_pdfs(tag_dir, 0)
        assert "GMR85" not in pdfs


class TestFindUntaggedPdfs:
    def test_finds_untagged(self, populated_library):
        bib_dir, tag_dir = populated_library
        from citationkeys.misc import list_cks
        cks = list_cks(bib_dir, False)
        tagged = find_tagged_pdfs(tag_dir, 0)
        untagged = find_untagged_pdfs(bib_dir, tag_dir, cks, tagged.keys(), 0)
        untagged_cks = {ck for _, ck in untagged}
        assert "GMR85" in untagged_cks
        assert "BLS01" not in untagged_cks
        assert "KZG10" not in untagged_cks


class TestParseTags:
    def test_comma_separated(self):
        assert parse_tags("crypto,sigs,zk") == ["crypto", "sigs", "zk"]

    def test_strips_whitespace(self):
        assert parse_tags("  crypto , sigs , zk  ") == ["crypto", "sigs", "zk"]

    def test_empty_entries_filtered(self):
        assert parse_tags("crypto,,sigs,") == ["crypto", "sigs"]

    def test_custom_splitter(self):
        assert parse_tags("crypto;sigs", splitter=";") == ["crypto", "sigs"]


class TestTagsFilterWhitespace:
    def test_strips_and_filters(self):
        assert tags_filter_whitespace(["  a  ", "", "  ", "b"]) == ["a", "b"]
