#!/bin/bash
set -e

which brew &>/dev/null || { echo "ERROR: 'brew' is not installed"; exit 1; }

comp_dir=`brew --prefix`/etc/bash_completion.d/

# Does NOT overwrite existing files
cp -n bash_completion.d/ck $comp_dir || { echo "ERROR: Please manually remove previous completion file from ${comp_dir}ck"; exit 1; }
