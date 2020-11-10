#!/bin/bash
set -e

which brew &>/dev/null || { echo "ERROR: 'brew' is not installed"; exit 1; }

comp_dir=`brew --prefix`/etc/bash_completion.d/

# Does NOT overwrite existing files
if [ -f "${comp_dir}ck" ]; then
    read -p "Would you like to remove the existing file in ${comp_dir}ck? [y/N]: " ANS
    if [ "$ANS" = "y" ]; then
        rm "${comp_dir}ck"
    fi
fi

cp -n bash_completion.d/ck $comp_dir || { echo "ERROR: Something went wrong. Couldn't copy to ${comp_dir}ck. Perhaps the previous completion file was not successfully removed."; exit 1; }
