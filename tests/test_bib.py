"""Unit tests for citationkeys/bib.py"""

import pytest
from collections import defaultdict

from citationkeys.bib import (
    strip_accents,
    bibtex_to_bibent,
    bibtex_to_bibdb,
    bibent_to_bibtex,
    bibent_to_bibdb,
    bibent_new,
    bibent_from_url,
    bibent_from_file,
    bibent_to_file,
    bibent_canonicalize,
    bibent_get_url,
    bibent_get_venue,
    bibent_get_first_author_year_title_ck,
    bibent_get_author_initials_ck,
    bibent_to_default_ck,
    bibent_set_dateadded,
    bibent_to_markdown,
    bibent_to_text,
    bibpath_rename_ck,
)


class TestStripAccents:
    def test_plain_ascii(self):
        assert strip_accents("hello") == "hello"

    def test_accented_chars(self):
        assert strip_accents("café") == "cafe"
        assert strip_accents("naïve") == "naive"
        assert strip_accents("José") == "Jose"

    def test_empty_string(self):
        assert strip_accents("") == ""


class TestBibtexParsing:
    def test_parse_basic_entry(self, sample_bibtex):
        bibent = bibtex_to_bibent(sample_bibtex.decode())
        assert bibent["ID"] == "KZG10"
        assert bibent["ENTRYTYPE"] == "inproceedings"
        assert "Kate" in bibent["author"]
        assert "2010" == bibent["year"]

    def test_parse_preserves_fields(self):
        bibtex = """@article{Test01,
  author = {Alice Bob},
  title = {A Great Paper},
  journal = {Journal of Testing},
  year = {2001},
  volume = {42},
  pages = {1--10},
}"""
        bibent = bibtex_to_bibent(bibtex)
        assert bibent["volume"] == "42"
        # page_double_hyphen customization should normalize pages
        assert "--" in bibent["pages"]

    def test_parse_month_fields(self):
        """Bibtex with month = jun should parse without error."""
        bibtex = """@article{Test02,
  author = {Alice},
  title = {Monthly Paper},
  journal = {J. Test},
  year = {2002},
  month = jun,
}"""
        bibent = bibtex_to_bibent(bibtex)
        assert bibent["ID"] == "Test02"

    def test_roundtrip(self, sample_bibent):
        """Parse -> write -> parse should preserve key fields."""
        bibtex_str = bibent_to_bibtex(sample_bibent)
        reparsed = bibtex_to_bibent(bibtex_str)
        assert reparsed["ID"] == sample_bibent["ID"]
        assert reparsed["year"] == sample_bibent["year"]

    def test_bibdb_multiple_entries(self):
        bibtex = """@article{A, author={A}, title={A}, year={2000}}
@article{B, author={B}, title={B}, year={2001}}"""
        bibdb = bibtex_to_bibdb(bibtex)
        assert len(bibdb.entries) == 2


class TestBibentNew:
    def test_creates_entry(self):
        bibent = bibent_new("mykey", "article")
        assert bibent["ID"] == "mykey"
        assert bibent["ENTRYTYPE"] == "article"

    def test_from_url(self):
        bibent = bibent_from_url("test01", "https://example.com/paper.pdf")
        assert bibent["ID"] == "test01"
        assert "example.com" in bibent["howpublished"]
        assert bibent["author"] == ""


class TestBibentFileIO:
    def test_write_and_read(self, tmp_path, sample_bibent):
        bibfile = str(tmp_path / "test.bib")
        bibent_to_file(bibfile, sample_bibent)
        loaded = bibent_from_file(bibfile)
        assert loaded["ID"] == sample_bibent["ID"]
        assert loaded["year"] == sample_bibent["year"]

    def test_rename_ck(self, tmp_path, sample_bibent):
        bibfile = str(tmp_path / "test.bib")
        bibent_to_file(bibfile, sample_bibent)
        bibpath_rename_ck(bibfile, "NewKey99")
        loaded = bibent_from_file(bibfile)
        assert loaded["ID"] == "NewKey99"


class TestBibentCanonicalize:
    def test_fixes_mismatched_ck(self, sample_bibent):
        sample_bibent["ID"] = "wrong_key"
        updated = bibent_canonicalize("KZG10", sample_bibent, 0)
        assert updated is True
        assert sample_bibent["ID"] == "KZG10"

    def test_strips_author_whitespace(self):
        bibent = bibent_new("X", "article")
        bibent["author"] = "  Alice\n  and Bob\r\n  "
        bibent["title"] = "Title"
        updated = bibent_canonicalize("X", bibent, 0)
        assert updated is True
        assert "\n" not in bibent["author"]
        assert "\r" not in bibent["author"]

    def test_wraps_title_in_braces(self):
        bibent = bibent_new("X", "article")
        bibent["author"] = "Alice"
        bibent["title"] = "Some Title"
        updated = bibent_canonicalize("X", bibent, 0)
        assert updated is True
        assert bibent["title"].startswith("{")
        assert bibent["title"].endswith("}")

    def test_no_update_when_already_canonical(self, sample_bibent):
        # First canonicalize
        bibent_canonicalize("KZG10", sample_bibent, 0)
        # Second call should not need updates
        updated = bibent_canonicalize("KZG10", sample_bibent, 0)
        assert updated is False


class TestBibentGetUrl:
    def test_url_field(self):
        bibent = {"url": "https://example.com/paper"}
        assert bibent_get_url(bibent) == "https://example.com/paper"

    def test_howpublished_url(self):
        bibent = {"howpublished": "\\url{https://example.com/paper}"}
        assert bibent_get_url(bibent) == "https://example.com/paper"

    def test_note_url(self):
        bibent = {"note": "Available at \\url{https://example.com/paper}"}
        assert bibent_get_url(bibent) == "https://example.com/paper"

    def test_eprint_url(self):
        bibent = {"eprint": "https://arxiv.org/abs/1234.5678"}
        assert bibent_get_url(bibent) == "https://arxiv.org/abs/1234.5678"

    def test_eprint_non_url(self):
        bibent = {"eprint": "1234.5678"}
        assert bibent_get_url(bibent) is None

    def test_no_url(self):
        bibent = {"author": "Alice", "title": "Test"}
        assert bibent_get_url(bibent) is None


class TestBibentGetVenue:
    def test_booktitle(self):
        bibent = {"booktitle": "CRYPTO 2020"}
        assert bibent_get_venue(bibent) == "CRYPTO 2020"

    def test_journal(self):
        bibent = {"journal": "J. Cryptology"}
        assert bibent_get_venue(bibent) == "J. Cryptology"

    def test_howpublished_non_url(self):
        bibent = {"howpublished": "Technical Report"}
        assert bibent_get_venue(bibent) == "Technical Report"

    def test_howpublished_url_excluded(self):
        bibent = {"howpublished": "\\url{https://example.com}"}
        assert bibent_get_venue(bibent) is None

    def test_no_venue(self):
        bibent = {"author": "Alice"}
        assert bibent_get_venue(bibent) is None


class TestCitationKeyGeneration:
    def test_first_author_year_title(self):
        bibent = {"author": "Boneh Dan", "year": "2001", "title": "Short signatures"}
        ck = bibent_get_first_author_year_title_ck(bibent)
        assert "boneh" in ck
        assert "2001" in ck

    def test_initials_single_author(self):
        bibent = {"author": "Goldwasser, Shafi"}
        ck = bibent_get_author_initials_ck(bibent, 0)
        assert ck == "Gold"

    def test_initials_two_authors(self):
        bibent = {"author": "Kate, Aniket and Zaverucha, Gregory"}
        ck = bibent_get_author_initials_ck(bibent, 0)
        assert ck == "KZ"

    def test_initials_four_authors(self):
        bibent = {"author": "Alice A and Bob B and Charlie C and Dave D"}
        ck = bibent_get_author_initials_ck(bibent, 0)
        assert ck == "ABCD"

    def test_initials_five_plus_authors(self):
        bibent = {"author": "Alice A and Bob B and Charlie C and Dave D and Eve E"}
        ck = bibent_get_author_initials_ck(bibent, 0)
        assert ck == "ABC+"

    def test_default_ck_initials_short_year(self):
        bibent = defaultdict(lambda: "", {
            "ID": "orig",
            "author": "Kate, Aniket and Zaverucha, Gregory M. and Goldberg, Ian",
            "year": "2010",
            "title": "Test",
        })
        ck = bibent_to_default_ck(bibent, "InitialsShortYear", 0)
        assert ck == "KZG10"

    def test_default_ck_initials_full_year(self):
        bibent = defaultdict(lambda: "", {
            "ID": "orig",
            "author": "Kate, Aniket and Zaverucha, Gregory M. and Goldberg, Ian",
            "year": "2010",
            "title": "Test",
        })
        ck = bibent_to_default_ck(bibent, "InitialsFullYear", 0)
        assert ck == "KZG2010"

    def test_default_ck_keep_bibtex(self):
        bibent = defaultdict(lambda: "", {"ID": "OriginalKey", "author": "A", "year": "2000", "title": "T"})
        ck = bibent_to_default_ck(bibent, "KeepBibtex", 0)
        assert ck == "OriginalKey"


class TestBibentDateAdded:
    def test_set_custom_date(self, sample_bibent):
        bibent_set_dateadded(sample_bibent, "2024-01-01 12:00:00")
        assert sample_bibent["ckdateadded"] == "2024-01-01 12:00:00"

    def test_set_auto_date(self, sample_bibent):
        bibent_set_dateadded(sample_bibent, None)
        assert "ckdateadded" in sample_bibent
        # Should be a date-like string
        assert len(sample_bibent["ckdateadded"]) == 19


class TestBibentFormatting:
    def test_to_markdown(self, sample_bibent):
        md = bibent_to_markdown(sample_bibent)
        assert "[^KZG10]" in md
        assert "**" in md  # bold title

    def test_to_text(self, sample_bibent):
        txt = bibent_to_text(sample_bibent)
        assert "[KZG10]" in txt
        assert "Kate" in txt
