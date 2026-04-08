#!/bin/bash
set -e

which brew &>/dev/null || { echo "ERROR: 'brew' is not installed"; exit 1; }

comp_dir=`brew --prefix`/etc/bash_completion.d/

# Remove existing file or symlink if present
if [ -e "${comp_dir}ck" ] || [ -L "${comp_dir}ck" ]; then
    read -p "Would you like to remove the existing file in ${comp_dir}ck? [y/N]: " ANS
    if [ "$ANS" = "y" ]; then
        rm "${comp_dir}ck"
    else
        echo "Keeping existing file. Exiting."
        exit 0
    fi
fi

ln -s "$(cd "$(dirname "$0")" && pwd)/bash_completion.d/ck" "${comp_dir}ck" || { echo "ERROR: Something went wrong. Couldn't symlink to ${comp_dir}ck."; exit 1; }
