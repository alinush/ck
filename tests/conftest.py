import configparser
import os
import tempfile

import pytest


@pytest.fixture
def ck_dirs(tmp_path):
    """Creates temporary BibDir and TagDir for testing."""
    bib_dir = tmp_path / "papers"
    tag_dir = tmp_path / "tags"
    bib_dir.mkdir()
    tag_dir.mkdir()
    return str(bib_dir), str(tag_dir)


@pytest.fixture
def ck_config(tmp_path, ck_dirs):
    """Creates a temporary ck config file pointing to temp dirs."""
    bib_dir, tag_dir = ck_dirs
    config_path = tmp_path / "ck.config"
    config_path.write_text(f"""[default]
BibDir                = {bib_dir}
TagDir                = {tag_dir}
DefaultCk             = InitialsShortYear
TextEditor            = vim
MarkdownEditor        = vim
TagAfterCkAddConflict = false
""")
    return str(config_path)


@pytest.fixture
def sample_bibtex():
    """Returns a sample BibTeX string for testing."""
    return b"""@inproceedings{KZG10,
  author    = {Kate, Aniket and Zaverucha, Gregory M. and Goldberg, Ian},
  title     = {Constant-Size Commitments to Polynomials and Their Applications},
  booktitle = {ASIACRYPT},
  year      = {2010},
}"""


@pytest.fixture
def sample_bibent():
    """Returns a parsed bibentry dict for testing."""
    from citationkeys.bib import bibtex_to_bibent
    bibtex = """@inproceedings{KZG10,
  author    = {Kate, Aniket and Zaverucha, Gregory M. and Goldberg, Ian},
  title     = {Constant-Size Commitments to Polynomials and Their Applications},
  booktitle = {ASIACRYPT},
  year      = {2010},
}"""
    return bibtex_to_bibent(bibtex)


@pytest.fixture
def populated_library(ck_dirs):
    """Creates a library with a few papers (bib + dummy PDF) and tags."""
    bib_dir, tag_dir = ck_dirs

    papers = {
        "KZG10": b"""@inproceedings{KZG10,
  author = {Kate, Aniket and Zaverucha, Gregory M. and Goldberg, Ian},
  title = {Constant-Size Commitments to Polynomials and Their Applications},
  booktitle = {ASIACRYPT},
  year = {2010},
  ckdateadded = {2024-01-15 10:30:00},
}""",
        "BLS01": b"""@article{BLS01,
  author = {Boneh, Dan and Lynn, Ben and Shacham, Hovav},
  title = {Short Signatures from the Weil Pairing},
  journal = {Journal of Cryptology},
  year = {2001},
  ckdateadded = {2024-02-20 14:00:00},
}""",
        "GMR85": b"""@inproceedings{GMR85,
  author = {Goldwasser, Shafi and Micali, Silvio and Rackoff, Charles},
  title = {The Knowledge Complexity of Interactive Proof-Systems},
  booktitle = {STOC},
  year = {1985},
  ckdateadded = {2024-03-01 09:00:00},
}""",
    }

    # Write .bib and dummy .pdf files
    for ck, bibtex in papers.items():
        with open(os.path.join(bib_dir, ck + ".bib"), "wb") as f:
            f.write(bibtex)
        with open(os.path.join(bib_dir, ck + ".pdf"), "wb") as f:
            f.write(b"%PDF-1.4 fake pdf content for " + ck.encode())

    # Create some tags with symlinks
    for tag in ["sigs", "commitments", "sigs/bls"]:
        os.makedirs(os.path.join(tag_dir, tag), exist_ok=True)

    # Tag papers
    os.symlink(
        os.path.join(bib_dir, "BLS01.pdf"),
        os.path.join(tag_dir, "sigs", "BLS01.pdf"),
    )
    os.symlink(
        os.path.join(bib_dir, "BLS01.pdf"),
        os.path.join(tag_dir, "sigs/bls", "BLS01.pdf"),
    )
    os.symlink(
        os.path.join(bib_dir, "KZG10.pdf"),
        os.path.join(tag_dir, "commitments", "KZG10.pdf"),
    )

    return bib_dir, tag_dir
