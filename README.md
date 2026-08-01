CK
==

A command-line tool for managing your bibliography (i.e., `.bib` files and `.pdf` files) across multiple machines using Dropbox.

Features:

 - add papers, sorted by citation key, to Dropbox
 - easily open any paper given its citation key
 - organize papers by tagging them
 - generate a full `.bib` file of all your papers
 - export papers with a particular tag

Setup
-----

### 1. Install uv

The `ck` script declares its own dependencies ([PEP 723](https://peps.python.org/pep-0723/) inline metadata) and runs itself through [uv](https://docs.astral.sh/uv/), so there is no virtual environment or `pip install` step:

    brew install uv                                  # macOS
    curl -LsSf https://astral.sh/uv/install.sh | sh  # Linux/other

### 2. Put `ck` on your `PATH`

Symlink the script into a directory on your `PATH` (adjust the repo path as needed):

    ln -s "$HOME/repos/ck/ck" ~/.local/bin/ck

or add an alias to your `~/.bashrc` or `~/.bash_aliases`:

    alias ck="$HOME/repos/ck/ck"

The first time you run `ck`, uv will download the dependencies into its cache; after that, it starts instantly. (Any other PEP 723-aware runner works too, e.g., `pipx run ./ck`.)

### 3. Configure ck

Fill in `ck.config` and put it in your [user_config_dir folder](https://pypi.org/project/appdirs/).

### 4. Optional dependencies

For auto tag-suggesting, you can install pdfgrep:

    apt install pdfgrep # Ubuntu/Debian
    brew install pdfgrep # Mac OS

For PDF generation features:

    brew install pango libffi # Mac OS

To install bash auto-completion on macOS, run:

    ./install-osx.sh

Testing
-------

Run all tests (unit + integration):

    uv run --with-requirements requirements.txt python -m pytest -v

Skip slow network tests (URL handlers that hit real websites):

    uv run --with-requirements requirements.txt python -m pytest -m "not integration" -v

Run only URL handler integration tests:

    uv run --with-requirements requirements.txt python -m pytest tests/test_urlhandlers.py -v

How to use
----------

    # add a paper to your library given a paywall URL (e.g., ACM DL, SpringerLink, IEEEXplore)
    # or an eprint url (e.g., IACR eprint)
    ck add <paper-url> <citation-key>

    # add a bib file to your library without a PDF
    ck open <citation-key>.bib
    # ...and edit the .bib file and save it

    # open a paper's PDF
    ck open <citation-key>
    ck open <citation-key>.pdf

    # open a paper's .bib file
    ck open <citation-key>.bib

    # tag the paper with <tag> (or enter tag manually from keyboard)
    ck tag <citation-key> [<tag>]

    # search all your .bib files and print matching papers' citation keys
    ck search <query>

TODOs
-----

### Bugs

 - some springerlink URLs don't work because they have .ris citations only
    + e.g., https://link.springer.com/article/10.1007/s10207-005-0071-2 

### Features

 - `ck open` with a partial citation key should list all matches
 - tools for making .bib files consistent (titles in brackets, conference name normalization)
 - add support for adding PDF from a local file
