pip3 install --break-system-packages --user click pyperclip beautifulsoup4 appdirs fake-useragent bibtexparser lxml weasyprint

# Ghostscript gives us 'ps2pdf', which we need to convert PostScript-only papers (e.g., old IACR
# ePrint ones) into PDFs.
if which brew &>/dev/null; then
    brew install ghostscript
elif which apt &>/dev/null; then
    sudo apt install -y ghostscript
else
    echo "WARNING: Don't know how to install Ghostscript here; please install it so 'ps2pdf' works."
fi
