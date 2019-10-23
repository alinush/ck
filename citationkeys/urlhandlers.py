#!/usr/bin/env python3

# NOTE: Alphabetical order please
from bibtexparser.bwriter import BibTexWriter
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
import subprocess
import sys
import tempfile
import urllib

def get_url(opener, url, verbosity, user_agent):
    if verbosity > 0:
        print("Downloading URL:", url)

    if user_agent is not None:
        response = opener.open(Request(url, headers={'User-Agent': user_agent}))
    else:
        response = opener.open(url)

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

def download_pdf(opener, user_agent, pdfurl, destpdffile, verbosity):
    download_pdf_andor_bib(opener, user_agent, pdfurl, destpdffile, None, None, verbosity)

def download_pdf_andor_bib(opener, user_agent, pdfurl, destpdffile, biburl, destbibfile, verbosity):
    if pdfurl is not None:
        data = get_url(opener, pdfurl, verbosity, user_agent)

        with open(destpdffile, 'wb') as output:
            output.write(data)

    if biburl is not None:
        data = get_url(opener, biburl, verbosity, user_agent)

        with open(destbibfile, 'wb') as output:
            output.write(data)

def dlacm_handler(opener, soup, parsed_url, ck_bib_dir, destpdffile, destbibfile, citation_key, parser, user_agent, verbosity):
    paper_id = parsed_url.query.split('=')[1]

    # sometimes the URL might have ?doid=<parentid>.<id> rather than just ?doid=<id>
    if '.' in paper_id:
        paper_id = paper_id.split('.')[1]

    if verbosity > 0:
        print("ACM DL paper ID:", paper_id)
    # first, we scrape the PDF link
    elem = soup.find('a', attrs={"name": "FullTextPDF"})

    # then, we download the PDF
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

    download_pdf_andor_bib(opener, user_agent, pdfurl, destpdffile, biburl, destbibfile, verbosity)

def iacreprint_handler(opener, soup, parsed_url, ck_bib_dir, destpdffile, destbibfile, citation_key, parser, user_agent, verbosity):
    # let's accept links in both formats
    #  - https://eprint.iacr.org/2015/525.pdf
    #  - https://eprint.iacr.org/2015/525
    path = parsed_url.path[1:]
    if path.endswith(".pdf"):
        path = path[:-4]
        pdfurl = urlunparse(parsed_url)
    else:
        pdfurl = urlunparse(parsed_url) + ".pdf"

    download_pdf(opener, user_agent, pdfurl, destpdffile, verbosity)

    biburl = parsed_url.scheme + '://' + parsed_url.netloc + "/eprint-bin/cite.pl?entry=" + path
    print("Downloading BibTeX from", biburl)
    html = get_url(opener, biburl, verbosity, user_agent)
    bibsoup = BeautifulSoup(html, parser)
    bibtex = bibsoup.find('pre').text.strip()

    with open(destbibfile, 'wb') as output:
        output.write(bibtex.encode('utf-8'))

def springerlink_handler(opener, soup, parsed_url, ck_bib_dir, destpdffile, destbibfile, citation_key, parser, user_agent, verbosity):
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

    download_pdf_andor_bib(opener, user_agent, pdfurl, destpdffile, biburl, destbibfile, verbosity)

def epubssiam_handler(opener, soup, parsed_url, ck_bib_dir, destpdffile, destbibfile, citation_key, parser, user_agent, verbosity):
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

    download_pdf_andor_bib(opener, user_agent, pdfurl, destpdffile, biburl, destbibfile, verbosity)

def ieeexplore_handler(opener, soup, parsed_url, ck_bib_dir, destpdffile, destbibfile, citation_key, parser, user_agent, verbosity):
    url_prefix = parsed_url.scheme + '://' + parsed_url.netloc
    path = parsed_url.path

    splitpath = path.split('/')
    arnum = splitpath[2]

    # To get the PDF link, we have to download an HTML page which puts the PDF in an iframe. Doh.
    # e.g., https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=7958589
    # (How do you come up with this design?)
    pdf_iframe_url = url_prefix + '/stamp/stamp.jsp?tp=&arnumber=' + str(arnum)
    html = get_url(opener, pdf_iframe_url, verbosity, user_agent)
    pdfsoup = BeautifulSoup(html, parser)
    elem = pdfsoup.find('iframe')

    # e.g., PDF URL
    # https://ieeexplore.ieee.org/ielx7/7957740/7958557/07958589.pdf
    # e.g., BibTeX URL
    # https://ieeexplore.ieee.org/xpl/downloadCitations?recordIds=7958589&download-format=download-bibtex&citations-format=citation-only
    if verbosity > 1:
        print("Parsed iframe tag:", elem)

    pdfurl = elem['src']
    biburl = url_prefix + '/xpl/downloadCitations?recordIds=' + arnum + '&download-format=download-bibtex&citations-format=citation-abstract'

    tmpbibf = tempfile.NamedTemporaryFile(delete=True)
    tmpbibfile = tmpbibf.name
    download_pdf_andor_bib(opener, user_agent, pdfurl, destpdffile, biburl, tmpbibfile, verbosity)

    # clean the .bib file, which IEEExplore kindly serves with <br>'s in it
    bibtex = file_to_string(tmpbibfile)
    tmpbibf.close()
    bibtex = bibtex.replace('<br>', '')
    string_to_file(bibtex, destbibfile)
