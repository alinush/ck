#!/usr/bin/env python3

# NOTE: Alphabetical order please
from bibtexparser.bwriter import BibTexWriter
from bs4 import BeautifulSoup
from citationkeys.misc import *
from citationkeys.urlhandlers import *
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
import datetime
import os
import pyperclip
import subprocess
import sys
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
    ck_check(ctx.obj['ck_bib_dir'], ctx.obj['ck_tag_dir'], verbose)

@ck.command('check')
@click.pass_context
def ck_check_cmd(ctx):
    """Checks the BibDir and TagDir for integrity."""

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
                print("Checking", relpath)

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
        
    # make sure all .pdf extensions are lowercase in tagdir
    for relpath in os.listdir(ck_tag_dir):
        filepath = os.path.join(ck_tag_dir, relpath)
        ck, extOrig = os.path.splitext(relpath)
        
        ext = extOrig.lower()
        if ext != extOrig:
            print("WARNING:", filepath, "has uppercase", "." + extOrig, "extension in TagDir")
    
    # TODO: make sure symlinks are not broken in tagdir
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

    # TODO: come up with CK automatically if not specified & make sure it's unique (unclear how handle eprint version of the same paper)

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['ck_bib_dir']

    if verbosity > 0:
        print("Verbosity:", verbosity)

    now = datetime.datetime.now()
    nowstr = now.strftime("%Y-%m-%d %H:%M:%S")
    #print("Time:", nowstr)
    
    # Make sure paper doesn't exist in the library first
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
        handler(opener, soup, parsed_url, ck_bib_dir, destpdffile, destbibfile, citation_key, parser, user_agent, verbosity)
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
            for (filepath, citation_key) in untagged_pdfs:
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
        if tag is None:
            ctx.invoke(ck_bib_cmd, citation_key=citation_key, clipboard=False)

            # get tag from command line
            print_tags(ck_tag_dir)
            tags = prompt_for_tags("Please enter tag(s): ")
        else:
            tags = [ tag ]

        for tag in tags:
            tag_paper(ck_tag_dir, ck_bib_dir, citation_key, tag)

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
    """Removes the paper from the library (.pdf and .bib file)."""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['ck_bib_dir']
    
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

        # TODO: what to do about tagdir symlinks?
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
                now = datetime.datetime.now()
                nowstr = now.strftime("%Y-%m-%d %H:%M:%S")

                if confirm_user("\nWARNING: BibTeX is missing 'ckdateadded'. Would you like to set it to the current time?"):
                    # add ckdateadded field to keep track of papers by date added 
                    bibtex.entries[0]['ckdateadded'] = nowstr

                    # write back the .bib file
                    bibwriter = BibTexWriter()
                    with open(fullpath, 'w') as bibf:
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
    default=False,
    help='To (not) copy the BibTeX to clipboard.'
    )
@click.pass_context
def ck_bib_cmd(ctx, citation_key, clipboard):
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

    bibtex = file_to_string(path).strip()
    print()
    print("BibTeX for '%s'" % path)
    print()
    print(bibtex)
    print()
    if clipboard:
        pyperclip.copy(bibtex)
        print("Copied to clipboard!")
        print()

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

@ck.command('list')
@click.argument('directory', required=False, type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True))
@click.pass_context
def ck_list_cmd(ctx, directory):
    """Lists all citation keys in the library"""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['ck_bib_dir']
    ck_tag_dir = os.path.normpath(os.path.realpath(ctx.obj['ck_tag_dir']))

    if directory is not None:
        paper_dir = str(directory)
    else:
        cwd = os.path.normpath(os.getcwd())
        common_prefix = os.path.commonpath([ck_tag_dir, cwd])
        is_in_tag_dir = (common_prefix == ck_tag_dir)

        if verbosity > 0:
            print("Current working directory: ", cwd) 
            print("Tag directory:             ", ck_tag_dir) 
            print("Is in tag dir? ", is_in_tag_dir)
            print()

        if is_in_tag_dir:
            paper_dir=cwd
        else:
            paper_dir=ck_bib_dir

    if verbosity > 0:
        print("Looking in directory: ", paper_dir) 

    # TODO: Might want to support subdirectories, so this should be a dict() with the subdirectory as a key.
    # Then, we can list the papers by subdirectory below.
    cks = list_cks(paper_dir)

    for ck in cks:
        # TODO: Take flags that decide what to print. For now, "title, authors, year"
        bibfile = os.path.join(ck_bib_dir, ck + ".bib")
        if verbosity > 1:
            print("Parsing BibTeX for " + ck)

        try:
            with open(bibfile) as bibf:
                bibtex = bibtexparser.load(bibf)

            #print(bibtex.entries)
            #print("Comments: ")
            #print(bibtex.comments)
            bib = bibtex.entries[0]

            # make sure the CK in the .bib matches the filename
            bck = bib['ID']
            if bck != ck:
                print("\nWARNING: Expected '" + ck + "' CK in " + ck + ".bib file (got '" + bck + "')\n")

            author = bib['author'].replace('\r', '').replace('\n', ' ').strip()
            title  = bib['title']
            year   = bib['year']

            print(ck + ": \"" + title + "\" by " + author + ", " + year)

        except:
            print(ck + ": -- missing BibTeX in " + ck_bib_dir + " --")

    print()
    print(str(len(cks)) + " PDFs in " + paper_dir)

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

