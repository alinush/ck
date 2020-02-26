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

def string_to_file(string, path):
    with open(path, 'w') as output:
        output.write(string)

def ck_to_pdf(ck_bib_dir, ck):
    return os.path.join(ck_bib_dir, ck + ".pdf")

def ck_to_bib(ck_bib_dir, ck):
    return os.path.join(ck_bib_dir, ck + ".bib")

# for now, a CK 'existing' means it has a PDF file in the BibDir
def ck_exists(ck_bib_dir, ck):
    path = ck_to_pdf(ck_bib_dir, ck)
    return os.path.exists(path)

# useful for commands like 'ck list' and 'ck genbib'
# 1. When no path is given
#   1.1. if in TagDir, list CKs in all subdirs
#   1.2. if not in TagDir, list *all* CKs in BibDir
# 2. When paths are given, list CKs in all those paths
def cks_from_paths(ck_bib_dir, ck_tag_dir, pathnames):
    if len(pathnames) > 0:
        cks = set()
        for path in pathnames:
            if os.path.isdir(path):
                cks.update(list_cks(path))
            else:
                filename = os.path.basename(path)
                ck, ext = os.path.splitext(filename)
                cks.add(ck)
    else:
        # When listing with 'ck l', we have to figure out if the CWD is somewhere in the TagDir
        # and if so, only list the CKs there. Otherwise, we list all CKs in the BibDir.
        cwd = os.path.normpath(os.getcwd())
        common_prefix = os.path.commonpath([ck_tag_dir, cwd])
        is_in_tag_dir = (common_prefix == ck_tag_dir)

        #print("CWD:               ", cwd)
        #print("Tag dir:           ", ck_tag_dir)
        #print("Is CWD in tag dir? ", is_in_tag_dir)
        #print()

        if is_in_tag_dir:
            paper_dir=cwd
        else:
            paper_dir=ck_bib_dir

        # Then, we can list the papers by tags below.
        cks = list_cks(paper_dir)

    return cks

# TODO: Take flags that decide what to print. For now, "title, authors, year"
def cks_to_tuples(ck_bib_dir, cks, verbosity):
    ck_tuples = []

    for ck in cks:
        bibfile = os.path.join(ck_bib_dir, ck + ".bib")
        if verbosity > 1:
            click.echo("Parsing BibTeX for " + ck)

        try:
            with open(bibfile) as bibf:
                parser = bibtexparser.bparser.BibTexParser(interpolate_strings=True, common_strings=True)
                bibtex = bibtexparser.load(bibf, parser)

            #print(bibtex.entries)
            #print("Comments: ")
            #print(bibtex.comments)
            bib = bibtex.entries[0]

            # make sure the CK in the .bib matches the filename
            bck = bib['ID']
            if bck != ck:
                click.echo("\nWARNING: Expected '" + ck + "' CK in " + ck + ".bib file (got '" + bck + "')\n", err=True)

            author = bib['author'].replace('\r', '').replace('\n', ' ').strip()
            title  = bib['title'].strip("{}")
            year   = bib['year']
            date   = bib['ckdateadded'] if 'ckdateadded' in bib else ''

            ck_tuples.append((ck, author, title, year, date))

        except FileNotFoundError:
            click.secho(ck + ": Missing BibTeX file in directory " + ck_bib_dir, fg="red", err=True)
        except:
            click.secho(ck + ": Unexpected error", fg="red", err=True)
            traceback.print_exc()
            raise

    return ck_tuples

def print_ck_tuples(cks, tags):
    for (ck, author, title, year, date) in cks:
        click.secho(ck, fg='blue', nl=False)
        click.echo(", ", nl=False)
        click.secho(title, fg='green', nl=False)
        click.echo(", ", nl=False)
        click.secho(year,fg='red', bold=True, nl=False)
        click.echo(", ", nl=False)
        click.echo(author, nl=False)
        if date:
            date = datetime.strftime(datetime.strptime(date, "%Y-%m-%d %H:%M:%S"), "%B %-d, %Y")
            click.echo(', (', nl=False)
            click.secho(date, fg='magenta', nl=False)
            click.echo(')', nl=False)

        if ck in tags:
            click.echo(', ', nl=False)
            click.echo(style_tags(tags[ck]), nl=False)
        click.echo()

        #print(ck + ": " + title + " by " + author + ", " + year + date)

# NOTE: This can be called on the bibdir or on the tagdir and it proceeds recursively
def list_cks(ck_bib_dir):
    cks = set()

    for filename in sorted(os.listdir(ck_bib_dir)):
        fullpath = os.path.join(ck_bib_dir, filename)

        if os.path.isdir(fullpath):
            cks.update(list_cks(fullpath))
        else:
            ck, ext = os.path.splitext(filename)

            # e.g., CMT12.pdf might have CMT12.slides.pdf next to it
            if '.' in ck:
                continue

            if ext.lower() == ".pdf" or ext.lower() == ".bib":
                cks.add(ck)

    return sorted(cks)

def style_ck(ck):
    return click.style(ck, fg="blue")
