"""Tests for 'ck addbib' with a local .bib file path.

Runs the 'ck' script in a subprocess against a temporary library, so no
network access is needed.
"""

import os
import subprocess
import sys

import pytest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CK_SCRIPT = os.path.join(REPO_DIR, "ck")

SAMPLE_BIBTEX = """@inproceedings{tomescu2019transparency,
  author = {Alin Tomescu and Vivek Bhupatiraju and Dimitrios Papadopoulos and Charalampos Papamanthou and Nikos Triandopoulos and Srinivas Devadas},
  title = {Transparency Logs via Append-Only Authenticated Dictionaries},
  booktitle = {ACM CCS},
  year = {2019},
}
"""

OTHER_BIBTEX = """@article{BLS01,
  author = {Boneh, Dan and Lynn, Ben and Shacham, Hovav},
  title = {Short Signatures from the Weil Pairing},
  journal = {Journal of Cryptology},
  year = {2001},
}
"""


def run_addbib(ck_config, *args, stdin=""):
    """Runs 'ck addbib' with the given arguments and returns the completed process."""
    return subprocess.run(
        [sys.executable, CK_SCRIPT, "-c", ck_config, "addbib"] + list(args),
        capture_output=True, text=True, input=stdin, cwd=REPO_DIR,
    )


@pytest.fixture
def bib_file(tmp_path):
    """Writes a local .bib file to add to the library."""
    path = tmp_path / "downloaded.bib"
    path.write_text(SAMPLE_BIBTEX)
    return str(path)


class TestAddbibLocalFile:
    def test_adds_local_bib_file(self, ck_config, ck_dirs, bib_file):
        bib_dir, _ = ck_dirs
        res = run_addbib(ck_config, bib_file)

        assert res.returncode == 0, res.stderr
        assert "Local .bib file detected" in res.stdout

        # The DefaultCk policy (InitialsShortYear) picks the citation key
        destbibfile = os.path.join(bib_dir, "TBP+19.bib")
        assert os.path.exists(destbibfile)

        written = open(destbibfile).read()
        assert "Transparency Logs via Append-Only Authenticated Dictionaries" in written
        # The citation key in the .bib file is rewritten to match the filename
        assert "@inproceedings{TBP+19," in written
        # The date added is set for us
        assert "ckdateadded" in written

    def test_uses_given_citation_key(self, ck_config, ck_dirs, bib_file):
        bib_dir, _ = ck_dirs
        res = run_addbib(ck_config, bib_file, "AlinCCS19")

        assert res.returncode == 0, res.stderr
        assert os.path.exists(os.path.join(bib_dir, "AlinCCS19.bib"))
        assert not os.path.exists(os.path.join(bib_dir, "TBP+19.bib"))

    def test_no_pdf_is_created(self, ck_config, ck_dirs, bib_file):
        bib_dir, _ = ck_dirs
        run_addbib(ck_config, bib_file, "AlinCCS19")

        assert not os.path.exists(os.path.join(bib_dir, "AlinCCS19.pdf"))

    def test_multiple_entries_warns_and_adds_first(self, ck_config, ck_dirs, tmp_path):
        bib_dir, _ = ck_dirs
        path = tmp_path / "two.bib"
        path.write_text(SAMPLE_BIBTEX + "\n" + OTHER_BIBTEX)

        res = run_addbib(ck_config, str(path), "AlinCCS19")

        assert res.returncode == 0, res.stderr
        assert "2 BibTeX entries" in res.stdout
        written = open(os.path.join(bib_dir, "AlinCCS19.bib")).read()
        assert "Transparency Logs" in written
        assert "Weil Pairing" not in written

    def test_empty_file_errors_out(self, ck_config, ck_dirs, tmp_path):
        bib_dir, _ = ck_dirs
        path = tmp_path / "empty.bib"
        path.write_text("")

        res = run_addbib(ck_config, str(path))

        assert res.returncode != 0
        assert "No BibTeX entry found" in res.stderr
        assert os.listdir(bib_dir) == []

    def test_unparseable_file_errors_out(self, ck_config, ck_dirs, tmp_path):
        bib_dir, _ = ck_dirs
        path = tmp_path / "junk.bib"
        path.write_text("this is not BibTeX at all")

        res = run_addbib(ck_config, str(path))

        assert res.returncode != 0
        assert os.listdir(bib_dir) == []

    def test_conflicting_ck_prints_existing_paper(self, ck_config, ck_dirs, bib_file):
        bib_dir, _ = ck_dirs
        run_addbib(ck_config, bib_file, "AlinCCS19")

        # Adding it again under the same CK conflicts: ck describes both papers and
        # prompts for a new citation key (EOF on stdin aborts the prompt).
        res = run_addbib(ck_config, bib_file, "AlinCCS19")

        assert "Existing paper: " in res.stdout
        assert "New paper:      " in res.stdout
        assert "Transparency Logs via Append-Only Authenticated Dictionaries" in res.stdout
        assert "already exists" in res.stdout
