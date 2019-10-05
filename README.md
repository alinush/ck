CK
==

A command-line tool for managing your bibliography (i.e., `.bib` files and `.pdf` files) across multiple machines using Dropbox.

Features:

 - add papers, sorted by citation key, to Dropbox
 - easily open any paper given its citation key
 - organize papers by tagging them
 - generate a full `.bib` file of all your papers

Dependencies
------------

    pip install click pyperclip beautifulsoup4 appdirs fake-useragent bibtexparser

Other useful, related repositories
----------------------------------

 - [zotero translators](https://github.com/zotero/translators/blob/master/IEEE%20Xplore.js)
 - [BibFromXplore.sh](https://github.com/rval735/BNN-PhD/blob/9a8941bbdf2a9c0dbda4420b522ca306da216e0c/Scripts/BibFromXplore.sh)
 - [AnyBibTeX](https://github.com/Livich/AnyBibTeX)
 - [paperbot](https://github.com/kanzure/paperbot)
 - [iacr-dl](https://github.com/znewman01/iacr-dl)

Just search GitHub for more: ["ieeexplore downloadcitations"](https://github.com/search?q=ieeexplore+downloadcitations&type=Code)

TODOs
-----

 - if PDFs are not available from publisher, try sci-hub.tw: see [python example here](https://gist.github.com/mpratt14/df20f09a06ba4249f3fad0776610f39d)
 - figure out how to have a setup.py that installs this thing
 - how to list files sorted by add date? where to keep a 'date-added' field?
 - add aliases for subcommands; see [here](http://click.palletsprojects.com/en/5.x/advanced/)
 - `ck` command
    - list all conferences across papers
    + `open` subcommand
        - autocomplete citation key
        - if you type in a partial citation key, should list all matches
            - if just one match, should just open it, displaying a warning that it only partially matched so as to not train you to use the wrong CK
        - if you type an ambiguous citation key (lowercase / uppercase), maybe you should be prompted for what to open, because there won't be many matches.
