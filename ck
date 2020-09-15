#!/usr/bin/env python3

# NOTE: Alphabetical order please
from os import abort, path
from bibtexparser.bwriter import BibTexWriter
from bs4 import BeautifulSoup
from citationkeys.bib  import *
from citationkeys.misc import *
from citationkeys.tags import *
from citationkeys.urlhandlers import *
from datetime import datetime
from fake_useragent import UserAgent
from http.cookiejar import CookieJar
from pathlib import Path
from pprint import pprint
from urllib.parse import urlparse, urlunparse
from urllib.request import Request

# NOTE: Alphabetical order please
import appdirs
import bibtexparser
import bs4
import click
import configparser
import glob
import os
import pyperclip
import random
import re
import subprocess
import shutil
import string
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

    if verbose > 0:
        click.echo("Verbosity level: " + str(verbose))
        click.echo("Reading CK config file at " + config_file)

    # read configuration
    if not os.path.exists(config_file):
        print_error("CK config file does not exist: " + config_file)
        sys.exit(1)

    if verbose > 1:
        click.echo(file_to_string(config_file).strip())

    config = configparser.ConfigParser()
    with open(config_file, 'r') as f:
        config.read_file(f)

    if verbose > 2:
        click.echo("Configuration sections: " + str(config.sections()))

    # set a context with various config params that we pass around to the subcommands
    try:
        ctx.ensure_object(dict)
        ctx.obj['verbosity']                  = verbose
        ctx.obj['BibDir']                     = config['default']['BibDir']
        ctx.obj['TagDir']                     = config['default']['TagDir']
        ctx.obj['DefaultCk']                  = config['default']['DefaultCk']
        ctx.obj['TextEditor']                 = config['default']['TextEditor']
        ctx.obj['MarkdownEditor']             = config['default']['MarkdownEditor']
        ctx.obj['TagAfterCkAddConflict']      = config['default']['TagAfterCkAddConflict'].lower() == "true"
        ctx.obj['tags']                       = find_tagged_pdfs(ctx.obj['TagDir'], verbose)
    except:
        print_error("Config file '" + config_file + "' is in bad shape. Please edit manually!")
        raise


    # set command to open PDFs with
    if sys.platform.startswith('linux'):
        ctx.obj['OpenCmd'] = 'xdg-open'
    elif sys.platform == 'darwin':
        ctx.obj['OpenCmd'] = 'open'
    else:
        print_error(sys.platform + " is not supported.")
        sys.exit(1)

    if verbose > 0:
        click.echo()

    # always do a sanity check before invoking the actual subcommand
    # TODO(Alin): figure out how to call this *after* (not before) the subcommand is invoked, so the user can actually see its output
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
            print_warning(filepath + " has uppercase " + "." + extOrig + " extension in TagDir")
    
    # TODO(Alin): make sure symlinks are not broken in TagDir
    # TODO(Alin): make sure all .bib files have the right CK and have ckdateadded

def abort_citation_exists(ctx, destpdffile, citation_key):
    print_error(destpdffile + " already exists. Pick a different citation key.")

    askToTagConflict = ctx.obj['TagAfterCkAddConflict']

    if askToTagConflict:
        # Could be useful to ask the user to tag the conflicting paper?
        print()
        if click.confirm("Would you like to tag the existing paper?", default=True):
            print()
            # prompt user to tag paper
            ctx.invoke(ck_tag_cmd, citation_key=citation_key)

@ck.command('add')
@click.argument('url', required=True, type=click.STRING)
@click.argument('citation_key', required=False, type=click.STRING)
@click.option(
    '-n', '--no-tag-prompt',
    is_flag=True,
    default=False,
    help='Does not prompt the user to tag the paper.'
    )
@click.pass_context
def ck_add_cmd(ctx, url, citation_key, no_tag_prompt):
    """Adds the paper to the library (.pdf and .bib file).
       Uses the specified citation key, if given.
       Otherwise, uses the DefaultCk policy in the configuration file."""

    ctx.ensure_object(dict)
    verbosity        = ctx.obj['verbosity']
    default_ck       = ctx.obj['DefaultCk']
    ck_bib_dir       = ctx.obj['BibDir']
    ck_tag_dir       = ctx.obj['TagDir']

    parsed_url = urlparse(url)
    if verbosity > 0:
        print("Paper's URL:", parsed_url)

    # get domain of website and handle it accordingly
    #
    # TODO(Alex): Change to regex matching
    # NOTE(Alin): Sure, but for now might be overkill: the only time we need it is for [www.]sciencedirect.com
    #
    # TODO(Alex): Incorporate Zotero translators (see https://www.zotero.org/support/translators)
    handlers = {
        "link.springer.com"     : springerlink_handler,
        "arxiv.org"             : arxiv_handler,
        "rd.springer.com"       : springerlink_handler,
        "eprint.iacr.org"       : iacreprint_handler,
        "dl.acm.org"            : dlacm_handler,
        "epubs.siam.org"        : epubssiam_handler,
        "ieeexplore.ieee.org"   : ieeexplore_handler,
        "www.sciencedirect.com" : sciencedirect_handler,
        "sciencedirect.com"     : sciencedirect_handler,
    }

    # For most handled URLs, the handlers get a parsed index.html object. But,
    # for others (e.g., IACR ePrint), the handler doesn't need to parse the
    # page at all since the .pdf and .bib file links are derived directly from
    # the URL itself.
    no_index_html = set()
    no_index_html.add("eprint.iacr.org")

    # Sets up a HTTP URL opener object, with a random UserAgent to prevent various
    # websites from borking.
    domain = parsed_url.netloc
    cj = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    user_agent = UserAgent().random

    # This is used to initialize the BeautifoulSoup HTML parser.
    parser = "lxml" 

    # The PDF and .bib data will be stored in these variables before being written to disk
    pdf_data = None
    bibtex = None

    # Download PDF (and potentially .bib file too)
    is_handled_url = domain in handlers
    if is_handled_url:
        soup = None
        index_html = None

        # e.g., We don't need to download the index.html page for IACR ePrint
        if domain not in no_index_html:
            index_html = get_url(opener, url, verbosity, user_agent)
            soup = BeautifulSoup(index_html, parser)

        handler = handlers[domain]
        bibtex, pdf_data = handler(opener, soup, parsed_url, ck_bib_dir, parser, user_agent, verbosity)
    else:
        click.echo("No handler for URL was found. This is a PDF-only download, so expecting user to give a citation key.")
        
        # If no citation key is given, fail because we can't check .bib file exists until after
        # user did all the .bib file editing. Thus, it would be unfriendly to tell them their
        # citation key already exists and waste their editing work.
        if not citation_key:
            print_error("Please supply the citation key too, since it cannot be determined from PDF only.")
            sys.exit(1)

        click.echo("Trying to download as PDF...")
        pdf_data = download_pdf(opener, user_agent, url, verbosity)

        # If there's no .bib file for the user's citation key, let them edit one manually.
        bibpath_tmp = ck_to_bib(ck_bib_dir, citation_key)
        if not os.path.exists(bibpath_tmp):
            bibent_tmp = bibent_new(citation_key, "misc")

            # TODO(Alex): Try to pre-fill information here from PDF metadata (or PDF OCR?)
            bibent_tmp['howpublished']   = '\\url{' + url + '}'
            bibent_tmp['author']         = ''
            bibent_tmp['year']           = ''
            bibent_tmp['title']          = ''

            bibtex = bibent_to_bibtex(bibent_tmp)

            # Launch external editor and return the edited .bib file data
            bibtex_old = bibtex
            bibtex = click.edit(bibtex_old, ctx.obj['TextEditor']).encode('utf-8')

            # NOTE(Alin): Could simply not add a .bib file when the user fails to add the info,
            # but then 'ck add' would leave the library in an inconsistent state. So we abort.
            if bibtex_old == bibtex:
                print_error("You must add author(s), year and title to the .bib file.")
                sys.exit(1)
        else:
            # WARNING: Code below expects bibtex to be bytes that it can call .decode() on
            bibtex = file_to_bytes(bibpath_tmp)

    #
    # Invariant: We have the PDF data in pdf_data and the .bib data in bibtex.
    #            If this is a non-handled URL, we also have the citation key for the file.
    #            If it's a handled URL, we can determine the citation key.
    #            Either way, we are ready to check the paper does not exist and, if so, save the files.
    #

    # Parse the BibTeX into an object
    bibent = defaultdict(lambda : '', bibtex_to_bibent(bibtex.decode()))
    bibtex = None # make sure we never use this again

    # If no citation key was given as argument, use the DefaultCk policy from the configuration file.
    # NOTE(Alin): Non-handled URLs always have a citation key, so we need not worry about them.
    if not citation_key:
        # We use the DefaultCk policy from the configuration file to determine the citation key, if none was given
        if default_ck == "KeepBibtex":
            citation_key = bibent['ID']
        elif default_ck == "FirstAuthorYearTitle":
            citation_key = bibent_get_first_author_year_title_ck(bibent)
        elif default_ck == "InitialsShortYear":
            citation_key = bibent_get_author_initials_ck(bibent, verbosity)
            citation_key += bibent['year'][-2:]
        elif default_ck == "InitialsFullYear":
            citation_key = bibent_get_author_initials_ck(bibent, verbosity)
            citation_key += bibent['year']
        else:
            print_error("Unknown default citation key policy in configuration file: " + default_ck)
            sys.exit(1)
            
        # Something went wrong if the citation key is empty, so exit.
        assert len(citation_key) > 0

    # Set the citation key in the BibTeX object
    click.secho('Will use citation key: %s' % citation_key, fg="yellow")
    bibent['ID'] = citation_key
    
    # Derive PDF and .bib file paths from citation key.
    destpdffile = ck_to_pdf(ck_bib_dir, citation_key)
    destbibfile = ck_to_bib(ck_bib_dir, citation_key)
    
    # Make sure we've never added this paper before! (Otherwise, user will be surprised when
    # they overwrite their previous papers.)
    if os.path.exists(destpdffile):
        abort_citation_exists(ctx, destpdffile, citation_key)
        sys.exit(1)

    # One caveat:
    #  - For handled URLs, if we have a .bib file but no PDF, then something went wrong, so we err on the side of displaying an error to the user
    #  - For non-handled URLs, a .bib file might be there from a previous 'ck bib' or 'ck open' command, and we want to leave it untouched.
    #
    # TODO(Alin): This makes the flow of 'ck add' too complicated to follow.
    # We should simplify it by adding 'ck updatepdf' and 'ck updatebib' as commands used to update the .bib and .pdf files explicitly.
    # Then, 'ck add' should always check that neither a PDF nor a .bib file exists.
    if is_handled_url and os.path.exists(destbibfile):
        abort_citation_exists(ctx, destbibfile, citation_key)
        sys.exit(1)
    
    # Write the PDF file
    with open(destpdffile, 'wb') as fout:
        fout.write(pdf_data)

    # Write the .bib file
    # (except for the case where it this is a non-handled URL and a .bib file exists)
    if not os.path.exists(destbibfile):
        # First, sets the 'ckdateadded' field in the .bib file
        bibent_set_dateadded(bibent, None)
        bibent_to_file(destbibfile, bibent)

    # Prompt the user to tag the paper
    if not no_tag_prompt:
        # TODO(Alin): Print abstract, authors, year & title to the user and prompt user for tags!
        ctx.invoke(ck_tag_cmd, citation_key=citation_key)

@ck.command('config')
@click.option(
    '-e', '--edit',
    is_flag=True,
    default=False,
    help='Actually opens an editor to edit the file.')
@click.pass_context
def ck_config_cmd(ctx, edit):
    """Lets you edit the config file and prints it at the end."""

    ctx.ensure_object(dict)
    ck_text_editor = ctx.obj['TextEditor']

    config_file = os.path.join(appdirs.user_config_dir('ck'), 'ck.config')

    if not edit:
        print(config_file)
    else:
        os.system(ck_text_editor + " \"" + config_file + "\"")

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
        ctx.invoke(ck_tag_cmd, silent=True, citation_key=citation_key, tags="queue/to-read")
        ctx.invoke(ck_untag_cmd, silent=True, citation_key=citation_key, tags="queue/finished,queue/reading")
    else:
        click.secho("Papers that remain to be read:", bold=True)
        click.echo()

        ctx.invoke(ck_list_cmd, pathnames=[os.path.join(ck_tag_dir, 'queue/to-read')])

@ck.command('dequeue')
@click.argument('citation_key', required=True, type=click.STRING)
@click.pass_context
def ck_dequeue_cmd(ctx, citation_key):
    """Removes this paper from the to-read list"""
    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']
    ck_tag_dir = ctx.obj['TagDir']

    ctx.invoke(ck_untag_cmd, silent=True, citation_key=citation_key, tags="queue/to-read")

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
        ctx.invoke(ck_untag_cmd, silent=True, citation_key=citation_key, tags="queue/to-read,queue/finished")
        ctx.invoke(ck_tag_cmd, silent=True, citation_key=citation_key, tags="queue/reading")
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
        ctx.invoke(ck_untag_cmd, silent=True, citation_key=citation_key, tags="queue/to-read,queue/reading")
        ctx.invoke(ck_tag_cmd, silent=True, citation_key=citation_key, tags="queue/finished")
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
@click.option(
    '-s', '--silent',
    is_flag=True,
    default=False,
    help='Does not display error message when paper was not tagged.')
@click.argument('citation_key', required=False, type=click.STRING)
@click.argument('tags', required=False, type=click.STRING)
@click.pass_context
def ck_untag_cmd(ctx, force, silent, citation_key, tags):
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
            sys.stdout.write("Untagged papers:\n")
            for (filepath, citation_key) in untagged_pdfs:
                # display paper info
                ctx.invoke(ck_info_cmd, citation_key=citation_key)
            click.echo()

            for (filepath, citation_key) in untagged_pdfs:
                # prompt user to tag paper
                ctx.invoke(ck_tag_cmd, citation_key=citation_key)
        else:
            click.echo("No untagged papers.")
    else:
        if tags is not None:
            tags = parse_tags(tags)
            for tag in tags:
                if untag_paper(ck_tag_dir, citation_key, tag):
                    click.secho("Removed '" + tag + "' tag", fg="green")
                else:
                    # When invoked by ck_{queue/read/finished}_cmd, we want this silenced
                    if not silent:
                        click.secho("Was not tagged with '" + tag + "' tag to begin with", fg="red", err=True)
        else:
            if force or click.confirm("Are you sure you want to remove ALL tags for " + click.style(citation_key, fg="blue") + "?"):
                if untag_paper(ck_tag_dir, citation_key):
                    click.secho("Removed all tags!", fg="green")
                else:
                    click.secho("No tags to remove.", fg="red")

@ck.command('info')
@click.argument('citation_key', required=True, type=click.STRING)
@click.pass_context
def ck_info_cmd(ctx, citation_key):
    """Displays info about the specified paper"""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']
    ck_tag_dir = ctx.obj['TagDir']
    ck_tags    = ctx.obj['tags']

    include_url = True
    print_ck_tuples(cks_to_tuples(ck_bib_dir, [ citation_key ], verbosity), ck_tags, include_url)

@ck.command('tags')
@click.argument('tag', required=False, type=click.STRING)
@click.pass_context
def ck_tags_cmd(ctx, tag):
    """Lists all tags in the library. If a <tag> is given as argument, prints matching tags in the library."""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']
    ck_tag_dir = ctx.obj['TagDir']
    ck_tags    = ctx.obj['tags']

    tags = get_all_tags(ck_tag_dir)
    if tag is None:
        print_tags(tags)
    else:
        matching = []
        for t in tags:
            if tag in t:
                matching.append(t)

        if len(matching) > 0:
            click.echo("Tags matching '" + tag + "': ", nl=False)
            print_tags(matching)
        else:
            click.secho("No tags matching '" + tag + "' in library.", fg='yellow')

@ck.command('tag')
@click.option(
    '-s', '--silent',
    is_flag=True,
    default=False,
    help='Does not display error message when paper is already tagged.')
@click.argument('citation_key', required=True, type=click.STRING)
@click.argument('tags', required=False, type=click.STRING)
@click.pass_context
def ck_tag_cmd(ctx, silent, citation_key, tags):
    """Tags the specified paper"""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']
    ck_tag_dir = ctx.obj['TagDir']
    ck_tags    = ctx.obj['tags']

    #if not silent:
    #    click.echo("Tagging '" + style_ck(citation_key) + "' with " + style_tags(tags) + "...")

    ctx.invoke(ck_info_cmd, citation_key=citation_key)

    if not ck_exists(ck_bib_dir, citation_key):
        print_error(citation_key + " has no PDF file.")
        sys.exit(1)

    if tags is None:
        completed = subprocess.run(
            ['which pdfgrep'],
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        if completed.returncode != 0: 
            print_warning("Not suggesting any tags because 'pdfgrep' is not installed.")
        else:
            tags = get_all_tags(ck_tag_dir)
            suggested_tags = []
            tag_extended_regex = '|'.join([ r'\b{}\b'.format(t) for t in tags])

            try:
                matches = subprocess.check_output("pdfgrep '%s' %s" % (tag_extended_regex, ck_to_pdf(ck_bib_dir, citation_key)), shell=True).decode()
            except subprocess.CalledProcessError as e:
                print_warning("Not suggesting any tags because 'pdfgrep' returned with non-zero return code: " + str(e.returncode))
                matches = ''

            for tag in tags:
                if tag in matches: # count only non-zero
                    suggested_tags.append((tag, matches.count(tag)))

            suggested_tags = sorted(suggested_tags, key=lambda x: x[1], reverse=True)

            if len(suggested_tags) > 0:
                click.secho("Suggested tags: " + ','.join([x[0] for x in suggested_tags]), fg="cyan")

        # returns array of tags
        tags = prompt_for_tags(ctx, "Please enter tag(s) for '" + click.style(citation_key, fg="blue") + "'")
    else:
        # parses comma-separated tag string into an array of tags
        tags = parse_tags(tags)

    for tag in tags:
        if tag_paper(ck_tag_dir, ck_bib_dir, citation_key, tag):
            click.secho("Added '" + tag + "' tag", fg="green")
        else:
            # When invoked by ck_{queue/read/finished}_cmd, we want this silenced
            if not silent:
                click.secho(citation_key + " already has '" + tag + "' tag", fg="red", err=True)

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
            if not click.confirm("Are you sure you want to delete '" + citation_key + "' from the library?"):
                click.echo("Okay, not deleting anything.")
                return

        for f in files:
            if os.path.exists(f):
                os.remove(f)
                click.secho("Deleted " + f, fg="green")
            else:
                print_warning(f + " does not exist, nothing to delete...")

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
    verbosity          = ctx.obj['verbosity']
    ck_bib_dir         = ctx.obj['BibDir']
    ck_tag_dir         = ctx.obj['TagDir']
    ck_open            = ctx.obj['OpenCmd']
    ck_text_editor     = ctx.obj['TextEditor']
    ck_markdown_editor = ctx.obj['MarkdownEditor']
    ck_tags            = ctx.obj['tags']

    citation_key, extension = os.path.splitext(filename)

    if len(extension.strip()) == 0:
        filename = citation_key + ".pdf"
        extension = '.pdf'

    fullpath = os.path.join(ck_bib_dir, filename)

    # The BibTeX might be in bad shape (that's why the user is using ck_open_cmd to edit) so ck_info_cmd, might throw
    if extension.lower() != '.bib':
        ctx.invoke(ck_info_cmd, citation_key=citation_key)

    if extension.lower() == '.pdf':
        if os.path.exists(fullpath) is False:
            print_error(citation_key + " paper is NOT in the library as a PDF.")
            sys.exit(1)

        # not interested in output
        completed = subprocess.run(
            [ck_open, fullpath],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        
        if completed.returncode != 0:
            print_error("Could not open " + fullpath)
            sys.exit(1)
    elif extension.lower() == '.bib':
        os.system(ck_text_editor + " " + fullpath)

        # After the user successfully edited the file, we add the correct citation key and the 'ckdateadded' field
        if os.path.exists(fullpath):
            print(file_to_string(fullpath).strip())
        
            try:
                bibent = bibent_from_file(fullpath)

                # make sure the .bib file always has the right citation key
                bibent['ID'] = citation_key

                # warn if bib file is missing 'ckdateadded' field
                if 'ckdateadded' not in bibent:
                    if click.confirm("\nWARNING: BibTeX is missing 'ckdateadded'. Would you like to set it to the current time?"):
                        bibent_set_dateadded(bibent, None)

                # write back the file
                bibent_to_file(fullpath, bibent)
            except:
                print_warning("Could not parse BibTeX:")
                traceback.print_exc()

    elif extension.lower() == '.md':
        # NOTE: Need to cd to the directory first so vim picks up the .vimrc there
        os.system('cd "' + ck_bib_dir + '" && ' + ck_markdown_editor + ' "' + filename + '"')
    elif extension.lower() == '.html':
        if os.path.exists(fullpath) is False:
            print_error("No HTML notes in the library for '" + citation_key + "'.")
            sys.exit(1)

        completed = subprocess.run(
            [ck_open, fullpath],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if completed.returncode != 0:
            print_error("Could not open " + fullpath)
            sys.exit(1)
    else:
        print_error(extension.lower() + " extension is not supported.")
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

    path = ck_to_bib(ck_bib_dir, citation_key)
    if os.path.exists(path) is False:
        if click.confirm(citation_key + " has no .bib file. Would you like to create it?"):
            ctx.invoke(ck_open_cmd, filename=citation_key + ".bib")
        else:
            click.echo("Okay, will NOT create .bib file. Exiting...")
            sys.exit(1)

    # Parse the BibTeX
    bibent = bibent_from_file(path)
    has_abstract = False

    if not markdown:
        print("BibTeX for '%s'" % path)
        print()

        # We print the full thing!
        to_print = bibent_to_bibtex(bibent)

        # We're not gonna copy the abstract to the clipboard, since usually we don't want it taking up space in .bib files of papers we're writing.
        has_abstract = 'abstract' in bibent
        bibent.pop('abstract', None)
        to_copy = bibent_to_bibtex(bibent)
    else:
        title = bibent['title'].strip("{}")
        authors = bibent['author']
        year = bibent['year']
        authors = authors.replace("{", "")
        authors = authors.replace("}", "")
        citation_key_noplus = citation_key.replace("+", "plus") # beautiful-jekyll is not that beautiful and doesn't like '+' in footnote names
        to_copy = "[^" + citation_key_noplus + "]: **" + title + "**, by " + authors

        if 'booktitle' in bibent:
            venue = bibent['booktitle']
        elif 'journal' in bibent:
            venue = bibent['journal']
        elif 'howpublished' in bibent and "\\url" not in bibent['howpublished']:
            venue = bibent['howpublished']
        else:
            venue = None

        if venue != None:
            to_copy = to_copy + ", *in " + venue + "*"

        to_copy = to_copy +  ", " + year

        url = bibent_get_url(bibent)
        if url is not None:
            mdurl = "[[URL]](" + url + ")"
            to_copy = to_copy + ", " + mdurl

        # For Markdown bib's, we print exactly what we copy!
        to_print = to_copy

    click.secho(to_print, fg='cyan')

    if clipboard:
        pyperclip.copy(to_copy)
        click.echo()
        if markdown or not has_abstract:
            print_success("Copied to clipboard!")
        else:
            print_success("Copied to clipboard (without abstract)!")

@ck.command('rename')
@click.argument('old_citation_key', required=True, type=click.STRING)
@click.argument('new_citation_key', required=True, type=click.STRING)
@click.pass_context
def ck_rename_cmd(ctx, old_citation_key, new_citation_key):
    """Renames a paper's .pdf and .bib file with a new citation key. Updates its .bib file and all symlinks to it in the TagDir."""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']
    ck_tag_dir = ctx.obj['TagDir']
    ck_tags    = ctx.obj['tags']

    # make sure old CK exists and new CK does not
    if not ck_exists(ck_bib_dir, old_citation_key):
        print_error("Old citation key '" + old_citation_key + "' does NOT exist.")
        sys.exit(1)

    if ck_exists(ck_bib_dir, new_citation_key):
        print_error("New citation key '" + new_citation_key + "' already exists.")
        sys.exit(1)

    # find all files associated with the CK
    files = glob.glob(os.path.join(ck_bib_dir, old_citation_key) + '*')
    for f in files:
        path_noext, ext = os.path.splitext(f)
        # e.g.,
        # ('/Users/alinush/Dropbox/Papers/MBK+19', '.pdf')
        # ('/Users/alinush/Dropbox/Papers/MBK+19', '.bib')
        # ('/Users/alinush/Dropbox/Papers/MBK+19.slides', '.pdf')

        #dirname = os.path.dirname(path_noext)  # i.e., BibDir
        oldfilename = os.path.basename(path_noext)

        # replaces only the 1st occurrence of the old CK to deal with the (astronomically-rare?)
        # event where the old CK appears multiple times in the filename
        newfilename = oldfilename.replace(old_citation_key, new_citation_key, 1)
        click.echo("Renaming '" + oldfilename + ext + "' to '" + newfilename + ext + "' in " + ck_bib_dir)

        # rename file in BibDir
        os.rename(
            os.path.join(ck_bib_dir, oldfilename + ext), 
            os.path.join(ck_bib_dir, newfilename + ext))

    # update .bib file citation key
    click.echo("Renaming CK in .bib file...")
    bibpath_rename_ck(ck_to_bib(ck_bib_dir, new_citation_key), new_citation_key)

    # if the paper is tagged, update all symlinks in TagDir by un-tagging and re-tagging
    if old_citation_key in ck_tags:
        click.echo("Recreating tag information...")
        tags = ck_tags[old_citation_key]
        for tag in tags:
            if not untag_paper(ck_tag_dir, old_citation_key, tag):
                print_warning("Could not remove '" + tag + "' tag")

            if not tag_paper(ck_tag_dir, ck_bib_dir, new_citation_key, tag):
                print_warning("Already has '" + tag + "' tag")

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
        include_url = True
        print_ck_tuples(cks_to_tuples(ck_bib_dir, cks, verbosity), ck_tags, include_url)
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
        bibfile = ck_to_bib(ck_bib_dir, ck)
        if verbosity > 1:
            print("Parsing BibTeX for " + ck)
        try:
            with open(bibfile) as bibf:
                parser = bibtexparser.bparser.BibTexParser(interpolate_strings=True, common_strings=True)
                bibtex = bibtexparser.load(bibf, parser)

            assert len(bibtex.entries) == 1
            assert type(ck) == str
            updated = bibent_canonicalize(ck, bibtex.entries[0], verbosity)

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
#@click.argument('pathnames', nargs=-1, type=click.Path(exists=True, file_okay=True, dir_okay=True, resolve_path=True))
@click.argument('pathnames', nargs=-1, type=click.STRING)
@click.option(
    '-u', '--url',
    is_flag=True,
    default=False,
    help='Includes the URLs next to each paper'
    )
@click.option(
    '-s', '--short',
    is_flag=True,
    default=False,
    help='Citation keys only'
)
@click.option(
    '-r', '--relative', 'is_relative_to_tagdir',
    is_flag=True,
    default=False,
    help='Interprets all pathnames relative to TagDir'
)
@click.pass_context
def ck_list_cmd(ctx, pathnames, url, short, is_relative_to_tagdir):
    """Lists all citation keys in the library. Pathnames can be a list of <citation-key>'s, a list of <tag>'s, a list of <tag>/<citation-key>'s (if -t is given) or it can be empty (to print all citation keys)."""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']
    ck_tag_dir = os.path.normpath(os.path.realpath(ctx.obj['TagDir']))
    ck_tags    = ctx.obj['tags']

    cks = cks_from_paths(ck_bib_dir, ck_tag_dir, pathnames, is_relative_to_tagdir)
    
    if short:
        print(' '.join(cks))

    else:
        if verbosity > 0:
            print(cks)

        ck_tuples = cks_to_tuples(ck_bib_dir, cks, verbosity)

        sorted_cks = sorted(ck_tuples, key=lambda item: item[4])
    
        print_ck_tuples(sorted_cks, ck_tags, url)

        print()
        print(str(len(cks)) + " PDFs listed")

    # TODO(Alin): query could be a space-separated list of tokens
    # a token can be a hashtag (e.g., #dkg-dlog) or a sorting token (e.g., 'year')
    # For example: 
    #  $ ck l #dkg-dlog year title
    # would list all papers with tag #dkg-dlog and sort them by year and then by title
    # TODO(Alin): could have AND / OR operators for hashtags
    # TODO(Alin): filter by year/author/title/conference

@ck.command('genbib')
@click.argument('output-bibtex-file', required=True, type=click.File('w'))
@click.argument('pathnames', nargs=-1, type=click.Path(exists=True, file_okay=True, dir_okay=True, resolve_path=True))
@click.option(
    '-r', '--relative', 'is_relative_to_tagdir',
    is_flag=True,
    default=False,
    help='Interprets all pathnames relative to TagDir'
)
@click.pass_context
def ck_genbib(ctx, output_bibtex_file, pathnames, is_relative_to_tagdir):
    """Generates a master bibliography file of all papers. Pathnames can be a list of <citation-key>'s, a list of <tag>'s, a list of <tag>/<citation-key>'s (if -t is given) or it can be empty (to indicate all citation keys should be exported)."""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']
    ck_tag_dir = ctx.obj['TagDir']

    cks = cks_from_paths(ck_bib_dir, ck_tag_dir, pathnames, is_relative_to_tagdir)

    num = 0
    sortedcks = sorted(cks)
    for ck in sortedcks:
        bibfilepath = ck_to_bib(ck_bib_dir, ck)

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
@click.option(
    '-r', '--relative', 'is_relative_to_tagdir',
    is_flag=True,
    default=False,
    help='Interprets all pathnames relative to TagDir'
)
@click.pass_context
def ck_copypdfs(ctx, output_dir, pathnames, is_relative_to_tagdir):
    """Copies all PDFs from the specified pathnames into the output directory. Pathnames can be a list of <citation-key>'s, a list of <tag>'s, a list of <tag>/<citation-key>'s (if -t is given) or it can be empty (to copy all citation keys)."""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['BibDir']
    ck_tag_dir = ctx.obj['TagDir']

    cks = cks_from_paths(ck_bib_dir, ck_tag_dir, pathnames, is_relative_to_tagdir)

    num = 0
    sortedcks = sorted(cks)
    for ck in sortedcks:

        if ck_exists(ck_bib_dir, ck):
            num += 1
            shutil.copy2(ck_to_pdf(ck_bib_dir, ck), output_dir)

    if num == 0:
        print("No .pdf files in specified directories.")
    else:
        print("Copied", num, ".pdf files to", output_dir)

if __name__ == '__main__':
    ck(obj={})

