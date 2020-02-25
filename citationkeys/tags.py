#!/usr/bin/env python3

# NOTE: Alphabetical order please
from datetime import datetime
from pprint import pprint

# NOTE: Alphabetical order please
import bibtexparser
import click
import os
import sys
import traceback

# returns a map of CK to its list of tags
def find_tagged_pdfs(ck_tag_subdir, verbosity):
    pdfs = dict()
    find_tagged_pdfs_helper(ck_tag_subdir, ck_tag_subdir, pdfs, verbosity)
    return pdfs

def find_tagged_pdfs_helper(root_tag_dir, tag_subdir, pdfs, verbosity):
    for relpath in os.listdir(tag_subdir):
        fullpath = os.path.join(tag_subdir, relpath)

        if os.path.isdir(fullpath):
            find_tagged_pdfs_helper(root_tag_dir, fullpath, pdfs, verbosity)
        elif os.path.islink(fullpath):
            citation_key, extension = os.path.splitext(relpath)
            tagname = os.path.relpath(os.path.dirname(fullpath), root_tag_dir)

            if verbosity > 1:
                print("CK:", citation_key)
                print("Tagname:", tagname)
                print("Symlink:", fullpath)

            if extension.lower() == ".pdf":
                if citation_key not in pdfs:
                    pdfs[citation_key] = []
                pdfs[citation_key].append(tagname)

# @param    tagged_cks  a list of CKs that are tagged already 
#           (i.e., just call keys() on the return value of find_tagged_pdfs())
def find_untagged_pdfs(ck_bib_dir, ck_tag_dir, cks, tagged_cks, verbosity):
    untagged = set()

    if verbosity > 2:
        print("Tagged papers:", sorted(tagged_cks))

    for ck in cks:
        filepath = os.path.join(ck_bib_dir, ck + ".pdf")
        #filename = os.path.basename(filepath)

        if os.path.exists(filepath):
            if ck not in tagged_cks:
                untagged.add((filepath, ck))

    return untagged

def get_all_tags(tagdir, prefix=''):
    tags = []

    for tagname in os.listdir(tagdir):
        curdir = os.path.join(tagdir, tagname)
        if not os.path.isdir(curdir):
            #print(curdir, "is not a dir")
            continue

        if len(prefix) > 0:
            fulltag = prefix + '/' + tagname
        else:
            fulltag = tagname

        #print("Added " + fulltag)
        tags.append(fulltag)

        #print("Recursing on: " + curdir)
        tags.extend(get_all_tags(curdir, fulltag))

    return sorted(tags)

def print_all_tags(ck_tag_dir):
    tags = get_all_tags(ck_tag_dir)
    print_tags(tags)

def style_tags(taglist):
    tagstr = ""
    for tag in taglist:
        t = click.style('#' + tag, fg='yellow')
        if len(tagstr) == 0:
            tagstr = t
        else:
            tagstr = tagstr + ", " + t

    return tagstr

def print_tags(tags):
    # TODO: pretty print. get width using get_terminal_width
    sys.stdout.write("Tags: ")
    print(tags)

def parse_tags(tags):
    tags = tags.split(',')
    tags = [t.strip() for t in tags]
    tags = filter(lambda t: len(t) > 0, tags)
    return tags

def prompt_for_tags(prompt):
    tags_str = prompt_user(prompt)
    return parse_tags(tags_str)

# if tag is None, removes all tags for the paper
def untag_paper(ck_tag_dir, citation_key, tag=None):
    if tag is not None:
        filepath = os.path.join(ck_tag_dir, tag, citation_key + ".pdf")
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        else:
            return False
    else:
        untagged = False
        filename = citation_key + ".pdf"
        for root, dirs, files in os.walk(ck_tag_dir):
             for name in files:
                if name == filename:
                    os.remove(os.path.join(root, name))
                    untagged = True

        return untagged

def tag_paper(ck_tag_dir, ck_bib_dir, citation_key, tag):
    pdf_tag_dir = os.path.join(ck_tag_dir, tag)
    os.makedirs(pdf_tag_dir, exist_ok=True)

    pdfname = citation_key + ".pdf"
    try:
        os.symlink(os.path.join(ck_bib_dir, pdfname), os.path.join(pdf_tag_dir, pdfname))
        return True
    except FileExistsError:
        return False
    except:
        print("Unexpected error while tagging " + citation_key + " with '" + tag) 
        traceback.print_exc()
        raise
