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

### 1. Add a `ck` function to your shell config

Add the following to your `~/.bashrc` or `~/.bash_aliases`:

```bash
# Helper function to run ck with venv
function ck() {
    local ck_dir="$HOME/repos/ck"  # adjust path as needed
    local venv_dir="$ck_dir/venv"
    
    # Create venv if it doesn't exist
    if [ ! -d "$venv_dir" ]; then
        echo "Creating virtual environment..."
        python3 -m venv "$venv_dir" || return 1
    fi
    
    # Activate venv and install deps if needed
    source "$venv_dir/bin/activate"
    if ! python3 -c "import click" 2>/dev/null; then
        echo "Installing dependencies..."
        pip install -r "$ck_dir/requirements.txt" || return 1
    fi
    
    # Run ck with all arguments
    "$ck_dir/ck" "$@"
    
    deactivate
}
```

Then reload your shell config:

    source ~/.bashrc  # or ~/.bash_aliases

The first time you run `ck`, it will automatically create a virtual environment and install all dependencies.

### 2. Configure ck

Fill in `ck.config` and put it in your [user_config_dir folder](https://pypi.org/project/appdirs/).

### 3. Optional dependencies

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

    source venv/bin/activate
    python -m pytest -v

Skip slow network tests (URL handlers that hit real websites):

    python -m pytest -m "not integration" -v

Run only URL handler integration tests:

    python -m pytest tests/test_urlhandlers.py -v

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
