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

def prompt_user(prompt):
    sys.stdout.write(prompt)
    sys.stdout.flush()
    answer = sys.stdin.readline().strip()
    return answer

def confirm_user(prompt):
    prompt += " [y/N]: "
    ans = prompt_user(prompt).strip()
    return ans.lower() == "y" or ans.lower() == "yes"

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
        if title[0] != "{" and title[len(title)-1] != "}":
            title = "{" + title + "}"
        if bib['title'] != title:
            if verbosity > 1:
                print(ck + ": Added brackets to title: " + title)
            bib['title'] = title
            updated = True

    assert type(bib['ID']) == str

    return updated
