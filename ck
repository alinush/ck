#!/usr/bin/env python3

# NOTE: Alphabetical order please
from bibtexparser.bwriter import BibTexWriter
from bs4 import BeautifulSoup
from citationkeys.misc import *
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
    ctx.obj['verbosity']        = verbose
    ctx.obj['ck_bib_dir']       = config['default']['ck_bib_dir']
    ctx.obj['ck_tag_dir']       = config['default']['ck_tag_dir']
    ctx.obj['ck_text_editor']   = config['default']['ck_text_editor']

    # set command to open PDFs with
    if sys.platform.startswith('linux'):
        ctx.obj['ck_open'] = 'xdg-open'
    elif sys.platform == 'darwin':
        ctx.obj['ck_open'] = 'open'
    else:
        print("ERROR:", sys.platform, "is not supported")
        sys.exit(1)

    # always do a sanity check before invoking the actual subcommand
    # TODO: figure out how to call this *after* (not before) the subcommand is invoked, so the user can actually see its output
    #ck_check(ctx.obj['ck_bib_dir'], ctx.obj['ck_tag_dir'], verbose)

@ck.command('check')
@click.pass_context
def ck_check_cmd(ctx):
    """Checks the BibDir and TagDir for integrity."""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['ck_bib_dir']
    ck_tag_dir = ctx.obj['ck_tag_dir']

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
    ck_bib_dir = ctx.obj['ck_bib_dir']

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
        print("ERROR:", destpdffile, "already exists. Pick a different citation key.")
        sys.exit(1)
    
    if os.path.exists(destbibfile):
        print("ERROR:", destbibfile, "already exists. Pick a different citation key.")
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
        print("ERROR: Cannot handle URLs from", domain, "yet.")
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
        ctx.invoke(ck_tag_cmd, citation_key=citation_key)

@ck.command('config')
@click.pass_context
def ck_config_cmd(ctx):
    """Lets you edit the config file and prints it at the end."""

    ctx.ensure_object(dict)
    ck_text_editor = ctx.obj['ck_text_editor'];

    fullpath = os.path.join(appdirs.user_config_dir('ck'), 'ck.config')
    os.system(ck_text_editor + " \"" + fullpath + "\"");
    if os.path.exists(fullpath):
        print(file_to_string(fullpath).strip())

@ck.command('queue')
@click.argument('citation_key', required=False, type=click.STRING)
@click.pass_context
def ck_queue_cmd(ctx, citation_key):
    """Marks this paper as 'to-be-read', removing the 'queue/reading' and/or 'queue/finished' tags"""
    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['ck_bib_dir']
    ck_tag_dir = ctx.obj['ck_tag_dir']

    if citation_key is not None:
        ctx.invoke(ck_tag_cmd, citation_key=citation_key, tag="queue/to-read")
        ctx.invoke(ck_untag_cmd, citation_key=citation_key, tags="queue/finished,queue/reading")
    else:
        click.echo(click.style("Papers that remain to be read:", bold=True))
        click.echo()

        ctx.invoke(ck_list_cmd, pathnames=[os.path.join(ck_tag_dir, 'queue/to-read')])

@ck.command('read')
@click.argument('citation_key', required=False, type=click.STRING)
@click.pass_context
def ck_read_cmd(ctx, citation_key):
    """Marks this paper as in the process of 'reading', removing the 'queue/to-read' and/or 'queue/finished' tags"""
    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['ck_bib_dir']
    ck_tag_dir = ctx.obj['ck_tag_dir']

    if citation_key is not None:
        ctx.invoke(ck_untag_cmd, citation_key=citation_key, tags="queue/to-read,queue/finished")
        ctx.invoke(ck_tag_cmd, citation_key=citation_key, tag="queue/reading")
        ctx.invoke(ck_open_cmd, filename=citation_key + ".pdf")
    else:
        click.echo(click.style("Papers you are currently reading:", bold=True))
        click.echo()

        ctx.invoke(ck_list_cmd, pathnames=[os.path.join(ck_tag_dir, 'queue/reading')])

@ck.command('finished')
@click.argument('citation_key', required=False, type=click.STRING)
@click.pass_context
def ck_finished_cmd(ctx, citation_key):
    """Marks this paper as 'finished reading', removing the 'queue/to-read' and/or 'queue/reading' tags"""
    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['ck_bib_dir']
    ck_tag_dir = ctx.obj['ck_tag_dir']

    if citation_key is not None:
        ctx.invoke(ck_untag_cmd, citation_key=citation_key, tags="queue/to-read,queue/reading")
        ctx.invoke(ck_tag_cmd, citation_key=citation_key, tag="queue/finished")
    else:
        click.echo(click.style("Papers you have finished reading:", bold=True))
        click.echo()

        ctx.invoke(ck_list_cmd, pathnames=[os.path.join(ck_tag_dir, 'queue/finished')])

@ck.command('untag')
@click.argument('citation_key', required=True, type=click.STRING)
@click.argument('tags', required=True, type=click.STRING)
@click.pass_context
def ck_untag_cmd(ctx, citation_key, tags):
    """Untags the specified paper."""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['ck_bib_dir']
    ck_tag_dir = ctx.obj['ck_tag_dir']

    tags = parse_tags(tags)
    for tag in tags:
        if untag_paper(ck_tag_dir, citation_key, tag):
            click.echo(click.style("Removed '" + tag + "' tag", fg="green")) 
        else:
            if verbosity > 0:
                click.echo(click.style("WARNING: " + citation_key + " is not tagged with '" + tag + "' tag", fg="red"), err=True) 

@ck.command('tag')
@click.argument('citation_key', required=False, type=click.STRING)
@click.argument('tag', required=False, type=click.STRING)
@click.option(
    '-l', '--list', 'list_opt',
    default=False,
    is_flag=True,
    help='Lists all the tags in the library.')
@click.pass_context
def ck_tag_cmd(ctx, citation_key, tag, list_opt):
    """Tags the specified paper."""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['ck_bib_dir']
    ck_tag_dir = ctx.obj['ck_tag_dir']

    if list_opt is True:
        print_tags(ck_tag_dir)
        sys.exit(0)

    if citation_key is None:
        # If no paper was specified, detects untagged papers and asks the user to tag them.
        assert tag is None

        untagged_pdfs = find_untagged_pdfs(ck_bib_dir, ck_tag_dir, verbosity)
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
        else:
            print("No untagged papers.")

        for (filepath, citation_key) in untagged_pdfs:
            ctx.invoke(ck_bib_cmd, citation_key=citation_key, clipboard=False)

            print_tags(ck_tag_dir)
            tags = prompt_for_tags("Please enter tag(s) for '" + citation_key + "': ")
            for tag in tags:
                tag_paper(ck_tag_dir, ck_bib_dir, citation_key, tag)
    else:
        destpdffile = ck_to_pdf(ck_bib_dir, citation_key)
        if not os.path.exists(destpdffile):
            print("ERROR:", citation_key, "has no PDF file")
            sys.exit(1)

        if tag is None:
            ctx.invoke(ck_bib_cmd, citation_key=citation_key, clipboard=False)

            # get tag from command line
            print_tags(ck_tag_dir)
            tags = prompt_for_tags("Please enter tag(s): ")
        else:
            tags = [ tag ]

        for tag in tags:
            if tag_paper(ck_tag_dir, ck_bib_dir, citation_key, tag):
                click.echo(click.style("Added '" + tag + "' tag", fg="green")) 
            else:
                click.echo(click.style("ERROR: " + citation_key + " already has '" + tag + "' tag", fg="red"), err=True) 

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
    ck_bib_dir = ctx.obj['ck_bib_dir']
    
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

    if something_to_del:
        if not force:
            if not confirm_user("Are you sure you want to delete '" + citation_key + "' from the library?"):
                print("Okay, not deleting anything.")
                return

        for f in files:
            if os.path.exists(f):
                os.remove(f)
                print("Deleted", f)
            else:
                print("WARNING:", f, "does not exist, nothing to delete...")

        # TODO: what to do about TagDir symlinks?
    else:
        print(citation_key, "is not in library. Nothing to delete.")

@ck.command('open')
@click.argument('filename', required=True, type=click.STRING)
@click.pass_context
def ck_open_cmd(ctx, filename):
    """Opens the .pdf or .bib file."""

    ctx.ensure_object(dict)
    verbosity      = ctx.obj['verbosity']
    ck_bib_dir     = ctx.obj['ck_bib_dir']
    ck_open        = ctx.obj['ck_open'];
    ck_text_editor = ctx.obj['ck_text_editor'];

    basename, extension = os.path.splitext(filename)

    if len(extension.strip()) == 0:
        filename = basename + ".pdf"
        extension = '.pdf'
        
    fullpath = os.path.join(ck_bib_dir, filename)

    if extension.lower() == '.pdf':
        if os.path.exists(fullpath) is False:
            print("ERROR:", basename, "paper is NOT in the library as a PDF")
            sys.exit(1)

        # not interested in output
        completed = subprocess.run(
            [ck_open, fullpath],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        );
        # TODO: check for failure in completed.returncode
    elif extension.lower() == '.bib':
        os.system(ck_text_editor + " " + fullpath);
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
            print("ERROR: No HTML notes in the library for '" + basename + "'")
            sys.exit(1)

        completed = subprocess.run(
            [ck_open, fullpath],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        );
    else:
        print("ERROR:", extension.lower(), "extension is not supported")
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
    ck_bib_dir = ctx.obj['ck_bib_dir']

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
    ck_bib_dir = ctx.obj['ck_bib_dir']

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
    ck_bib_dir = ctx.obj['ck_bib_dir']

    matched = False
    
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
                    matched = True
                    if verbosity > 0:
                        print(origBibtex.strip())
                        print()
                    else:
                        print(filename)

    if matched is False:
        print("No matches!")

@ck.command('cleanbib')
@click.pass_context
def ck_cleanbib_cmd(ctx):
    """Command to clean up the .bib files a little. (Temporary, until I write something better.)"""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['ck_bib_dir']
    ck_tag_dir = os.path.normpath(os.path.realpath(ctx.obj['ck_tag_dir']))

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
    ck_bib_dir = ctx.obj['ck_bib_dir']
    ck_tag_dir = os.path.normpath(os.path.realpath(ctx.obj['ck_tag_dir']))

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

        if verbosity > 0:
            print("CWD:               ", cwd) 
            print("Tag dir:           ", ck_tag_dir) 
            print("Is CWD in tag dir? ", is_in_tag_dir)
            print()

        if is_in_tag_dir:
            paper_dir=cwd
        else:
            paper_dir=ck_bib_dir

        # TODO: list_cks could return a dict() mapping the tag name to the CK(s)?
        # Then, we can list the papers by tags below.
        cks = list_cks(paper_dir)

    if verbosity > 0:
        print(cks)

    sorted_cks = []
    for ck in cks:
        # TODO: Take flags that decide what to print. For now, "title, authors, year"
        bibfile = os.path.join(ck_bib_dir, ck + ".bib")
        if verbosity > 1:
            print("Parsing BibTeX for " + ck)

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
                print("\nWARNING: Expected '" + ck + "' CK in " + ck + ".bib file (got '" + bck + "')\n")

            author = bib['author'].replace('\r', '').replace('\n', ' ').strip()
            title  = bib['title'].strip("{}")
            year   = bib['year']
            date   = bib['ckdateadded'] if 'ckdateadded' in bib else ''

            sorted_cks.append((ck, author, title, year, date))

        except FileNotFoundError:
            print(ck + ":", "Missing BibTeX file in directory", ck_bib_dir)
        except:
            print(ck + ":", "Unexpected error")
            traceback.print_exc()

    sorted_cks = sorted(sorted_cks, key=lambda item: item[4])

    for (ck, author, title, year, date) in sorted_cks:
        click.echo(click.style(ck, fg='blue'), nl=False)
        click.echo(", ", nl=False)
        click.echo(click.style(title, fg='green'), nl=False)
        click.echo(", ", nl=False)
        click.echo(click.style(year,fg='red', bold=True), nl=False)
        click.echo(", ", nl=False)
        click.echo(author, nl=False)
        if date:
            date = datetime.strftime(datetime.strptime(date, "%Y-%m-%d %H:%M:%S"), "%B %-d, %Y")
            click.echo(', (', nl=False)
            click.echo(click.style(date, fg='magenta'), nl=False)
            click.echo(')', nl=False)
        click.echo()

        #print(ck + ": " + title + " by " + author + ", " + year + date)

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
@click.argument('output-file', type=click.File('w'))
@click.pass_context
def ck_genbib(ctx, output_file):
    """Generates a master bibliography file of all papers."""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['ck_bib_dir']

    num = 0
    sortedfiles = sorted(os.listdir(ck_bib_dir))
    for relpath in sortedfiles:
        filepath = os.path.join(ck_bib_dir, relpath)
        filename, extension = os.path.splitext(relpath)

        if extension.lower() == ".bib":
            num += 1
            bibtex = file_to_string(filepath)
            output_file.write(bibtex + '\n')

    if num == 0:
        print("No .bib files in library.")
    else:
        print("Wrote", num, ".bib files to", output_file.name)

if __name__ == '__main__':
    ck(obj={})

