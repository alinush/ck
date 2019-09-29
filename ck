#!/usr/bin/env python3

# NOTE: Alphabetical order please
from bs4 import BeautifulSoup
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fake_useragent import UserAgent
from pprint import pprint
from urllib.parse import urlparse, urlunparse
from urllib.request import urlopen, Request

# NOTE: Alphabetical order please
import appdirs
import bs4
import click
import configparser
import datetime
import os
import pyperclip
import smtplib
import subprocess
import sys

def notimplemented():
    print()
    print("ERROR: Not implemented yet. Exiting...")
    print()
    sys.exit(0)

def get_url(url, verbosity=0, user_agent=None):
    if verbosity > 0:
        print("Downloading page at", url, "...")

    if user_agent is not None:
        response = urlopen(Request(url, headers={'User-Agent': user_agent}))
    else:
        response = urlopen(url)

    html = response.read()
    if verbosity > 0:
        print(" * Done.")

    return html

def file_to_string(path):
    with open(path, 'r') as f:
        data = f.read()
    
    return data

#@click.group(invoke_without_command=True)
@click.group()
@click.option(
    '-c', '--config-file',
    default=os.path.join(appdirs.user_config_dir('ck'), 'ck.config'),
    help='Path to ck config file'
    )
@click.option(
    '-v', '--verbose',
    count=True,
    help='Displays more detailed information'
    )
@click.pass_context
def ck(ctx, config_file, verbose):
    if ctx.invoked_subcommand is None:
        click.echo('I was invoked without subcommand, listing bibliography...')
        notimplemented()
        click.echo('Call with --help for usage.')
    #else:
    #    click.echo("I am about to invoke '%s' subcommand" % ctx.invoked_subcommand)

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

def ck_to_pdf(ck_bib_dir, ck):
    return os.path.join(ck_bib_dir, ck + ".pdf")

def ck_to_bib(ck_bib_dir, ck):
    return os.path.join(ck_bib_dir, ck + ".bib")

@ck.command('check')
@click.pass_context
def ck_check_cmd(ctx):
    """Checks the bibdir and tagdir for integrity"""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['ck_bib_dir']
    ck_tag_dir = ctx.obj['ck_tag_dir']

    # find PDFs without bib files (and viceversa)
    for relpath in os.listdir(ck_bib_dir):
        filepath = os.path.join(ck_bib_dir, relpath)
        filename, extensionOrig = os.path.splitext(relpath)

        if verbosity > 1:
            print("Checking", relpath)

        extension = extensionOrig.lower()

        if extension == ".bib":
            if extension != extensionOrig:
                print("WARNING:", filepath, "has uppercase .bib extension")

            counterpart_ext = ".pdf"
        elif extension == ".pdf":
            if extension != extensionOrig:
                print("WARNING:", filepath, "has uppercase .pdf extension")
           
            counterpart_ext = ".bib"
        else:
            continue

        counterpart = os.path.join(ck_bib_dir, filename + counterpart_ext)
        if not os.path.exists(counterpart):
            print("WARNING: '" + relpath + "' should have a " + counterpart_ext + " file in bibdir")
        
    # make sure all .pdf extensions are lowercase in tagdir
    for relpath in os.listdir(ck_tag_dir):
        filepath = os.path.join(ck_tag_dir, relpath)
        filename, extensionOrig = os.path.splitext(relpath)
        
        extension = extensionOrig.lower()
        if extension != extensionOrig:
            print("WARNING:", filepath, "has uppercase .pdf extension in tagdir")
    
    # TODO: make sure symlinks are not broken in tagdir

@ck.command('add')
@click.argument('url', required=True, type=click.STRING)
@click.argument('citation_key', required=True, type=click.STRING)
@click.pass_context
def ck_add_cmd(ctx, url, citation_key):
    """Adds the specified paper to the library (.pdf and .bib file)"""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['ck_bib_dir']

    if verbosity > 0:
        print("Verbosity:", verbosity)

    #now = datetime.datetime.now()
    #print("Time:", now.strftime("%Y-%m-%d %H:%M"))
    
    # Make sure paper doesn't exist in the library first
    destpdffile = ck_to_pdf(ck_bib_dir, citation_key)
    destbibfile = ck_to_bib(ck_bib_dir, citation_key)

    if os.path.exists(destpdffile):
        print("ERROR:", destpdffile, "already exists. Pick a different citation key.")
        sys.exit(1)
    
    if os.path.exists(destbibfile):
        print("ERROR:", destbibfile, "already exists. Pick a different citation key.")
        sys.exit(1)

    user_agent = UserAgent().random
    parsed_url = urlparse(url)
    if verbosity > 0:
        print("Parsed added paper's URL:", parsed_url)
    index_html = get_url(url, verbosity, user_agent)

    # get domain of website and handle it accordingly
    handlers = dict()
    handlers["link.springer.com"] = springerlink_handler
    handlers["eprint.iacr.org"]   = iacreprint_handler
    handlers["dl.acm.org"]        = dlacm_handler
    # TODO: handlers["ieeexplore.ieee.org"] = ???
    # TODO: handlers["epubs.siam.org"] = ???
    # e.g., https://epubs.siam.org/doi/abs/10.1137/S0036144502417715

    domain = parsed_url.netloc
    if domain in handlers:
        parser = "lxml"
        soup = BeautifulSoup(index_html, parser)

        handler = handlers[domain]
        handler(soup, parsed_url, ck_bib_dir, destpdffile, destbibfile, citation_key, parser, user_agent, verbosity)
    else:
        print("ERROR: Cannot handle URLs from", domain, "yet.")
        sys.exit(1)

    print()
    print("TODO: Don't forget to tag the paper and change the citation key in the .bib file to", citation_key)
    print()
    print(" $ ck open", citation_key + ".bib")
    print()

def dlacm_handler(soup, parsed_url, ck_bib_dir, destpdffile, destbibfile, citation_key, parser, user_agent, verbosity):
    paper_id = parsed_url.query.split('=')[1]
    if verbosity > 0:
        print("ACM DL paper ID:", paper_id)
    # first, we scrape the PDF link
    elem = soup.find('a', attrs={"name": "FullTextPDF"})

    # then, we download the PDF
    url_prefix = parsed_url.scheme + '://' + parsed_url.netloc
    pdfurl = url_prefix + '/'  + elem.get('href')
    if verbosity > 0:
        print("Downloading PDF from:", pdfurl, " with User-Agent:", user_agent)

    req = urlopen(Request(pdfurl, headers={'User-Agent': user_agent}))
    with open(destpdffile, 'wb') as output:
        output.write(req.read())

    # second, we scrape the .bib link
    # We use the <meta name="citation_abstract_html_url" content="http://dl.acm.org/citation.cfm?id=28395.28420"> tag in the <head> 
    elem = soup.find("head").find("meta", attrs={"name": "citation_abstract_html_url"})
    newurl = urlparse(elem['content'])
    ids = newurl.query
    parent_id = ids.split('=')[1].split('.')[0]
    if verbosity > 0:
        print("ACM DL parent ID:", parent_id)

    # then, we download the .bib file from, say, https://dl.acm.org/downformats.cfm?id=28420&parent_id=28395&expformat=bibtex
    biburl = url_prefix + '/downformats.cfm?id=' + paper_id + '&parent_id=' + parent_id + '&expformat=bibtex'
    if verbosity > 0:
        print("Downloading .bib from:", biburl, " with User-Agent:", user_agent)

    req = urlopen(Request(biburl, headers={'User-Agent': user_agent}))
    with open(destbibfile, 'wb') as output:
        output.write(req.read())

def iacreprint_handler(soup, parsed_url, ck_bib_dir, destpdffile, destbibfile, citation_key, parser, user_agent, verbosity):
    pdfurl = urlunparse(parsed_url) + ".pdf"
    biburl = parsed_url.scheme + '://' + parsed_url.netloc + "/eprint-bin/cite.pl?entry=" + parsed_url.path[1:]

    print("Downloading PDF from", pdfurl, "to", destpdffile)

    req = urlopen(pdfurl)
    with open(destpdffile, 'wb') as output:
      output.write(req.read())
    
    print("Downloading BibTeX from", biburl)
    html = get_url(biburl, verbosity)
    bibsoup = BeautifulSoup(html, parser)
    bibtex = bibsoup.find('pre').text.strip()

    with open(destbibfile, 'wb') as output:
        output.write(bibtex.encode('utf-8'))

def springerlink_handler(soup, parsed_url, ck_bib_dir, destpdffile, destbibfile, citation_key, parser, user_agent, verbosity):
    url_prefix = parsed_url.scheme + '://' + parsed_url.netloc
    path = parsed_url.path
    paper_id = path[len('chapter/'):]
    print("Paper ID:", paper_id)

    elem = soup.select_one("#cobranding-and-download-availability-text > div > a")
    if verbosity > 0:
        print("HTML for PDF:", elem)

    pdfurl = url_prefix + elem.get('href')
    
    #elem = soup.select_one("#Dropdown-citations-dropdown > ul > li:nth-child(4) > a") # does not work because needs JS
    # e.g. of .bib URL: https://citation-needed.springer.com/v2/references/10.1007/978-3-540-28628-8_20?format=bibtex&flavour=citation
    biburl = 'https://citation-needed.springer.com/v2/references' + paper_id + '?format=bibtex&flavour=citation'

    print("Downloading PDF from", pdfurl, "to", destpdffile)

    req = urlopen(pdfurl)
    with open(destpdffile, 'wb') as output:
        output.write(req.read())
    
    print("Downloading .bib from", biburl, "to", destbibfile)
    req = urlopen(biburl)
    with open(destbibfile, 'wb') as output:
        output.write(req.read())

@ck.command('rm')
@click.option(
    '-y', '--yes',
    is_flag=True,
    default=False,
    help='Do not prompt for confirmation before deleting'
    )
@click.argument('citation_key', required=True, type=click.STRING)
@click.pass_context
def ck_rm_cmd(ctx, yes, citation_key):
    """Removes the specified paper from the library (.pdf and .bib file)"""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['ck_bib_dir']
    
    files = [ ck_to_pdf(ck_bib_dir, citation_key), ck_to_bib(ck_bib_dir, citation_key) ]
    something_to_del = False
    for f in files:
        if os.path.exists(f):
            something_to_del = True

    if something_to_del:
        if not yes:
            sys.stdout.write("Are you sure you want to delete '" + citation_key + "' from the library? [y/N]: ")
            sys.stdout.flush()
            answer = sys.stdin.readline().strip()
            if answer != "y":
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
@click.argument('pdf_or_bib_file', required=True, type=click.STRING)
@click.pass_context
def ck_open_cmd(ctx, pdf_or_bib_file):
    """Opens the .pdf or .bib file"""

    ctx.ensure_object(dict)
    verbosity      = ctx.obj['verbosity']
    ck_bib_dir     = ctx.obj['ck_bib_dir']
    ck_open        = ctx.obj['ck_open'];
    ck_text_editor = ctx.obj['ck_text_editor'];

    filename, extension = os.path.splitext(pdf_or_bib_file)

    if not extension.strip():
        pdf_or_bib_file = pdf_or_bib_file + ".pdf"
        extension = '.pdf'
        
    fullpath = os.path.join(ck_bib_dir, pdf_or_bib_file)

    if extension.lower() == '.pdf':
        if os.path.exists(fullpath) is False:
            print("ERROR:", filename, "paper is NOT in the library as a PDF")
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
        print(file_to_string(fullpath).strip())
    else:
        print("ERROR:", extension.lower(), "extension is not supported")
        sys.exit(1)

@ck.command('bib')
@click.argument('citation_key', required=True, type=click.STRING)
@click.pass_context
def ck_bib_cmd(ctx, citation_key):
    """Prints the specified paper's BibTeX and copies it to the clipboard"""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['ck_bib_dir']

    # TODO: maybe add args for isolating author/title/year/etc

    path = os.path.join(ck_bib_dir, citation_key + '.bib')
    if os.path.exists(path) is False:
        print("ERROR:", citation_key, "has no .bib file")
        sys.exit(1)

    bibtex = file_to_string(path).strip()
    print()
    print("BibTeX for '%s'" % path)
    print()
    print(bibtex)
    print()
    print("Copied to clipboard!")
    print()
    pyperclip.copy(bibtex)

@ck.command('rename')
@click.argument('old_citation_key', required=True, type=click.STRING)
@click.argument('new_citation_key', required=True, type=click.STRING)
@click.pass_context
def ck_rename_cmd(ctx, old_citation_key, new_citation_key):
    """Renames a paper's .pdf and .bib file with a new citation key. Updates its .bib file and all symlinks to it in the tagdir."""

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
    help='Enables case-sensitive search'
    )
@click.pass_context
def ck_search_cmd(ctx, query, case_sensitive):
    """Searches all .bib files for the specified text"""

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

@ck.command('l')
@click.argument('query', required=False, type=click.STRING)
@click.pass_context
def ck_list_cmd(ctx, query):
    """Lists papers in the library that match the query"""

    ctx.ensure_object(dict)
    verbosity  = ctx.obj['verbosity']
    ck_bib_dir = ctx.obj['ck_bib_dir']

    for relpath in os.listdir(ck_bib_dir):
        filepath = os.path.join(ck_bib_dir, relpath)
        filename, extension = os.path.splitext(relpath)

        if extension.lower() == ".pdf":
            print(filename)
            if verbosity > 0:
                bibfile = os.path.join(ck_bib_dir, filename + ".bib")
                if os.path.exists(bibfile) is False:
                    print("WARNING: No .bib file for '%s' paper" % (filename))
                else:
                    print(file_to_string(bibfile))
                print

    # TODO: query could be a space-separated list of tokens
    # a token can be a hashtag (e.g., #dkg-dlog) or a sorting token (e.g., 'year')
    # For example: 
    #  $ ck l #dkg-dlog year title
    # would list all papers with tag #dkg-dlog and sort them by year and then by title
    # TODO: could have AND / OR operators for hashtags
    # TODO: filter by year/author/title/conference

if __name__ == '__main__':
    ck(obj={})

