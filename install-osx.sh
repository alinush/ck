#!/bin/bash
set -e

comp_dir=`brew --prefix`/etc/bash_completion.d/

# Does NOT overwrite existing files
cp -n bash_completion.d/ck $comp_dir || { echo "ERROR: Please manually remove previous completion file from ${comp_dir}ck"; exit 1; }
