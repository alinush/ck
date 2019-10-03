#!/bin/bash

scriptdir=$(cd $(dirname $0); pwd -P)

ck_config="$scriptdir/ck-test.config"
ckdir='/tmp/ck'
bibdir="$ckdir/papers"
tagdir="$ckdir/tags"

if [ -n "`find $bibdir -type f`" ]; then
    echo "ERROR: bibdir '$bibdir' should be empty! Please clean."
    exit 1
fi

mkdir -p "$bibdir"
mkdir -p "$tagdir"

urls="\
https://link.springer.com/chapter/10.1007/11818175_27
https://dl.acm.org/citation.cfm?id=62225
https://epubs.siam.org/doi/10.1137/S0097539790187084
https://eprint.iacr.org/2018/721
https://eprint.iacr.org/2018/721.pdf
https://ieeexplore.ieee.org/document/7958589
"


pdf_hashes=(
"86fdfbf63a7433440918e939504b24fd6468256a6700b6db6eb6e8a1d70c33b3"
"70405b39ef003eb4871ec218330b33d0d70e6081d8afe13b5f93ba9eedc34470"
"dynamic_pdf"
"34c933f87d74013981ecbee99253226c2c22c1f1f06de01b5ff6b567e0424c24"
"34c933f87d74013981ecbee99253226c2c22c1f1f06de01b5ff6b567e0424c24"
"d4a2a9c5eedd0837d358c4fc3060e10c7ceb1061f52f8c89e8bb03a447050e8c"
)

bib_hashes=(
"99dae3559882be087149a2ab538a710cc6950653bf32c3ecc6b6c0068a2d66c7"
"d4d3e51b2817a6acd0506fde765c92afeb830ca7f06d414f7f99aad893b3e9f6"
"b6d380ba2eb67b8f4c98f48f2a59f7753cd41c8b51a4ab63fcfcc51fc4ec0501"
"23df56e2a5349ee51baa05d0915fa6e02f2f6474863ccead0dd818ae3aeab2ba"
"23df56e2a5349ee51baa05d0915fa6e02f2f6474863ccead0dd818ae3aeab2ba"
"31592cce2909cd2cbbd66576ae61892eb705cb70c90cd2a7f7d14a032bb73995"
)

sha256hash()
{
   sha256sum "$1" | cut -f 1 -d' ' 
}

i=0
failed_urls=
for url in $urls; do
    if [ -n "$url" ]; then
        echo "Testing URL: $url"

        name=Test${i}
        pdf_hash_actual=${pdf_hashes[$i]}
        bib_hash_actual=${bib_hashes[$i]}

        $scriptdir/ck -c $ck_config -v add "$url" $name
        rc=$?
        i=$(($i+1))

        if [ $rc -ne 0 ]; then
            echo
            echo "ERROR: 'ck add $url'  returned non-zero."
            echo
            failed_urls="$failed_urls
                $url"

            continue
        fi

        pdffile=$bibdir/$name.pdf
        bibfile=$bibdir/$name.bib
        pdf_hash_downl=`sha256hash $pdffile`
        bib_hash_downl=`sha256hash $bibfile`

        if [ "$bib_hash_downl" != "$bib_hash_actual" ]; then
            echo
            echo "ERROR: bib hashes don't match!"
            echo " - Expected  : $bib_hash_actual"
            echo " - Downloaded: $bib_hash_downl"
            echo

            failed_urls="$failed_urls
                $url"
        fi

        if [ "$pdf_hash_actual" != "dynamic_pdf" ]; then
            if [ "$pdf_hash_downl" != "$pdf_hash_actual" ]; then
                echo
                echo "ERROR: PDF hashes don't match!"
                echo " - Expected  : $pdf_hash_actual"
                echo " - Downloaded: $pdf_hash_downl"
                echo

                failed_urls="$failed_urls
                    $url"
                continue
            fi
        else
            if ! pdfinfo "$pdffile"; then
                failed_urls="$failed_urls
                    $url"
                continue
            fi
        fi

        echo
    fi
done

for url in $failed_urls; do
    url=$url
    echo "ERROR: Failed processing paper at URL '$url'"
done

if [ -n "$failed_urls" ]; then
    exit 1
fi
