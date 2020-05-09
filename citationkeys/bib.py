#!/usr/bin/env python3

# NOTE: Alphabetical order please
from datetime import datetime
from pprint import pprint
from .tags import style_tags

# NOTE: Alphabetical order please
import bibtexparser
import click
import os
import sys
import traceback

def canonicalize_bibtex(ck, bibtex, verbosity):
    assert len(bibtex.entries) == 1
    updated = False

    for i in range(len(bibtex.entries)):
        bib = bibtex.entries[i]

        # make sure the CK in the .bib matches the filename
        bck = bib['ID']
        if bck != ck:
            if verbosity > 1:
                print(ck + ": Replaced unexpected '" + bck + "' CK in .bib file. Fixing...")
            bib['ID'] = ck
            updated = True

        author = bib['author'].replace('\r', '').replace('\n', ' ').strip()
        if bib['author'] != author:
            if verbosity > 1:
                print(ck + ": Stripped author name(s): " + author)
            bib['author'] = author
            updated = True

        title  = bib['title'].strip()
        if len(title) > 0 and title[0] != "{" and title[len(title)-1] != "}":
            title = "{" + title + "}"
        if bib['title'] != title:
            if verbosity > 1:
                print(ck + ": Added brackets to title: " + title)
            bib['title'] = title
            updated = True

    assert type(bib['ID']) == str

    return updated

def bib_new(citation_key, entry_type):
    bibtex = bibtexparser.bibdatabase.BibDatabase()
    bibtex.entries = [ { 'ID': citation_key, 'ENTRYTYPE': entry_type } ]
    return bibtex

def bib_read(destbibfile):
    with open(destbibfile) as bibf:
        # NOTE: Without this specially-created parser, the library fails parsing .bib files with 'month = jun' or 'month = sep' fields.
        parser = bibtexparser.bparser.BibTexParser(interpolate_strings=True, common_strings=True)
        bibtex = bibtexparser.load(bibf, parser)

        return bibtex

def bib_write(destbibfile, bibtex):
    with open(destbibfile, 'w') as bibf:
        bibwriter = bibtexparser.bwriter.BibTexWriter()
        canonicalize_bibtex(bibtex.entries[0]['ID'], bibtex, 0)
        bibf.write(bibwriter.write(bibtex))
    
def bib_rename_ck(destbibfile, citation_key):
    bibtex = bib_read(destbibfile)
    bibtex.entries[0]['ID'] = citation_key
    bib_write(destbibfile, bibtex)
        
# add ckdateadded field to keep track of papers by date added
def bib_set_dateadded(destbibfile, timestr):
    if timestr == None:
        now = datetime.now()
        timestr = now.strftime("%Y-%m-%d %H:%M:%S")

    #print("Time:", nowstr)
    bibtex = bib_read(destbibfile)
    bibtex.entries[0]['ckdateadded'] = timestr
    bib_write(destbibfile, bibtex)
