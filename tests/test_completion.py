"""Tests for bash completion.

Runs the bash completion script in a subprocess with mock COMP_WORDS,
then checks COMPREPLY for expected values.
"""

import os
import subprocess
import textwrap

import pytest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPLETION_SCRIPT = os.path.join(REPO_DIR, "bash_completion.d", "ck")


def run_completion(tag_dir, bib_dir, comp_words, comp_cword, func="_citation_key_ck_completion", cwd=None):
    """Run a completion function and return COMPREPLY as a list."""
    config_file = os.path.join(os.path.dirname(tag_dir), "ck-test.config")

    # Write a test config
    with open(config_file, "w") as f:
        f.write(textwrap.dedent(f"""\
            [default]
            BibDir                = {bib_dir}
            TagDir                = {tag_dir}
            DefaultCk             = InitialsShortYear
            TextEditor            = vim
            MarkdownEditor        = vim
            TagAfterCkAddConflict = false
        """))

    # Build the COMP_WORDS array assignment
    words_str = " ".join(f'"{w}"' for w in comp_words)

    script = textwrap.dedent(f"""\
        shopt -s extglob

        # Mock ck command
        ck() {{
            if [ "$1" == "config" ]; then
                echo "{config_file}"
            elif [ "$1" == "list" ]; then
                echo "BLS01"
                echo "GMR85"
                echo "KZG10"
            elif [ "$1" == "--help" ]; then
                cat <<'HELPEOF'
Usage: ck [OPTIONS] COMMAND [ARGS]...

Commands:
  add       Adds a paper
  bib       Shows the BibTeX
  info      Shows paper info
  list      Lists papers
  open      Opens PDF
  rename    Renames a paper
  rm        Removes a paper
  tag       Tags a paper
  untag     Untags a paper
HELPEOF
            fi
        }}

        # Stub bash-completion functions
        _get_comp_words_by_ref() {{ :; }}
        _compopt_o_filenames() {{ :; }}
        _rl_enabled() {{ return 1; }}
        _filedir() {{ :; }}

        source "{COMPLETION_SCRIPT}"

        COMP_WORDS=({words_str})
        COMP_CWORD={comp_cword}
        COMPREPLY=()
        {func}

        # Print one reply per line
        for r in "${{COMPREPLY[@]}}"; do
            echo "$r"
        done
    """)

    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True, text=True,
        cwd=cwd,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Completion script failed: {result.stderr}")
    return [line for line in result.stdout.strip().split("\n") if line]


@pytest.fixture
def completion_dirs(tmp_path):
    """Set up tag and bib dirs with test data for completion tests."""
    tag_dir = tmp_path / "tags"
    bib_dir = tmp_path / "papers"
    tag_dir.mkdir()
    bib_dir.mkdir()

    # Create tag hierarchy
    for tag in [
        "sigs/bls", "sigs/schnorr", "sigs/threshold/frost",
        "commitments", "encryption/abe", "encryption/fhe", "zkproofs",
    ]:
        (tag_dir / tag).mkdir(parents=True)

    # Create dummy papers
    for ck in ["KZG10", "BLS01", "GMR85"]:
        (bib_dir / f"{ck}.pdf").write_bytes(b"%PDF fake")
        (bib_dir / f"{ck}.bib").write_text(
            f"@article{{{ck}, author={{Test}}, title={{Test}}, year={{2000}}, ckdateadded={{2024-01-01 00:00:00}}}}\n"
        )

    # Tag a paper
    os.symlink(str(bib_dir / "BLS01.pdf"), str(tag_dir / "sigs" / "BLS01.pdf"))

    return str(tag_dir), str(bib_dir)


class TestCkCompleteTagsHelper:
    """Tests for the _ck_complete_tags helper function."""

    def test_top_level_tags(self, completion_dirs):
        tag_dir, bib_dir = completion_dirs
        # Call _ck_complete_tags directly
        replies = run_completion(
            tag_dir, bib_dir,
            comp_words=["ck", "l", "-t", ""],
            comp_cword=3,
        )
        assert "sigs/" in replies
        assert "commitments" in replies
        assert "encryption/" in replies
        assert "zkproofs" in replies

    def test_prefix_filtering(self, completion_dirs):
        tag_dir, bib_dir = completion_dirs
        replies = run_completion(
            tag_dir, bib_dir,
            comp_words=["ck", "l", "-t", "sig"],
            comp_cword=3,
        )
        assert "sigs/" in replies
        assert "commitments" not in replies

    def test_subtags(self, completion_dirs):
        tag_dir, bib_dir = completion_dirs
        replies = run_completion(
            tag_dir, bib_dir,
            comp_words=["ck", "l", "-t", "sigs/"],
            comp_cword=3,
        )
        assert "sigs/bls" in replies
        assert "sigs/schnorr" in replies
        assert "sigs/threshold/" in replies

    def test_deeper_nesting(self, completion_dirs):
        tag_dir, bib_dir = completion_dirs
        replies = run_completion(
            tag_dir, bib_dir,
            comp_words=["ck", "l", "-t", "sigs/threshold/"],
            comp_cword=3,
        )
        assert "sigs/threshold/frost" in replies

    def test_slash_suffix_only_on_dirs_with_children(self, completion_dirs):
        tag_dir, bib_dir = completion_dirs
        replies = run_completion(
            tag_dir, bib_dir,
            comp_words=["ck", "l", "-t", ""],
            comp_cword=3,
        )
        # sigs and encryption have children -> trailing /
        assert "sigs/" in replies
        assert "encryption/" in replies
        # commitments and zkproofs are leaves -> no trailing /
        assert "commitments" in replies
        assert "zkproofs" in replies

    def test_single_match_expands_with_children(self, completion_dirs):
        """When only one match and it ends with /, children are included
        so bash doesn't append a space."""
        tag_dir, bib_dir = completion_dirs
        replies = run_completion(
            tag_dir, bib_dir,
            comp_words=["ck", "l", "-t", "sig"],
            comp_cword=3,
        )
        assert "sigs/" in replies
        # Children should also be present
        assert "sigs/bls" in replies


class TestTagCommand:
    def test_first_arg_completes_cks(self, completion_dirs):
        tag_dir, bib_dir = completion_dirs
        replies = run_completion(
            tag_dir, bib_dir,
            comp_words=["ck", "tag", ""],
            comp_cword=2,
        )
        assert "KZG10" in replies
        assert "BLS01" in replies
        assert "GMR85" in replies

    def test_second_arg_completes_tags(self, completion_dirs):
        tag_dir, bib_dir = completion_dirs
        replies = run_completion(
            tag_dir, bib_dir,
            comp_words=["ck", "tag", "KZG10", ""],
            comp_cword=3,
        )
        assert "sigs/" in replies
        assert "commitments" in replies
        assert "KZG10" not in replies

    def test_remove_flag_completes_tags(self, completion_dirs):
        tag_dir, bib_dir = completion_dirs
        replies = run_completion(
            tag_dir, bib_dir,
            comp_words=["ck", "tag", "-r", ""],
            comp_cword=3,
        )
        assert "sigs/" in replies
        assert "commitments" in replies


class TestListCommand:
    def test_with_tags_flag(self, completion_dirs):
        tag_dir, bib_dir = completion_dirs
        replies = run_completion(
            tag_dir, bib_dir,
            comp_words=["ck", "l", "-t", ""],
            comp_cword=3,
        )
        assert "sigs/" in replies

    def test_with_long_tags_flag(self, completion_dirs):
        tag_dir, bib_dir = completion_dirs
        replies = run_completion(
            tag_dir, bib_dir,
            comp_words=["ck", "list", "--tags", ""],
            comp_cword=3,
        )
        assert "sigs/" in replies


class TestOpenCommand:
    def test_completes_cks(self, completion_dirs):
        tag_dir, bib_dir = completion_dirs
        replies = run_completion(
            tag_dir, bib_dir,
            comp_words=["ck", "open", ""],
            comp_cword=2,
        )
        assert "KZG10" in replies


class TestSubcommands:
    def test_lists_subcommands(self, completion_dirs):
        tag_dir, bib_dir = completion_dirs
        replies = run_completion(
            tag_dir, bib_dir,
            comp_words=["ck", ""],
            comp_cword=1,
        )
        assert "add" in replies
        assert "tag" in replies
        assert "list" in replies

    def test_removed_commands_absent(self, completion_dirs):
        tag_dir, bib_dir = completion_dirs
        replies = run_completion(
            tag_dir, bib_dir,
            comp_words=["ck", ""],
            comp_cword=1,
        )
        assert "queue" not in replies
        assert "dequeue" not in replies
        assert "read" not in replies
        assert "finished" not in replies


class TestAddCommand:
    """Tests for ck add file path completion."""

    @pytest.fixture
    def pdf_dir(self, tmp_path):
        """Create a directory with some PDF files and subdirs for testing."""
        d = tmp_path / "downloads"
        d.mkdir()
        (d / "paper1.pdf").write_bytes(b"%PDF fake")
        (d / "paper2.pdf").write_bytes(b"%PDF fake")
        (d / "notes.txt").write_bytes(b"some notes")
        sub = d / "subdir"
        sub.mkdir()
        (sub / "deep.pdf").write_bytes(b"%PDF fake")
        return d

    def test_completes_files_in_cwd(self, completion_dirs, pdf_dir):
        tag_dir, bib_dir = completion_dirs
        replies = run_completion(
            tag_dir, bib_dir,
            comp_words=["ck", "add", ""],
            comp_cword=2,
            cwd=str(pdf_dir),
        )
        assert "paper1.pdf" in replies
        assert "paper2.pdf" in replies
        assert "notes.txt" in replies

    def test_completes_with_prefix(self, completion_dirs, pdf_dir):
        tag_dir, bib_dir = completion_dirs
        replies = run_completion(
            tag_dir, bib_dir,
            comp_words=["ck", "add", "paper"],
            comp_cword=2,
            cwd=str(pdf_dir),
        )
        assert "paper1.pdf" in replies
        assert "paper2.pdf" in replies
        assert "notes.txt" not in replies

    def test_directories_get_slash(self, completion_dirs, pdf_dir):
        tag_dir, bib_dir = completion_dirs
        replies = run_completion(
            tag_dir, bib_dir,
            comp_words=["ck", "add", "sub"],
            comp_cword=2,
            cwd=str(pdf_dir),
        )
        assert "subdir/" in replies

    def test_single_dir_match_expands_children(self, completion_dirs, pdf_dir):
        """When a single directory matches, its children are included so bash
        doesn't append a space and the user can keep tabbing deeper."""
        tag_dir, bib_dir = completion_dirs
        replies = run_completion(
            tag_dir, bib_dir,
            comp_words=["ck", "add", "sub"],
            comp_cword=2,
            cwd=str(pdf_dir),
        )
        assert "subdir/" in replies
        assert "subdir/deep.pdf" in replies

    def test_absolute_path_single_dir_expands_children(self, completion_dirs, pdf_dir):
        """Absolute path to a unique directory also expands children."""
        tag_dir, bib_dir = completion_dirs
        prefix = str(pdf_dir) + "/sub"
        replies = run_completion(
            tag_dir, bib_dir,
            comp_words=["ck", "add", prefix],
            comp_cword=2,
            cwd=str(pdf_dir),
        )
        assert str(pdf_dir) + "/subdir/" in replies
        assert str(pdf_dir) + "/subdir/deep.pdf" in replies

    def test_tag_option_completes_tags(self, completion_dirs, pdf_dir):
        tag_dir, bib_dir = completion_dirs
        replies = run_completion(
            tag_dir, bib_dir,
            comp_words=["ck", "add", "paper1.pdf", "MyCK", "-t", ""],
            comp_cword=5,
            cwd=str(pdf_dir),
        )
        assert "sigs/" in replies
        assert "commitments" in replies
