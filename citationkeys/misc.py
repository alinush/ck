#!/usr/bin/env python3

import os
import readline
import sys
import traceback
from collections import defaultdict
from datetime import datetime

import bibtexparser
import click

from .bib import bibent_get_url, bibent_get_venue, new_bibtex_parser
from .tags import style_tags, SimpleCompleter
from .print import print_error

def get_terminal_width():
    rows, columns = os.popen('stty size', 'r').read().split()
    return columns

def notimplemented():
    print()
    print("ERROR: Not implemented yet. Exiting...")
    print()
    sys.exit(0)

def file_to_string(path):
    with open(path, 'r') as f:
        data = f.read()

    return data

def file_to_bytes(path):
    with open(path, 'rb') as f:
        data = f.read()

    return data

def string_to_file(string, path):
    with open(path, 'w') as output:
        output.write(string)

# Prompts the user for a citation key, autocompleting with the current ones (can be used to detect conflicts)
def prompt_for_ck(ctx, prompt):
    readline.set_completer(SimpleCompleter(list_cks(ctx.obj['BibDir'], True), ',').complete)

    readline.parse_and_bind('tab: complete')

    ck = ""
    while len(ck.strip()) == 0:
        ck = input(prompt)

    return ck

def ck_to_pdf(ck_bib_dir, ck):
    if ck == None or len(ck) == 0:
        raise ValueError("Cannot derive PDF file path from empty citation key")

    return os.path.join(ck_bib_dir, ck + ".pdf")

def ck_to_bib(ck_bib_dir, ck):
    if ck == None or len(ck) == 0:
        raise ValueError("Cannot derive BibTeX file path from empty citation key")

    return os.path.join(ck_bib_dir, ck + ".bib")

# for now, a CK 'existing' means it has either a .bib or PDF file in the BibDir
def ck_exists(ck_bib_dir, ck):
    pdfpath = ck_to_pdf(ck_bib_dir, ck)
    bibpath = ck_to_bib(ck_bib_dir, ck)
    return os.path.exists(pdfpath) or os.path.exists(bibpath)

def is_cwd_in_tagdir(ck_tag_dir):
    cwd = os.path.normpath(os.getcwd())
    common_prefix = os.path.commonpath([ck_tag_dir, cwd])
    return common_prefix == ck_tag_dir

# Given a list of tags, returns all citation keys with those tags.
# If recursive is False, then does not include citation keys that are indirectly tagged.
# For example, if the tag is #accumulators, and we have a CK tagged only with #accumulators/merkle
# and not with #accumulators, then this CK will not be included when recursive=False.
def cks_from_tags(ck_tag_dir, tags, recursive=True):
    cks = set()
    for tag in tags:
        path = ck_tag_dir + '/' + tag
        if os.path.isdir(path):
            cks.update(list_cks(path, recursive))
        else:
            print_error(style_tags([tag]) + " does not exist as a tag")
    return cks

# TODO(Alin): Take flags that decide what to print. For now, "title, authors, year"
def cks_to_tuples(ck_bib_dir, cks, verbosity):
    ck_tuples = []

    for ck in cks:
        bibfile = os.path.join(ck_bib_dir, ck + ".bib")
        if verbosity > 1:
            click.echo("Parsing BibTeX for " + ck)

        try:
            with open(bibfile) as bibf:
                bibtex = bibtexparser.load(bibf, new_bibtex_parser())

            #print(bibtex.entries)
            #print("Comments: ")
            #print(bibtex.comments)
            bib = defaultdict(lambda: '', bibtex.entries[0])

            # make sure the CK in the .bib matches the filename
            bck = bib['ID']
            if bck != ck:
                click.echo("\nWARNING: Expected '" + ck + "' CK in " + ck + ".bib file (got '" + bck + "')\n", err=True)

            author = bib['author'].replace('\r', '').replace('\n', ' ').strip()
            title  = bib['title'].strip("{}")
            year   = bib['year']
            date   = bib['ckdateadded'] if 'ckdateadded' in bib else ''
            url    = bibent_get_url(bib)
            venue  = bibent_get_venue(bib)

            ck_tuples.append((ck, author, title, year, date, url, venue))

        except FileNotFoundError:
            click.secho(ck + ": Missing BibTeX file in directory " + ck_bib_dir, fg="red", err=True)
        except:
            click.secho(ck + ": Unexpected error", fg="red", err=True)
            traceback.print_exc()
            raise

    return ck_tuples

def print_ck_tuples(cks, tags, include_url=False, include_venue=True, include_ck=True, include_dateadded=True, include_tags=True):
    for (ck, author, title, year, date, url, venue) in cks:
        if include_ck:
            click.secho(ck, fg='blue', nl=False)
            click.echo(", ", nl=False)

        click.secho(title, fg='green', nl=False)

        click.echo(", ", nl=False)
        click.secho(year,fg='red', bold=True, nl=False)

        click.echo(", ", nl=False)
        click.echo(author, nl=False)

        if date and include_dateadded:
            date = datetime.strftime(datetime.strptime(date, "%Y-%m-%d %H:%M:%S"), "%B %-d, %Y")
            click.echo(", ", nl=False)
            click.echo('(', nl=False)
            click.secho(date, fg='magenta', nl=False)
            click.echo(')', nl=False)

        if include_tags and ck in tags:
            click.echo(', ', nl=False)
            click.echo(style_tags(tags[ck]), nl=False)

        if include_venue and venue is not None:
            click.echo(', ', nl=False)
            click.secho(venue, fg='cyan', nl=False)

        if include_url and url is not None:
            click.echo(', ', nl=False)
            click.echo(url, nl=False)
        click.echo()

        #print(ck + ": " + title + " by " + author + ", " + year + date)

# NOTE: This can be called on the bibdir or on the tagdir and it proceeds recursively
def list_cks(some_dir, recursive):
    cks = set()

    for filename in sorted(os.listdir(some_dir)):
        fullpath = os.path.join(some_dir, filename)

        if recursive and os.path.isdir(fullpath):
            cks.update(list_cks(fullpath, recursive))
        else:
            ck, ext = os.path.splitext(filename)

            # e.g., CMT12.pdf might have CMT12.slides.pdf next to it
            if '.' in ck:
                continue

            if ext.lower() == ".pdf" or ext.lower() == ".bib":
                cks.add(ck)

    return sorted(cks)
