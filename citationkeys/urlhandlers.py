#!/usr/bin/env python3

# NOTE: Alphabetical order please
from bs4 import BeautifulSoup
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fake_useragent import UserAgent
from http.cookiejar import CookieJar
from pprint import pprint
from urllib.parse import urlparse, urlunparse
from urllib.request import Request
from .misc import *

# NOTE: Alphabetical order please
import appdirs
import bibtexparser
import bs4
import click
import configparser
import datetime
import os
import pyperclip
import smtplib
import sys
import tempfile
import urllib

def get_url(opener, url, verbosity, user_agent, restrict_content_type=None, extra_headers={}):
    # TODO(Alin): handle 403 error and display HTML returned
    if verbosity > 0:
        print("Downloading URL:", url)

    if user_agent is None:
        raise "Please specify a user agent"

    try:
        extra_headers['User-Agent'] = user_agent
        req = Request(url, headers=extra_headers)
        response = opener.open(req)
        content_type = response.getheader("Content-Type")
        #click.echo("Content-Type: " + str(content_type))
        # throw if bad content type
        found = False
        if restrict_content_type is not None:
            # we allow user to either pass a string, or a list of strings for this
            if not isinstance(restrict_content_type, list):
                restrict_content_type = [ restrict_content_type ]

            for r in restrict_content_type:
                if content_type.startswith(r):
                    found = True

            if not found:
                raise RuntimeError("Expected this to be URL to " + str(restrict_content_type) + " but got '" + content_type + "' Content-Type")
    except urllib.error.HTTPError as err:
        print("HTTP Error Code: ", err.code)
        print("HTTP Error Reason: ", err.reason)
        print("HTTP Error Headers: ", err.headers)
        raise

    if response.getcode() != 200:
        print("ERROR: Got" + response.getcode() + " response code")
        raise

    html = response.read()

    if verbosity > 2:
        print("Downloaded:")
        print(html)

    if verbosity > 0:
        print(" * Done.")

    return html

def download_bib(opener, user_agent, biburl, verbosity):
    if biburl is not None:
        bib_data = get_url(opener, biburl, verbosity, user_agent)
        return bib_data
    return None

def download_pdf(opener, user_agent, pdfurl, verbosity):
    if pdfurl is not None:
        pdf_data = get_url(opener, pdfurl, verbosity, user_agent, ["application/pdf", "application/octet-stream"])
        return pdf_data
    return None

def download_pdf_andor_bib(opener, user_agent, pdfurl, biburl, verbosity):
    return \
        download_bib(opener, user_agent, biburl, verbosity), \
        download_pdf(opener, user_agent, pdfurl, verbosity)

# Call the right handler for the specified URL and returns a tuple
# <is_url_handled, bib_data, pdf_data>, where:
#  - is_url_handled is True if the URL type is known so has a handler, and bib_data and pdf_data store the downloaded data
#  - is_url_handled is False if this type of URL is unknown, and bib_data and pdf_data store nothing
def handle_url(url, handlers, opener, user_agent, verbosity, bib_downl, pdf_downl):
    parsed_url = urlparse(url)
    if verbosity > 0:
        print("Paper's URL:", parsed_url)
    domain = parsed_url.netloc

    # This is used to initialize the BeautifoulSoup HTML parser.
    parser = "lxml"
    soup = None
    index_html = None

    # For most handled URLs, the handlers get a parsed index.html object. But,
    # for others (e.g., IACR ePrint), the handler doesn't need to parse the
    # page at all since the .pdf and .bib file links are derived directly from
    # the URL itself.
    no_index_html = set()
    no_index_html.add("eprint.iacr.org")

    # e.g., We don't need to download the index.html page for IACR ePrint
    if domain not in no_index_html:
        index_html = get_url(opener, url, verbosity, user_agent)
        soup = BeautifulSoup(index_html, parser)

    if domain in handlers:
        handler = handlers[domain]
        # NOTE: * expands the tuple returned by handler() into individual arguments
        return True, *handler(opener, soup, parsed_url, parser, user_agent, verbosity, bib_downl, pdf_downl)
    else:
        return False, None, None

def dlacm_handler(opener, soup, parsed_url, parser, user_agent, verbosity, bib_downl, pdf_downl):
    path = parsed_url.path.split('/')[2:]
    if len(path) > 1:
        doi = path[-2] + '/' + path[-1]
    elif 'doid' in parsed_url.query:
        doi = '10.1145/' + parsed_url.query.split('=')[1] # 10.1145/doid
    else:
        assert(False)

    if verbosity > 0:
        print("ACM DL paper DOI:", doi)

    # WARNING: Leave these initialized to None, to handle downloading either .bib or .pdf, but not both.
    pdf_data = None
    bibtex = None

    if pdf_downl:
        # First, we scrape the PDF link
        elem = soup.find('a', attrs={"title": "PDF"})
        url_prefix = parsed_url.scheme + '://' + parsed_url.netloc
        pdfurl = url_prefix + elem.get('href')
        if verbosity > 0:
            print("ACM DL paper PDF URL:", pdfurl)
        pdf_data = download_pdf(opener, user_agent, pdfurl, verbosity)

    if bib_downl:
        # Ugh, the new dl.acm.org has no easy way of getting the BibTeX AFAICT, so using something else
        biburl = "http://doi.org/" + doi
        if verbosity > 0:
            print("ACM DL paper bib URL:", biburl)
        bibtex = get_url(opener, biburl, verbosity, user_agent, None, {"Accept": "application/x-bibtex"})

        if verbosity > 1:
            # Assuming UTF8 encoding. Will pay for this later, rest assured.
            print("ACM DL paper BibTeX: ", bibtex.decode("utf-8"))

    return bibtex, pdf_data

#
# DEPRECATED: Since DL ACM website changed in 2019/2020.
#
#def dlacm_handler_old(opener, soup, parsed_url, parser, user_agent, verbosity):
#    paper_id = parsed_url.query.split('=')[1]
#
#    # sometimes the URL might have ?doid=<parentid>.<id> rather than just ?doid=<id>
#    if '.' in paper_id:
#        paper_id = paper_id.split('.')[1]
#
#    if verbosity > 0:
#        print("ACM DL paper ID:", paper_id)
#    # first, we scrape the PDF link
#    elem = soup.find('a', attrs={"name": "FullTextPDF"})
#    url_prefix = parsed_url.scheme + '://' + parsed_url.netloc
#    pdfurl = url_prefix + '/'  + elem.get('href')
#
#    # second, we scrape the .bib link
#    # We use the <meta name="citation_abstract_html_url" content="http://dl.acm.org/citation.cfm?id=28395.28420"> tag in the <head> 
#    elem = soup.find("head").find("meta", attrs={"name": "citation_abstract_html_url"})
#    newurl = urlparse(elem['content'])
#    ids = newurl.query
#    parent_id = ids.split('=')[1].split('.')[0]
#    if verbosity > 0:
#        print("ACM DL parent ID:", parent_id)
#
#    # then, we download the .bib file from, say, https://dl.acm.org/downformats.cfm?id=28420&parent_id=28395&expformat=bibtex
#    biburl = url_prefix + '/downformats.cfm?id=' + paper_id + '&parent_id=' + parent_id + '&expformat=bibtex'
#
#    return download_pdf_andor_bib(opener, user_agent, pdfurl, biburl, verbosity)

def iacreprint_handler(opener, soup, parsed_url, parser, user_agent, verbosity, bib_downl, pdf_downl):
    # let's accept links in both formats
    #  - https://eprint.iacr.org/2015/525.pdf
    #  - https://eprint.iacr.org/2015/525
    path = parsed_url.path[1:]

    # WARNING: Leave these initialized to None, to handle downloading either .bib or .pdf, but not both.
    pdf_data = None
    bibtex   = None

    if pdf_downl:
        if path.endswith(".pdf"):
            path = path[:-4]
            pdfurl = urlunparse(parsed_url)
        else:
            pdfurl = urlunparse(parsed_url) + ".pdf"

        pdf_data = download_pdf(opener, user_agent, pdfurl, verbosity)

    if bib_downl:
        biburl = parsed_url.scheme + '://' + parsed_url.netloc + "/eprint-bin/cite.pl?entry=" + path
        print("Downloading BibTeX from", biburl)
        html = get_url(opener, biburl, verbosity, user_agent)
        bibsoup = BeautifulSoup(html, parser)
        bibtex = bibsoup.find('pre').text.strip()
        bibtex = bibtex.encode('utf-8')

    return bibtex, pdf_data

def sciencedirect_handler(opener, soup, parsed_url, parser, user_agent, verbosity, bib_downl, pdf_downl):
    url_prefix = parsed_url.scheme + '://' + parsed_url.netloc

    # WARNING: Leave these initialized to None, to handle downloading either .bib or .pdf, but not both.
    pdfurl = None
    biburl = None

    if pdf_downl:
        # First, try to find a link to the PDF
        pdf_redirect_url = None
        # Option 1: <head> has a <meta> tag with the link
        elem = soup.find("head").find("meta", attrs={"name": "citation_pdf_url"})
        if elem != None:
            if verbosity > 1:
                print("<head> <meta> PDF elem:", elem)

            pdf_redirect_url = elem['content']
        # Option 2: PDF link appears in an <a> tag
        else:
            print_warning("Could not find 'citation_pdf_url' <meta> in <head>, trying to search for an <a> link with a PDF href...")
            elems = soup.find_all("a")
            for e in elems:
                if "Download full text in PDF" in e.text:
                    pdf_redirect_url = url_prefix + e.get("href")

        # If both approaches failed, exit!
        if not pdf_redirect_url:
            print_error("Failed to find a PDF link")
            sys.exit(1)

        if verbosity > 0:
            click.echo("PDF redirect URL: " + str(pdf_redirect_url))

        html = get_url(opener, pdf_redirect_url, verbosity, user_agent)
        html = html.decode('utf-8')
        substr = "window.location = '"
        pdfurl = html[html.find(substr) + len(substr):]
        pdfurl = pdfurl[0 : pdfurl.find("'")]
        if verbosity > 1:
            click.echo("PDF URL: " + str(pdfurl))

    if bib_downl:
        # Then, try to build a link to the BibTeX file
        elem = soup.find("head").find("meta", attrs={"name": "citation_pii"})
        if verbosity > 1:
            print("<head> <meta> .bib elem:", elem)
        pii = elem['content']
        biburl = url_prefix + "/sdfe/arp/cite?pii=" + pii + "&format=text/x-bibtex&withabstract=True"

        if verbosity > 0:
            click.echo("BibTeX URL: " + str(biburl))

    return download_pdf_andor_bib(opener, user_agent, pdfurl, biburl, verbosity)

def springerlink_handler(opener, soup, parsed_url, parser, user_agent, verbosity, bib_downl, pdf_downl):
    url_prefix = parsed_url.scheme + '://' + parsed_url.netloc
    path = parsed_url.path
    if 'chapter/' in path:
        paper_id = path[len('chapter/'):]
    elif 'book/' in path:
        print_error("We do not yet support book/ in SpringerLink URLs")
    else:
        print_error("Expected chapter/ in SpringerLink URL")
        sys.exit(1)

    print("Paper ID:", paper_id)

    # WARNING: Leave these initialized to None, to handle downloading either .bib or .pdf, but not both.
    pdfurl = None
    biburl = None

    if pdf_downl:
        elem = soup.select_one("#cobranding-and-download-availability-text > div > a")
        if elem is None:
            elem = soup.select_one("#cobranding-and-download-availability-text > div > p > a")
        if verbosity > 1:
            print("HTML for PDF:", elem)

        pdfurl = url_prefix + elem.get('href')
    
    if bib_downl:
        #elem = soup.select_one("#Dropdown-citations-dropdown > ul > li:nth-child(4) > a") # does not work because needs JS
        # e.g. of .bib URL: https://citation-needed.springer.com/v2/references/10.1007/978-3-540-28628-8_20?format=bibtex&flavour=citation
        biburl = 'https://citation-needed.springer.com/v2/references' + paper_id + '?format=bibtex&flavour=citation'

    return download_pdf_andor_bib(opener, user_agent, pdfurl, biburl, verbosity)

# https://arxiv.org/pdf/XXXX.XXXX.pdf
# https://arxiv.org/abs/XXXX.XXXX
def arxiv_handler(opener, soup, parsed_url, parser, user_agent, verbosity, bib_downl, pdf_downl):
    if '.pdf' in parsed_url.path:
        paper_id = parsed_url.path[len('/pdf/'):-len('.pdf')]    
    elif '/abs' in parsed_url.path:
        paper_id = parsed_url.path[len('/abs/'):]
    else:
        assert(False) # not implemented yet
    
    paper_id = paper_id.strip('/')
    
    if verbosity > 0:
        print("arXiv paper ID:", paper_id)
    
    # WARNING: Leave these initialized to None, to handle downloading either .bib or .pdf, but not both.
    pdfurl = None
    bibtex = None

    if pdf_downl:
        pdfurl = 'https://arxiv.org/pdf/%s.pdf' % paper_id

    if bib_downl:
        index_html = get_url(opener, 'https://arxiv2bibtex.org/?q=' + paper_id + '&format=bibtex', verbosity, user_agent)
        soup = BeautifulSoup(index_html, parser)
        bibtex = soup.select_one('#bibtex > textarea').get_text().strip()
        bibtex = bibtex.encode('utf-8')

    return bibtex, download_pdf(opener, user_agent, pdfurl, verbosity)

def epubssiam_handler(opener, soup, parsed_url, parser, user_agent, verbosity, bib_downl, pdf_downl):
    url_prefix = parsed_url.scheme + '://' + parsed_url.netloc
    path = parsed_url.path

    splitpath = path.split('/')
    if '/doi/abs' in path:
        doi_start = splitpath[3]
        doi_end   = splitpath[4]
    else: # if just /doi in URL
        doi_start = splitpath[2]
        doi_end   = splitpath[3]
    doi       = doi_start + '/' + doi_end
    doi_alt   = doi_start + '%2F' + doi_end
    
    if verbosity > 0:
        print("Extracted DOI:", doi)

    # WARNING: Leave these initialized to None, to handle downloading either .bib or .pdf, but not both.
    pdfurl = None
    biburl = None

    if pdf_downl:
        # e.g., URL to download BibTeX for doi:10.1137/S0097539790187084
        # https://epubs.siam.org/action/downloadCitation?doi=10.1137%2FS0097539790187084&format=bibtex&include=cit
        pdfurl = url_prefix + '/doi/pdf/' + doi

    if bib_downl:
        biburl = url_prefix + '/action/downloadCitation?doi=' + doi_alt + '&format=bibtex&include=cit'

    return download_pdf_andor_bib(opener, user_agent, pdfurl, biburl, verbosity)

def ieeexplore_handler(opener, soup, parsed_url, parser, user_agent, verbosity, bib_downl, pdf_downl):
    url_prefix = parsed_url.scheme + '://' + parsed_url.netloc

    path = parsed_url.path
    if verbosity > 1:
        print('path: ', path)

    splitpath = path.split('/')
    if verbosity > 1:
        print('splitpath: ', splitpath)

    arnum = splitpath[-1]
    if verbosity > 1:
        print('arnumber: ', arnum)

    # WARNING: Leave these initialized to None, to handle downloading either .bib or .pdf, but not both.
    pdfurl = None
    biburl = None

    if pdf_downl:
        # To get the PDF link, we have to download an HTML page which puts the PDF in an iframe. Doh.
        # e.g., https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=7958589
        # (How do you come up with this design?)
        pdf_iframe_url = url_prefix + '/stamp/stamp.jsp?tp=&arnumber=' + str(arnum)
        html = get_url(opener, pdf_iframe_url, verbosity, user_agent)
        pdfsoup = BeautifulSoup(html, parser)
        elem = pdfsoup.find('iframe')
        if elem == None:
            print_error("Parsing failed! Could not find iframe in stamp.jsp HTML.")
            sys.exit(1)

        # TODO(Alin): If we keep getting more errors, try direct link: https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&isnumber=&arnumber=$arnum

        # e.g., PDF URL
        # https://ieeexplore.ieee.org/ielx7/7957740/7958557/07958589.pdf
        # e.g., BibTeX URL
        # https://ieeexplore.ieee.org/xpl/downloadCitations?recordIds=7958589&download-format=download-bibtex&citations-format=citation-only
        if verbosity > 1:
            print("Parsed iframe tag:", elem)

        pdfurl = elem['src']

    if bib_downl:
        biburl = url_prefix + '/xpl/downloadCitations?recordIds=' + arnum + '&download-format=download-bibtex&citations-format=citation-abstract'

    bib_data, pdf_data = download_pdf_andor_bib(opener, user_agent, pdfurl, biburl, verbosity)

    if bib_downl:
        # clean the .bib file, which IEEExplore kindly serves with <br>'s in it
        bib_data = bib_data.replace(b'<br>', b'')

    return bib_data, pdf_data
