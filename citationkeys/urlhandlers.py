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
        if restrict_content_type is not None and content_type.startswith(restrict_content_type) is False:
            raise RuntimeError("Expected this to be URL to a PDF, but got '" + content_type + "' Content-Type")
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
        pdf_data = get_url(opener, pdfurl, verbosity, user_agent, "application/pdf")
        return pdf_data
    return None

def download_pdf_andor_bib(opener, user_agent, pdfurl, biburl, verbosity):
    return \
        download_bib(opener, user_agent, biburl, verbosity), \
        download_pdf(opener, user_agent, pdfurl, verbosity)

def dlacm_handler(opener, soup, parsed_url, ck_bib_dir, parser, user_agent, verbosity):
    path = parsed_url.path.split('/')[2:]
    if len(path) > 1:
        doi = path[-2] + '/' + path[-1]
    elif 'doid' in parsed_url.query:
        doi = '10.1145/' + parsed_url.query.split('=')[1] # 10.1145/doid
    else:
        assert(False)

    if verbosity > 0:
        print("ACM DL paper DOI:", doi)
    # first, we scrape the PDF link
    elem = soup.find('a', attrs={"title": "PDF"})
    url_prefix = parsed_url.scheme + '://' + parsed_url.netloc
    pdfurl = url_prefix + elem.get('href')
    if verbosity > 0:
        print("ACM DL paper PDF URL:", pdfurl)

    pdf_data = download_pdf(opener, user_agent, pdfurl, verbosity)

    # ugh, the new dl.acm.org has no easy way of getting the BibTeX AFAICT, so using something else
    biburl = "http://doi.org/" + doi
    if verbosity > 0:
        print("ACM DL paper bib URL:", biburl)
    bibtex = get_url(opener, biburl, verbosity, user_agent, None, {"Accept": "application/x-bibtex"})

    if verbosity > 1:
        # Assuming UTF8 encoding. Will pay for this later, rest assured.
        bibtex_str = bibtex.decode("utf-8")
        print("ACM DL paper BibTeX: ", bibtex_str)

    return bibtex, pdf_data

# Deprecated, since DL ACM website changed in 2019/2020.
def dlacm_handler_old(opener, soup, parsed_url, ck_bib_dir, parser, user_agent, verbosity):
    paper_id = parsed_url.query.split('=')[1]

    # sometimes the URL might have ?doid=<parentid>.<id> rather than just ?doid=<id>
    if '.' in paper_id:
        paper_id = paper_id.split('.')[1]

    if verbosity > 0:
        print("ACM DL paper ID:", paper_id)
    # first, we scrape the PDF link
    elem = soup.find('a', attrs={"name": "FullTextPDF"})
    url_prefix = parsed_url.scheme + '://' + parsed_url.netloc
    pdfurl = url_prefix + '/'  + elem.get('href')

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

    return download_pdf_andor_bib(opener, user_agent, pdfurl, biburl, verbosity)

def iacreprint_handler(opener, soup, parsed_url, ck_bib_dir, parser, user_agent, verbosity):
    # let's accept links in both formats
    #  - https://eprint.iacr.org/2015/525.pdf
    #  - https://eprint.iacr.org/2015/525
    path = parsed_url.path[1:]
    if path.endswith(".pdf"):
        path = path[:-4]
        pdfurl = urlunparse(parsed_url)
    else:
        pdfurl = urlunparse(parsed_url) + ".pdf"

    pdf_data = download_pdf(opener, user_agent, pdfurl, verbosity)

    biburl = parsed_url.scheme + '://' + parsed_url.netloc + "/eprint-bin/cite.pl?entry=" + path
    print("Downloading BibTeX from", biburl)
    html = get_url(opener, biburl, verbosity, user_agent)
    bibsoup = BeautifulSoup(html, parser)
    bibtex = bibsoup.find('pre').text.strip()

    return bibtex.encode('utf-8'), pdf_data

def sciencedirect_handler(opener, soup, parsed_url, ck_bib_dir, parser, user_agent, verbosity):
    elem = soup.find("head").find("meta", attrs={"name": "citation_pdf_url"})
    pdf_redirect_url = elem['content']
    if verbosity > 0:
        click.echo("PDF redirect URL: " + str(pdf_redirect_url))

    elem = soup.find("head").find("meta", attrs={"name": "citation_pii"})
    pii = elem['content']
    url_prefix = parsed_url.scheme + '://' + parsed_url.netloc
    biburl = url_prefix + "/sdfe/arp/cite?pii=" + pii + "&format=text/x-bibtex&withabstract=True"

    if verbosity > 0:
        click.echo("BibTeX URL: " + str(biburl))

    html = get_url(opener, pdf_redirect_url, verbosity, user_agent)
    html = html.decode('utf-8')
    substr = "window.location = '"
    pdfurl = html[html.find(substr) + len(substr):]
    pdfurl = pdfurl[0 : pdfurl.find("'")]
    if verbosity > 0:
        click.echo("PDF URL: " + str(pdfurl))

    return download_pdf_andor_bib(opener, user_agent, pdfurl, biburl, verbosity)

def springerlink_handler(opener, soup, parsed_url, ck_bib_dir, parser, user_agent, verbosity):
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

    return download_pdf_andor_bib(opener, user_agent, pdfurl, biburl, verbosity)

# https://arxiv.org/pdf/XXXX.XXXX.pdf
# https://arxiv.org/abs/XXXX.XXXX
def arxiv_handler(opener, soup, parsed_url, ck_bib_dir, parser, user_agent, verbosity):
    if '.pdf' in parsed_url.path:
        paper_id = parsed_url.path[len('/pdf/'):-len('.pdf')]    
    elif '/abs' in parsed_url.path:
        paper_id = parsed_url.path[len('/abs/'):]
    else:
        assert(False) # not implemented yet
    
    paper_id = paper_id.strip('/')
    
    print("Paper ID:", paper_id)

    pdfurl = 'https://arxiv.org/pdf/%s.pdf' % paper_id
    index_html = get_url(opener, 'https://arxiv2bibtex.org/?q=' + paper_id + '&format=bibtex', verbosity, user_agent)
    soup = BeautifulSoup(index_html, parser)
    bibtex = soup.select_one('#bibtex > textarea').get_text().strip()

    #elem = soup.select_one("#Dropdown-citations-dropdown > ul > li:nth-child(4) > a") # does not work because needs JS
    # e.g. of .bib URL: https://citation-needed.springer.com/v2/references/10.1007/978-3-540-28628-8_20?format=bibtex&flavour=citation

    return bibtex.encode('utf-8'), download_pdf(opener, user_agent, pdfurl, verbosity)


def epubssiam_handler(opener, soup, parsed_url, ck_bib_dir, parser, user_agent, verbosity):
    url_prefix = parsed_url.scheme + '://' + parsed_url.netloc
    path = parsed_url.path

    splitpath = path.split('/')
    doi_start = splitpath[2]
    doi_end   = splitpath[3]
    doi       = doi_start + '/' + doi_end
    doi_alt   = doi_start + '%2F' + doi_end
    
    if verbosity > 0:
        print("Extracted DOI:", doi)

    # e.g., URL to download BibTeX for doi:10.1137/S0097539790187084
    # https://epubs.siam.org/action/downloadCitation?doi=10.1137%2FS0097539790187084&format=bibtex&include=cit
    pdfurl = url_prefix + '/doi/pdf/' + doi
    biburl = url_prefix + '/action/downloadCitation?doi=' + doi_alt + '&format=bibtex&include=cit'

    return download_pdf_andor_bib(opener, user_agent, pdfurl, biburl, verbosity)

def ieeexplore_handler(opener, soup, parsed_url, ck_bib_dir, parser, user_agent, verbosity):
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
    biburl = url_prefix + '/xpl/downloadCitations?recordIds=' + arnum + '&download-format=download-bibtex&citations-format=citation-abstract'

    bib_data, pdf_data = download_pdf_andor_bib(opener, user_agent, pdfurl, biburl, verbosity)

    # clean the .bib file, which IEEExplore kindly serves with <br>'s in it
    bib_data = bib_data.replace(b'<br>', b'')
    return bib_data, pdf_data
