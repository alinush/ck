#!/usr/bin/env python3

# NOTE: Alphabetical order please
from datetime import datetime
from pprint import pprint
from .tags import style_tags

# NOTE: Alphabetical order please
import bibtexparser
import click
import os
import re
import string
import sys
import traceback
import unicodedata

# WARNING(Alin): Please abide by the naming convention:
#  - We refer to a bibtexparser.bibdatabase.BibDatabase object as bibdb
#  - We refer to a bibdb.entries[i] object as a bibentry
#  - We refer to a BibTeX string as bibtex
#  - We refer to a BibTeX file path as bibpath
#
# IMPORTANT: Function and argument names MUST explicitly use 'bibdb/bibent/bibtex' for clarity!

def strip_accents(s):
    """
    Sanitize the given Unicode string and remove all special/localized
    characters from it.

    Used to sanitize citation keys derived from authors' first names in the .bib file.
    """

    # Category "Mn" stands for Nonspacing_Mark
    try:
        return ''.join(
            c for c in unicodedata.normalize('NFD', s)
            if unicodedata.category(c) != 'Mn'
        )
    except:
        return s

def bibent_canonicalize(ck, bibent, verbosity):
    updated = False

    # make sure the CK in the .bib matches the filename
    bck = bibent['ID']
    if bck != ck:
        if verbosity > 1:
            print(ck + ": Replaced unexpected '" + bck + "' CK in .bib file. Fixing...")
        bibent['ID'] = ck
        updated = True

    author = bibent['author'].replace('\r', '').replace('\n', ' ').strip()
    if bibent['author'] != author:
        if verbosity > 1:
            print(ck + ": Stripped author name(s): " + author)
        bibent['author'] = author
        updated = True

    title  = bibent['title'].strip()
    if len(title) > 0 and title[0] != "{" and title[len(title)-1] != "}":
        title = "{" + title + "}"
    if bibent['title'] != title:
        if verbosity > 1:
            print(ck + ": Added brackets to title: " + title)
        bibent['title'] = title
        updated = True

    assert type(bibent['ID']) == str

    return updated

def bibent_to_bibdb(bibent):
    """Wraps a single bibentry into a bibdb, which other calls might expect"""
    bibdb = bibtexparser.bibdatabase.BibDatabase()
    bibdb.entries = [ bibent ] 
    return bibdb

def bibent_new(citation_key, entry_type):
    return { 'ID': citation_key, 'ENTRYTYPE': entry_type }

def bibdb_from_file(destbibfile):
    """Returns a bibdb from a BibTeX file"""
    with open(destbibfile) as bibf:
        # NOTE(Alin): Without this specially-created parser, the library fails parsing .bib files with 'month = jun' or 'month = sep' fields.
        parser = bibtexparser.bparser.BibTexParser(interpolate_strings=True, common_strings=True)
        bibdb = bibtexparser.load(bibf, parser)

        return bibdb

def bibent_from_file(destbibfile):
    """Returns a single bibentry (for one paper) from a BibTeX file"""
    bibdb = bibdb_from_file(destbibfile)
    assert len(bibdb.entries) == 1
    return bibdb.entries[0]

def bibent_to_file(destbibfile, bibent):
    with open(destbibfile, 'w') as bibf:
        bibf.write(bibent_to_bibtex(bibent))

# This takes a single 'bibtex[i]' entry (not a vector 'bibtex') as input
def bibent_get_url(bibent):
    url = None
    urlbibkey = None
    if 'note' in bibent and '\\url' in bibent['note']:
        urlbibkey = 'note'
    elif 'howpublished' in bibent and '\\url' in bibent['howpublished']:
        urlbibkey = 'howpublished'
    elif 'url' in bibent:
        url = bibent['url']
    elif 'eprint' in bibent and ('http://' in bibent['eprint'] or 'https://' in bibent['eprint']):
        # NOTE: Sometimes this is not a URL, just an eprint ID number, so have to check 'http' in bibent['eprint']
        url = bibent['eprint']

    if urlbibkey is not None:
        m = re.search("\\\\url{(.*)}", bibent[urlbibkey])
        url = m.group(1)

    return url

# TODO(Alex): Let's use last names!
def bibent_get_first_author_year_title_ck(bibent):
    citation_key = bibent['author'].split(' ')[0].lower() + \
                                bibent['year'] + \
                                bibent['title'].split(' ')[0].lower() # google-scholar-like
    citation_key = strip_accents(citation_key)
    citation_key = ''.join([c for c in citation_key if c in string.ascii_lowercase or c in string.digits]) # filter out strange chars
    return citation_key

def bibent_get_author_initials_ck(bibent):
    allAuthors = bibent['author'].split(' and ')
    print("all authors: ", allAuthors)
    moreThanFour = len(allAuthors) > 4

    # get the first four (or less) author names
    if moreThanFour:
        authors = allAuthors[:3]
    else:
        authors = allAuthors[:4]

    print("authors: ", authors)
    # returns the last name (heuristically) from a string in either <first> <last> or <last>, <first> format
    def get_last_name(author):
        # NOTE(Alin): For now, we're restrict ourselves to simple names with A-Z letters only
        regex = re.compile('[^ a-zA-Z]')
        author = regex.sub('', author)
        #print('getting last name of author: ', author)

        if ',' in author:
            return author.split(',')[0]
        else:
            return author.split(' ')[-1]

    initials = ""
    # For single authors, use the first three letters of their last name
    # TODO(Alin): This won't work for Dutch authors with 'van' in their last name.
    # e.g., for 'van Damme', it will be either 'van' or 'Dam' but would be better to do 'vD' or something like that.
    if len(authors) == 1:
        last_name = get_last_name(authors[0])
        initials = last_name[0:3]
    # For <= 4 authors, we use 'ABCD99'
    else:
        for author in authors:
            # the author name format could be "<first> <last>" or "<last>, <first>"
            last_name = get_last_name(author)
            #print('last name of author', author, 'is', last_name)
            initials += last_name[0].upper()
    
    # If we had more than 4 authors, then we use 'ABC+99'
    if moreThanFour:
        initials += '+'

    return initials

def bibtex_to_bibdb(bibtex):
    """Parses the given BibTeX string into potentially multiple bibliography objects"""
    parser = bibtexparser.bparser.BibTexParser(interpolate_strings=True, common_strings=True)
    bibdb = bibtexparser.loads(bibtex, parser)
    return bibdb

def bibtex_to_bibent(bibtex):
    """Returns a bibliography object from a BibTeX string'"""
    return bibtex_to_bibdb(bibtex).entries[0]

def bibent_to_bibtex(bibent):
    """Returns a BibTeX string for the bibliography object'"""
    bibwriter = bibtexparser.bwriter.BibTexWriter()
    bibent_canonicalize(bibent['ID'], bibent, 0)

    return bibwriter.write(bibent_to_bibdb(bibent)).strip().strip('\n').strip('\r').strip('\t')

def bibpath_rename_ck(destbibfile, citation_key):
    bibent = bibent_from_file(destbibfile)
    bibent['ID'] = citation_key
    bibent_to_file(destbibfile, bibent)

def bibent_set_dateadded(bibent, timestr):
    if timestr == None:
        now = datetime.now()
        timestr = now.strftime("%Y-%m-%d %H:%M:%S")

    #print("Time:", nowstr)
    bibent['ckdateadded'] = timestr
 
# Add ckdateadded field to keep track of papers by date added
def bibpath_set_dateadded(destbibfile, timestr):
    bibent = bibent_from_file(destbibfile)
    bibent_set_dateadded(bibent, timestr)
    bibent_to_file(destbibfile, bibent)
