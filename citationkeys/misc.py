#!/usr/bin/env python3

# NOTE: Alphabetical order please
from pprint import pprint

# NOTE: Alphabetical order please
import os
import sys
import traceback

def get_terminal_width():
    rows, columns = os.popen('stty size', 'r').read().split()
    return columns

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

    if verbosity > 0:
        print("Tagged papers:", sorted(tagged_pdfs))

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
    # TODO: pretty print. get width using get_terminal_width
    #for t in tags: 
    #    print(t)
    print()

def parse_tags(tags):
    tags = tags.split(',')
    tags = [t.strip() for t in tags]
    tags = filter(lambda t: len(t) > 0, tags)
    return tags

def prompt_for_tags(prompt):
    tags_str = prompt_user(prompt)
    return parse_tags(tags_str)

def untag_paper(ck_tag_dir, citation_key, tag):
    filepath = os.path.join(ck_tag_dir, tag, citation_key + ".pdf")
    if os.path.exists(filepath):
        os.remove(filepath)
        return True
    else:
        return False

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

def canonicalize_bibtex(ck, bibtex, verbosity):
    assert len(bibtex.entries) == 1
    updated = False

    for i in range(len(bibtex.entries)):
        bib = bibtex.entries[i]

        # make sure the CK in the .bib matches the filename
        bck = bib['ID']
        if bck != ck:
            if verbosity > 1:
                print(ck + ": Replaced unexpected '" + bck + "' CK in .bib file. Fixing...")
            bib['ID'] = ck
            updated = True

        author = bib['author'].replace('\r', '').replace('\n', ' ').strip()
        if bib['author'] != author:
            if verbosity > 1:
                print(ck + ": Stripped author name(s): " + author)
            bib['author'] = author
            updated = True

        title  = bib['title'].strip()
        if title[0] != "{" and title[len(title)-1] != "}":
            title = "{" + title + "}"
        if bib['title'] != title:
            if verbosity > 1:
                print(ck + ": Added brackets to title: " + title)
            bib['title'] = title
            updated = True

    assert type(bib['ID']) == str

    return updated
