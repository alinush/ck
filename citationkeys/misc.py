#!/usr/bin/env python3

# NOTE: Alphabetical order please
from pprint import pprint

# NOTE: Alphabetical order please
import os
import sys

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

    return sorted(cks);

def find_tagged_pdfs(ck_tag_subdir, verbosity):
    tagged_pdfs = set()
    for relpath in os.listdir(ck_tag_subdir):
        fullpath = os.path.join(ck_tag_subdir, relpath)
        citation_key, extension = os.path.splitext(relpath)
        #filename = os.path.basename(filepath)

        if os.path.isdir(fullpath):
            tagged_pdfs.update(find_tagged_pdfs(fullpath, verbosity))
        elif os.path.islink(fullpath):
            if verbosity > 1:
                print("Symlink:", fullpath)
            if extension.lower() == ".pdf":
                realpath = os.readlink(fullpath)
                if verbosity > 1:
                    print(' \->', realpath)
                tagged_pdfs.add(realpath)

    return tagged_pdfs

def find_untagged_pdfs(ck_bib_dir, ck_tag_dir, verbosity):
    tagged_pdfs = find_tagged_pdfs(ck_tag_dir, verbosity)
    untagged = set()

    if verbosity > 1:
        print("Tagged papers:", tagged_pdfs)

    cks = list_cks(ck_bib_dir)
    for ck in cks:
        filepath = os.path.join(ck_bib_dir, ck + ".pdf")
        #filename = os.path.basename(filepath)

        if os.path.exists(filepath):
            if filepath not in tagged_pdfs:
                untagged.add((filepath, ck))

    return untagged

def get_tags(tagdir, prefix=''):
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
        tags.extend(get_tags(curdir, fulltag))

    return sorted(tags)

def print_tags(ck_tag_dir):
    sys.stdout.write("Tags: ")
    tags = get_tags(ck_tag_dir)
    print(tags);
    # TODO: pretty print somehow
    #for t in tags: 
    #    print(t)
    print()

def prompt_for_tags(prompt):
    tags_str = prompt_user(prompt)
    tags = tags_str.split(',')

    tags = [t.strip() for t in tags]
    tags = filter(lambda t: len(t) > 0, tags)
    return tags

def tag_paper(ck_tag_dir, ck_bib_dir, citation_key, tag):
    print("Tagging", citation_key, "with tag", tag, "...")

    pdf_tag_dir = os.path.join(ck_tag_dir, tag)
    # TODO: if dir doesn't exist, prompt user to create it, unless --yes option is passed
    os.makedirs(pdf_tag_dir, exist_ok=True)

    pdfname = citation_key + ".pdf"
    os.symlink(os.path.join(ck_bib_dir, pdfname), os.path.join(pdf_tag_dir, pdfname))
