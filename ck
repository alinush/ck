#!/usr/bin/env python3

# NOTE: Alphabetical order please
from bibtexparser.bwriter import BibTexWriter
from bs4 import BeautifulSoup
from citationkeys.misc import *
from citationkeys.tags import *
from citationkeys.urlhandlers import *
from datetime import datetime
from fake_useragent import UserAgent
from http.cookiejar import CookieJar
from pprint import pprint
from urllib.parse import urlparse, urlunparse
from urllib.request import Request

# NOTE: Alphabetical order please
import appdirs
import bibtexparser
import bs4
import click
import configparser
import os
import pyperclip
import subprocess
import shutil
import sys
import traceback
import urllib

class AliasedGroup(click.Group):
    def get_command(self, ctx, cmd_name):
        rv = click.Group.get_command(self, ctx, cmd_name)
        if rv is not None:
            return rv

        matches = [x for x in self.list_commands(ctx)
                   if x.startswith(cmd_name)]

        if not matches:
            return None
        elif len(matches) == 1:
            return click.Group.get_command(self, ctx, matches[0])

        ctx.fail('Too many matches: %s' % ', '.join(sorted(matches)))

#@click.group(invoke_without_command=True)
@click.group(cls=AliasedGroup)
@click.option(
    '-c', '--config-file',
    default=os.path.join(appdirs.user_config_dir('ck'), 'ck.config'),
    help='Path to ck config file.'
    )
@click.option(
    '-v', '--verbose',
    count=True,
    help='Pass multiple times for extra detail.'
    )
@click.pass_context
def ck(ctx, config_file, verbose):
    if ctx.invoked_subcommand is None:
        click.echo('I was invoked without subcommand, listing bibliography...')
        notimplemented()
        click.echo('Call with --help for usage.')

    #click.echo("I am about to invoke '%s' subcommand" % ctx.invoked_subcommand)

    # read configuration
    if verbose > 0:
        print("Reading CK config file at", config_file)
    config = configparser.ConfigParser()
    with open(config_file, 'r') as f:
        config.read_file(f)

    if verbose > 1:
        print("Configuration sections:", config.sections())

    # set a context with various config params that we pass around to the subcommands
    ctx.ensure_object(dict)
    ctx.obj['verbosity']    = verbose
    ctx.obj['BibDir']       = config['default']['ck_bib_dir']
    ctx.obj['TagDir']       = config['default']['ck_tag_dir']
    ctx.obj['TextEditor']   = config['default']['ck_text_editor']
    ctx.obj['tags']         = find_tagged_pdfs(ctx.obj['TagDir'], verbose)

    # set command to open PDFs with
    if sys.platform.startswith('linux'):
        ctx.obj['ck_open'] = 'xdg-open'
    elif sys.platform == 'darwin':
        ctx.obj['ck_open'] = 'open'
    else:
        click.secho("ERROR: " + sys.platform + " is not supported", fg="red", err=True)
        sys.exit(1)

    # always do a sanity check before invoking the actual subcommand
    # TODO: figure out how to call this *after* (not before) the subcommand is invoked, so the user can actually see its output
    #ck_check(ctx.obj['BibDir'], ctx.obj['TagDir'], verbose)

@ck.command('check')
@click.pass_context
def ck_check_cmd(ctx):
    """Checks the BibDir and TagDir for integrity."""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']
    ck_tag_dir = ctx.obj['TagDir']

    ck_check(ck_bib_dir, ck_tag_dir, verbosity)

def ck_check(ck_bib_dir, ck_tag_dir, verbosity):
    # find PDFs without bib files (and viceversa)
    missing = {}
    missing['.pdf'] = []
    missing['.bib'] = []
    counterpart_ext = {}
    counterpart_ext['.pdf'] = '.bib'
    counterpart_ext['.bib'] = '.pdf'

    extensions = missing.keys()
    for ck in list_cks(ck_bib_dir):
        for ext in extensions:
            filepath = os.path.join(ck_bib_dir, ck + ext)

            if verbosity > 1:
                print("Checking", filepath)

            counterpart = os.path.join(ck_bib_dir, ck + counterpart_ext[ext])

            if not os.path.exists(counterpart):
                missing[counterpart_ext[ext]].append(ck)

    for ext in [ '.pdf', '.bib' ]:
        if len(missing[ext]) > 0:
            print("Papers with missing " + ext + " files:")
            print("------------------------------")

        missing[ext].sort()
        for f in missing[ext]:
            print(" - " + f)

        if len(missing[ext]) > 0:
            print()
        
    # make sure all .pdf extensions are lowercase in TagDir
    for relpath in os.listdir(ck_tag_dir):
        filepath = os.path.join(ck_tag_dir, relpath)
        ck, extOrig = os.path.splitext(relpath)
        
        ext = extOrig.lower()
        if ext != extOrig:
            print("WARNING:", filepath, "has uppercase", "." + extOrig, "extension in TagDir")
    
    # TODO: make sure symlinks are not broken in TagDir
    # TODO: make sure all .bib files have the right CK and have ckdateadded

@ck.command('add')
@click.argument('url', required=True, type=click.STRING)
@click.argument('citation_key', required=True, type=click.STRING)
@click.option(
    '-n', '--no-tag-prompt',
    is_flag=True,
    default=False,
    help='Does not prompt the user to tag the paper.'
    )
@click.option(
    '-c', '--no-rename-ck',
    is_flag=True,
    default=False,
    help='Does not rename the CK in the .bib file.'
    )
@click.pass_context
def ck_add_cmd(ctx, url, citation_key, no_tag_prompt, no_rename_ck):
    """Adds the paper to the library (.pdf and .bib file)."""

    # TODO: come up with CK automatically if not specified & make sure it's unique (unclear how to handle eprint version of the same paper)

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']
    ck_tag_dir = ctx.obj['TagDir']

    if verbosity > 0:
        print("Verbosity:", verbosity)

    now = datetime.now()
    nowstr = now.strftime("%Y-%m-%d %H:%M:%S")
    #print("Time:", nowstr)
    
    # Make sure paper doesn't exist in the library first
    # TODO: save to temp file, so you can first display abstract with author names and prompt the user for the "Citation Key" rather than giving it as an arg
    destpdffile = ck_to_pdf(ck_bib_dir, citation_key)
    destbibfile = ck_to_bib(ck_bib_dir, citation_key)

    if os.path.exists(destpdffile):
        click.secho("ERROR: " + destpdffile + " already exists. Pick a different citation key.", fg="red", err=True)
        sys.exit(1)
    
    if os.path.exists(destbibfile):
        click.secho("ERROR: " + destbibfile + " already exists. Pick a different citation key.", fg="red", err=True)
        sys.exit(1)

    parsed_url = urlparse(url)
    if verbosity > 0:
        print("Paper's URL:", parsed_url)

    # get domain of website and handle it accordingly
    handlers = dict()
    handlers["link.springer.com"] = springerlink_handler
    handlers["eprint.iacr.org"]   = iacreprint_handler
    handlers["dl.acm.org"]        = dlacm_handler
    # e.g., https://epubs.siam.org/doi/abs/10.1137/S0036144502417715
    handlers["epubs.siam.org"] = epubssiam_handler
    handlers["ieeexplore.ieee.org"] = ieeexplore_handler

    # TODO: Cornell arXiv. See https://arxiv.org/help/api/index.
    # TODO: Science direct

    no_index_html = dict()
    no_index_html["eprint.iacr.org"] = True

    domain = parsed_url.netloc
    if domain in handlers:
        cj = CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

        user_agent = UserAgent().random
        parser = "lxml"
        soup = None
        index_html = None
        # e.g., we never download the index page for IACR ePrint
        if domain not in no_index_html or no_index_html[domain] == False:
            index_html = get_url(opener, url, verbosity, user_agent)
            soup = BeautifulSoup(index_html, parser)

        handler = handlers[domain]
        # TODO: display abstract
        # TODO: if no CK specified, prompt the user for one
        handler(opener, soup, parsed_url, ck_bib_dir, destpdffile, destbibfile, parser, user_agent, verbosity)
    else:
        click.secho("ERROR: Cannot handle URLs from '" + domain + "' yet.", fg="red", err=True)
        sys.exit(1)

    if not no_rename_ck:
        # change the citation key in the .bib file to citation_key
        if verbosity > 0:
            print("Renaming CK to " + citation_key + " in " + destbibfile)

        with open(destbibfile) as bibf:
            # NOTE: Without this specially-created parser, the library fails parsing .bib files with 'month = jun' or 'month = sep' fields.
            parser = bibtexparser.bparser.BibTexParser(interpolate_strings=True, common_strings=True)
            bibtex = bibtexparser.load(bibf, parser)
        bibtex.entries[0]['ID'] = citation_key

        # add ckdateadded field to keep track of papers by date added
        bibtex.entries[0]['ckdateadded'] = nowstr

        bibwriter = BibTexWriter()
        with open(destbibfile, 'w') as bibf:
            canonicalize_bibtex(citation_key, bibtex, verbosity)
            bibf.write(bibwriter.write(bibtex))

    if not no_tag_prompt:
        # prompt user to tag paper
        print_all_tags(ck_tag_dir)
        print()
        tags = prompt_for_tags("Please enter tag(s) for '" + citation_key + "': ")
        for tag in tags:
            tag_paper(ck_tag_dir, ck_bib_dir, citation_key, tag)

@ck.command('config')
@click.pass_context
def ck_config_cmd(ctx):
    """Lets you edit the config file and prints it at the end."""

    ctx.ensure_object(dict)
    ck_text_editor = ctx.obj['TextEditor']

    fullpath = os.path.join(appdirs.user_config_dir('ck'), 'ck.config')
    os.system(ck_text_editor + " \"" + fullpath + "\"")
    if os.path.exists(fullpath):
        print(file_to_string(fullpath).strip())

@ck.command('queue')
@click.argument('citation_key', required=False, type=click.STRING)
@click.pass_context
def ck_queue_cmd(ctx, citation_key):
    """Marks this paper as 'to-be-read', removing the 'queue/reading' and/or 'queue/finished' tags"""
    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']
    ck_tag_dir = ctx.obj['TagDir']

    if citation_key is not None:
        ctx.invoke(ck_tags_cmd, citation_key=citation_key, tags="queue/to-read")
        ctx.invoke(ck_untag_cmd, citation_key=citation_key, tags="queue/finished,queue/reading")
    else:
        click.secho("Papers that remain to be read:", bold=True)
        click.echo()

        ctx.invoke(ck_list_cmd, pathnames=[os.path.join(ck_tag_dir, 'queue/to-read')])

@ck.command('read')
@click.argument('citation_key', required=False, type=click.STRING)
@click.pass_context
def ck_read_cmd(ctx, citation_key):
    """Marks this paper as in the process of 'reading', removing the 'queue/to-read' and/or 'queue/finished' tags"""
    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']
    ck_tag_dir = ctx.obj['TagDir']

    if citation_key is not None:
        ctx.invoke(ck_untag_cmd, citation_key=citation_key, tags="queue/to-read,queue/finished")
        ctx.invoke(ck_tags_cmd, citation_key=citation_key, tags="queue/reading")
        ctx.invoke(ck_open_cmd, filename=citation_key + ".pdf")
    else:
        click.secho("Papers you are currently reading:", bold=True)
        click.echo()

        ctx.invoke(ck_list_cmd, pathnames=[os.path.join(ck_tag_dir, 'queue/reading')])

@ck.command('finished')
@click.argument('citation_key', required=False, type=click.STRING)
@click.pass_context
def ck_finished_cmd(ctx, citation_key):
    """Marks this paper as 'finished reading', removing the 'queue/to-read' and/or 'queue/reading' tags"""
    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']
    ck_tag_dir = ctx.obj['TagDir']

    if citation_key is not None:
        ctx.invoke(ck_untag_cmd, citation_key=citation_key, tags="queue/to-read,queue/reading")
        ctx.invoke(ck_tags_cmd, citation_key=citation_key, tags="queue/finished")
    else:
        click.secho("Papers you have finished reading:", bold=True)
        click.echo()

        ctx.invoke(ck_list_cmd, pathnames=[os.path.join(ck_tag_dir, 'queue/finished')])

@ck.command('untag')
@click.option(
    '-f', '--force',
    is_flag=True,
    default=False,
    help='Do not prompt for confirmation when removing all tags')
@click.argument('citation_key', required=False, type=click.STRING)
@click.argument('tags', required=False, type=click.STRING)
@click.pass_context
def ck_untag_cmd(ctx, force, citation_key, tags):
    """Untags the specified paper."""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']
    ck_tag_dir = ctx.obj['TagDir']
    ck_tags    = ctx.obj['tags']
        
    if citation_key is None and tags is None:
        # If no paper was specified, detects untagged papers and asks the user to tag them.
        untagged_pdfs = find_untagged_pdfs(ck_bib_dir, ck_tag_dir, list_cks(ck_bib_dir), ck_tags.keys(), verbosity)
        if len(untagged_pdfs) > 0:
            sys.stdout.write("Untagged papers: ")
            first_iter = True
            for (filepath, citation_key) in sorted(untagged_pdfs):
                if not first_iter:
                    sys.stdout.write(", ")
                sys.stdout.write(citation_key)
                sys.stdout.flush()

                first_iter = False
            sys.stdout.write("\b\b")
            print('\n')

            for (filepath, citation_key) in untagged_pdfs:
                ctx.invoke(ck_bib_cmd, citation_key=citation_key, clipboard=False)

                print_all_tags(ck_tag_dir)
                print()
                tags = prompt_for_tags("Please enter tag(s) for '" + citation_key + "': ")
                for tag in tags:
                    tag_paper(ck_tag_dir, ck_bib_dir, citation_key, tag)
        else:
            print("No untagged papers.")
    else:
        if tags is not None:
            tags = parse_tags(tags)
            for tag in tags:
                if untag_paper(ck_tag_dir, citation_key, tag):
                    click.secho("Removed '" + tag + "' tag", fg="green")
                else:
                    click.secho("Not tagged with '" + tag + "' tag", fg="red", err=True)
        else:
            if force or click.confirm("Are you sure you want to remove ALL tags for " + click.style(citation_key, fg="blue") + "?"):
                if untag_paper(ck_tag_dir, citation_key):
                    click.secho("Removed all tags!", fg="green")
                else:
                    click.secho("No tags to remove.", fg="red")

@ck.command('tags')
@click.argument('citation_key', required=False, type=click.STRING)
@click.argument('tags', required=False, type=click.STRING)
@click.pass_context
def ck_tags_cmd(ctx, citation_key, tags):
    """Tags the specified paper or lists its tags"""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']
    ck_tag_dir = ctx.obj['TagDir']
    ck_tags    = ctx.obj['tags']

    if tags is None:
        if citation_key is None:
            print_all_tags(ck_tag_dir)
        else:
            print_tags(ck_tags[citation_key])
    else:
        if not os.path.exists(ck_to_pdf(ck_bib_dir, citation_key)):
            click.secho("ERROR: " + citation_key + " has no PDF file", fg="red", err=True)
            sys.exit(1)

        tags = parse_tags(tags)

        for tag in tags:
            if tag_paper(ck_tag_dir, ck_bib_dir, citation_key, tag):
                click.secho("Added '" + tag + "' tag", fg="green")
            else:
                click.secho("ERROR: " + citation_key + " already has '" + tag + "' tag", fg="red", err=True)

@ck.command('rm')
@click.option(
    '-f', '--force',
    is_flag=True,
    default=False,
    help='Do not prompt for confirmation before deleting'
    )
@click.argument('citation_key', required=True, type=click.STRING)
@click.pass_context
def ck_rm_cmd(ctx, force, citation_key):
    """Removes the paper from the library (.pdf and .bib file). Can provide citation key or filename with .pdf or .bib extension."""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']
    ck_tag_dir = ctx.obj['TagDir']
    
    # allow user to provide file name directly (or citation key to delete everything)
    basename, extension = os.path.splitext(citation_key)

    if len(extension.strip()) > 0:
        files = [ os.path.join(ck_bib_dir, citation_key) ]
    else:
        files = [ ck_to_pdf(ck_bib_dir, citation_key), ck_to_bib(ck_bib_dir, citation_key) ]

    something_to_del = False
    for f in files:
        if os.path.exists(f):
            something_to_del = True

    if force or something_to_del:
        if not force:
            if not confirm_user("Are you sure you want to delete '" + citation_key + "' from the library?"):
                click.echo("Okay, not deleting anything.")
                return

        for f in files:
            if os.path.exists(f):
                os.remove(f)
                click.secho("Deleted " + f, fg="green")
            else:
                click.secho("WARNING: " + f + " does not exist, nothing to delete...", fg="red", err=True)

        # untag the paper
        untag_paper(ck_tag_dir, citation_key)
    else:
        click.echo(citation_key + " is not in library. Nothing to delete.")

@ck.command('open')
@click.argument('filename', required=True, type=click.STRING)
@click.pass_context
def ck_open_cmd(ctx, filename):
    """Opens the .pdf or .bib file."""

    ctx.ensure_object(dict)
    verbosity      = ctx.obj['verbosity']
    ck_bib_dir     = ctx.obj['BibDir']
    ck_tag_dir     = ctx.obj['TagDir']
    ck_open        = ctx.obj['ck_open']
    ck_text_editor = ctx.obj['TextEditor']
    ck_tags        = ctx.obj['tags']

    basename, extension = os.path.splitext(filename)

    if len(extension.strip()) == 0:
        filename = basename + ".pdf"
        extension = '.pdf'
        
    fullpath = os.path.join(ck_bib_dir, filename)

    print_tags(ck_tags[basename])

    if extension.lower() == '.pdf':
        if os.path.exists(fullpath) is False:
            click.secho("ERROR: " + basename + " paper is NOT in the library as a PDF", fg="red", err=True)
            sys.exit(1)

        # not interested in output
        completed = subprocess.run(
            [ck_open, fullpath],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # TODO: check for failure in completed.returncode
    elif extension.lower() == '.bib':
        os.system(ck_text_editor + " " + fullpath)
        if os.path.exists(fullpath):
            print(file_to_string(fullpath).strip())

            # warn if bib file is missing 'ckdateadded' field
            with open(fullpath) as bibf:
                # NOTE: Without this specially-created parser, the library fails parsing .bib files with 'month = jun' or 'month = sep' fields.
                parser = bibtexparser.bparser.BibTexParser(interpolate_strings=True, common_strings=True)
                bibtex = bibtexparser.load(bibf, parser)

            if 'ckdateadded' not in bibtex.entries[0]:
                now = datetime.now()
                nowstr = now.strftime("%Y-%m-%d %H:%M:%S")

                if confirm_user("\nWARNING: BibTeX is missing 'ckdateadded'. Would you like to set it to the current time?"):
                    # add ckdateadded field to keep track of papers by date added 
                    bibtex.entries[0]['ckdateadded'] = nowstr

                    # write back the .bib file
                    bibwriter = BibTexWriter()
                    with open(fullpath, 'w') as bibf:
                        canonicalize_bibtex(basename, bibtex, verbosity)
                        bibf.write(bibwriter.write(bibtex))

    elif extension.lower() == '.md':
        # NOTE: Need to cd to the directory first so vim picks up the .vimrc there
        os.system('cd "' + ck_bib_dir + '" && ' + ck_text_editor + ' "' + filename + '"')
    elif extension.lower() == '.html':
        if os.path.exists(fullpath) is False:
            click.secho("ERROR: No HTML notes in the library for '" + basename + "'", fg="red", err=True)
            sys.exit(1)

        completed = subprocess.run(
            [ck_open, fullpath],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        click.secho("ERROR: " + extension.lower() + " extension is not supported", fg="red", err=True)
        sys.exit(1)

@ck.command('bib')
@click.argument('citation_key', required=True, type=click.STRING)
@click.option(
    '--clipboard/--no-clipboard',
    default=True,
    help='To (not) copy the BibTeX to clipboard.'
    )
@click.option(
    '-m', '--markdown',
    is_flag=True,
    default=False,
    help='Output as a Markdown citation'
    )
@click.pass_context
def ck_bib_cmd(ctx, citation_key, clipboard, markdown):
    """Prints the paper's BibTeX and copies it to the clipboard."""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']

    # TODO: maybe add args for isolating author/title/year/etc

    path = os.path.join(ck_bib_dir, citation_key + '.bib')
    if os.path.exists(path) is False:
        if confirm_user(citation_key + " has no .bib file. Would you like to create it?"):
            ctx.invoke(ck_open_cmd, filename=citation_key + ".bib")

        sys.exit(1)

    if markdown == False:
        print()
        print("BibTeX for '%s'" % path)
        print()
        bibtex = file_to_string(path).strip()
        to_copy = bibtex
        print()
    else:
        try:
            with open(path) as bibf:
                parser = bibtexparser.bparser.BibTexParser(interpolate_strings=True, common_strings=True)
                bibtex = bibtexparser.load(bibf, parser)

            assert len(bibtex.entries) == 1
        except FileNotFoundError:
            print(citation_key + ":", "Missing BibTeX file in directory", ck_bib_dir)
        except:
            print(citation_key + ":", "Unexpected error")

        # TODO: check if it has a URL
        bib = bibtex.entries[0]
        title = bib['title'].strip("{}")
        authors = bib['author']
        authors = authors.replace("{", "")
        authors = authors.replace("}", "")
        citation_key_noplus = citation_key.replace("+", "plus") # beautiful-jekyll is not that beautiful and doesn't like '+' in footnote names
        to_copy = "[^" + citation_key_noplus + "]: **" + title + "**, by " + authors

        if 'booktitle' in bib:
            venue = bib['booktitle']
        elif 'journal' in bib:
            venue = bib['journal']
        elif 'howpublished' in bib:
            venue = bib['howpublished']
        else:
            venue = None

        if venue != None:
            to_copy = to_copy + ", *in " + venue + "*"

        year = bib['year']
        to_copy = to_copy +  ", " + year

    print(to_copy)

    if clipboard:
        pyperclip.copy(to_copy)
        click.echo("\nCopied to clipboard!\n")

@ck.command('rename')
@click.argument('old_citation_key', required=True, type=click.STRING)
@click.argument('new_citation_key', required=True, type=click.STRING)
@click.pass_context
def ck_rename_cmd(ctx, old_citation_key, new_citation_key):
    """Renames a paper's .pdf and .bib file with a new citation key. Updates its .bib file and all symlinks to it in the TagDir."""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']

    # TODO: make sure new_citation_key does not exist
    # TODO: rename in ck_bib_dir
    # TODO: update .bib file citation key
    # TODO: update all symlinks in by-tags/
    notimplemented()

@ck.command('search')
@click.argument('query', required=True, type=click.STRING)
@click.option(
    '-c', '--case-sensitive',
    is_flag=True,
    default=False,
    help='Enables case-sensitive search.'
    )
@click.pass_context
def ck_search_cmd(ctx, query, case_sensitive):
    """Searches all .bib files for the specified text."""

    ctx.ensure_object(dict)
    verbosity   = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']
    ck_tags    = ctx.obj['tags']

    cks = set()
    for relpath in os.listdir(ck_bib_dir):
        filepath = os.path.join(ck_bib_dir, relpath)
        filename, extension = os.path.splitext(relpath)
        #filename = os.path.basename(filepath)

        if extension.lower() == ".bib":
            origBibtex = file_to_string(filepath)

            if case_sensitive is False:
                bibtex = origBibtex.lower()
                query = query.lower()

                if query in bibtex:
                    cks.add(filename)

    if len(cks) > 0:
        print_ck_tuples(cks_to_tuples(ck_bib_dir, cks, verbosity), ck_tags)
    else:
        print("No matches!")

@ck.command('cleanbib')
@click.pass_context
def ck_cleanbib_cmd(ctx):
    """Command to clean up the .bib files a little. (Temporary, until I write something better.)"""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']
    ck_tag_dir = os.path.normpath(os.path.realpath(ctx.obj['TagDir']))

    cks = list_cks(ck_bib_dir)

    for ck in cks:
        bibfile = os.path.join(ck_bib_dir, ck + ".bib")
        if verbosity > 1:
            print("Parsing BibTeX for " + ck)
        try:
            with open(bibfile) as bibf:
                parser = bibtexparser.bparser.BibTexParser(interpolate_strings=True, common_strings=True)
                bibtex = bibtexparser.load(bibf, parser)

            assert len(bibtex.entries) == 1
            assert type(ck) == str
            updated = canonicalize_bibtex(ck, bibtex, verbosity)

            if updated:
                print("Updating " + bibfile)
                bibwriter = BibTexWriter()
                with open(bibfile, 'w') as bibf:
                    bibf.write(bibwriter.write(bibtex))
            else:
                if verbosity > 0:
                    print("Nothing to update in " + bibfile)

        except FileNotFoundError:
            print(ck + ":", "Missing BibTeX file in directory", ck_bib_dir)
        except:
            print(ck + ":", "Unexpected error") 
            traceback.print_exc()

@ck.command('list')
#@click.argument('directory', required=False, type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True))
@click.argument('pathnames', nargs=-1, type=click.Path(exists=True, file_okay=True, dir_okay=True, resolve_path=True))
@click.pass_context
def ck_list_cmd(ctx, pathnames):
    """Lists all citation keys in the library"""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']
    ck_tag_dir = os.path.normpath(os.path.realpath(ctx.obj['TagDir']))
    ck_tags    = ctx.obj['tags']

    cks = cks_from_paths(ck_bib_dir, ck_tag_dir, pathnames)

    if verbosity > 0:
        print(cks)

    ck_tuples = cks_to_tuples(ck_bib_dir, cks, verbosity)

    sorted_cks = sorted(ck_tuples, key=lambda item: item[4])

    print_ck_tuples(sorted_cks, ck_tags)

    print()
    print(str(len(cks)) + " PDFs listed")

    # TODO: query could be a space-separated list of tokens
    # a token can be a hashtag (e.g., #dkg-dlog) or a sorting token (e.g., 'year')
    # For example: 
    #  $ ck l #dkg-dlog year title
    # would list all papers with tag #dkg-dlog and sort them by year and then by title
    # TODO: could have AND / OR operators for hashtags
    # TODO: filter by year/author/title/conference

@ck.command('genbib')
@click.argument('output-bibtex-file', required=True, type=click.File('w'))
@click.argument('pathnames', nargs=-1, type=click.Path(exists=True, file_okay=True, dir_okay=True, resolve_path=True))
@click.pass_context
def ck_genbib(ctx, output_bibtex_file, pathnames):
    """Generates a master bibliography file of all papers."""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']
    ck_tag_dir = ctx.obj['TagDir']

    cks = cks_from_paths(ck_bib_dir, ck_tag_dir, pathnames)

    num = 0
    sortedcks = sorted(cks)
    for ck in sortedcks:
        bibfilepath = os.path.join(ck_bib_dir, ck + ".bib")
        #pdffilepath = os.path.join(ck_bib_dir, ck + ".pdf")

        if os.path.exists(bibfilepath):
            num += 1
            bibtex = file_to_string(bibfilepath)
            output_bibtex_file.write(bibtex + '\n')

    if num == 0:
        print("No .bib files in specified directories.")
    else:
        print("Wrote", num, ".bib files to", output_bibtex_file.name)

@ck.command('copypdfs')
@click.argument('output-dir', required=True, type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True))
@click.argument('pathnames', nargs=-1, type=click.Path(exists=True, file_okay=True, dir_okay=True, resolve_path=True))
@click.pass_context
def ck_copypdfs(ctx, output_dir, pathnames):
    """Copies all PDFs from the specified directories into the output directory."""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']
    ck_tag_dir = ctx.obj['TagDir']

    cks = cks_from_paths(ck_bib_dir, ck_tag_dir, pathnames)

    num = 0
    sortedcks = sorted(cks)
    for ck in sortedcks:
        pdffilepath = os.path.join(ck_bib_dir, ck + ".pdf")

        if os.path.exists(pdffilepath):
            num += 1
            shutil.copy2(pdffilepath, output_dir)

    if num == 0:
        print("No .pdf files in specified directories.")
    else:
        print("Copied", num, ".pdf files to", output_dir)

if __name__ == '__main__':
    ck(obj={})

