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

    pip install click pyperclip beautifulsoup4 appdirs fake-useragent bibtexparser lxml

Fill in `ck.config` and put it in your [user_config_dir folder](https://pypi.org/project/appdirs/).

For auto tag-suggesting, you can install pdfgrep (optional):
    
    apt install pdfgrep # Ubuntu/Debian
    brew install pdfgrep # mac

To install bash auto-completion, run

    source bash-completion.d/ck

Other useful, related repositories
----------------------------------

 - [zotero translators](https://github.com/zotero/translators/blob/master/IEEE%20Xplore.js)
 - [BibFromXplore.sh](https://github.com/rval735/BNN-PhD/blob/9a8941bbdf2a9c0dbda4420b522ca306da216e0c/Scripts/BibFromXplore.sh)
 - [AnyBibTeX](https://github.com/Livich/AnyBibTeX)
 - [iacr-dl](https://github.com/znewman01/iacr-dl)
 - [bibcure](https://github.com/bibcure/bibcure)
 - [scihub2pdf](https://github.com/bibcure/scihub2pdf)
 - [scholrref](https://adamsgaard.dk/scholarref.html)

Just search GitHub for more: ["ieeexplore downloadcitations"](https://github.com/search?q=ieeexplore+downloadcitations&type=Code)

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

 - if PDFs are not available from publisher, try sci-hub.tw: see [python example here](https://gist.github.com/mpratt14/df20f09a06ba4249f3fad0776610f39d)
 - figure out how to have a setup.py that installs this thing
 - tools for making the .bib files consistent
    + titles should have double brackets
    + same conference shouldn't have different names
    + author names should always be separated by ' and '
    - similar or incomplete author names
 - how to deal with multiple versions of the same paper (eprint, conference, journal)
    + when published in the same year, we could have the eprint version as an extra `ABC99.eprint.pdf` file
    - when published in different years, can just have a new CK for it
    - `open` should be adjusted to prompt user for what to open, if multiple `.pdf` files exist for a CK?
 - `ck` command
    - `list` subcommand
        - display associated file info
            - nopdf
            - nobib
            - md
            - any other files (e.g., ABC19.slides.pdf)
        - add sort-by options
            - need sort by most recently added (with date & time displayed)
        - list all conferences across papers
    - `open` subcommand
        - add support for various associated files: .bib, .html, .md, .notes.\[0-9\]\*.pdf, .slides.pdf, .etc
        - [DONE] autocomplete citation key
            + see [bash guide here](https://tuzz.tech/blog/how-bash-completion-works)
        - if you type in a partial citation key, should list all matches
            - if just one match, should just open it, displaying a warning that it only partially matched so as to not train you to use the wrong CK
        - if you type an ambiguous citation key (lowercase / uppercase), maybe you should be prompted for what to open, because there won't be many matches.
    - `untag` subcommand
        + right now, if we only have a `.bib` file without any PDFs, `untag` will not detect any untagged papers. how to handle?
