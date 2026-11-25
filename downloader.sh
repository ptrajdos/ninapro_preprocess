#!/usr/bin/env bash
# Download all .zip files of one or more NinaPro databases.
#
# Usage:  ./ninapro-dl.sh [-n] [-o OUTDIR] DB_NUMBER [DB_NUMBER ...]
#   -n         dry run: only print the zip URLs found
#   -o OUTDIR  root output directory (default: ./ninapro)
#
# Examples:
#   ./ninapro-dl.sh 2            -> ./ninapro/DB2/s1.zip ...
#   ./ninapro-dl.sh -o data 1 2 5
#   ./ninapro-dl.sh -n 7         -> just list links for DB7

set -euo pipefail

BASE_URL="https://ninapro.hevs.ch"
OUT_ROOT="ninapro"
DRY_RUN=0

usage() {
    sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
}

while getopts ":no:h" opt; do
    case $opt in
        n) DRY_RUN=1 ;;
        o) OUT_ROOT=$OPTARG ;;
        *) usage ;;
    esac
done
shift $((OPTIND - 1))
[[ $# -ge 1 ]] || usage

command -v wget >/dev/null || { echo "wget not found" >&2; exit 1; }

# Turn an href from the page into a full URL.
resolve_url() {
    local href=$1 page_dir=$2
    case $href in
        http://*|https://*) echo "$href" ;;
        //*)                echo "https:$href" ;;
        /*)                 echo "$BASE_URL$href" ;;
        *)                  echo "$page_dir/$href" ;;
    esac
}

failed=()

for db in "$@"; do
    if ! [[ $db =~ ^[0-9]+$ ]]; then
        echo "Skipping '$db': not a number" >&2
        continue
    fi

    page="$BASE_URL/instructions/DB$db.html"
    page_dir="${page%/*}"
    dir="$OUT_ROOT/DB$db"

    echo "==> DB$db: reading $page"
    if ! html=$(wget -qO- "$page"); then
        echo "    Could not fetch page for DB$db" >&2
        failed+=("DB$db (page)")
        continue
    fi

    # Pull out every href that points to a .zip (also with ?download=1 etc.)
    mapfile -t hrefs < <(
        grep -oiE "href=[\"'][^\"']+\.zip([?#][^\"']*)?[\"']" <<<"$html" \
            | sed -E "s/^href=[\"']//I; s/[\"']$//; s/&amp;/\&/g" \
            | sort -u
    )

    if [[ ${#hrefs[@]} -eq 0 ]]; then
        echo "    No zip links found for DB$db" >&2
        continue
    fi
    echo "    Found ${#hrefs[@]} zip file(s)"

    [[ $DRY_RUN -eq 1 ]] || mkdir -p "$dir"

    for href in "${hrefs[@]}"; do
        url=$(resolve_url "$href" "$page_dir")

        if [[ $DRY_RUN -eq 1 ]]; then
            echo "    $url"
            continue
        fi

        name="${url%%[?#]*}"   # drop ?query / #fragment
        name="${name##*/}"     # keep the file name only

        echo "    -> $dir/$name"
        if ! wget -c -q --show-progress --tries=5 --timeout=60 \
                  -O "$dir/$name" "$url"; then
            echo "    FAILED: $url" >&2
            failed+=("$url")
        fi
    done
done

if [[ ${#failed[@]} -gt 0 ]]; then
    echo
    echo "Some downloads failed (run the script again to resume):" >&2
    printf '  %s\n' "${failed[@]}" >&2
    exit 2
fi

echo "Done."