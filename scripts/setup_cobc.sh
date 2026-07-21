#!/usr/bin/env bash
# T1.5 / BL-9: install and validate the GnuCOBOL compile/behavior oracle.
set -euo pipefail

MIN_SUPPORTED="3.1.2"
MAX_MAJOR_EXCLUSIVE="4"
VERSION_OF_RECORD="3.2.0"

verify_cobc() {
    local binary="$1"
    local output banner major minor patch min_major min_minor min_patch

    if ! output=$("$binary" --version 2>&1); then
        echo "unable to run '$binary --version'" >&2
        return 1
    fi
    banner=${output%%$'\n'*}
    if [[ ${banner,,} != *gnucobol* ]]; then
        echo "compiler banner is not GnuCOBOL: $banner" >&2
        return 1
    fi
    if [[ ! $banner =~ ([0-9]+)\.([0-9]+)(\.([0-9]+))? ]]; then
        echo "unable to parse GnuCOBOL version from: $banner" >&2
        return 1
    fi
    major=${BASH_REMATCH[1]}
    minor=${BASH_REMATCH[2]}
    patch=${BASH_REMATCH[4]:-0}
    IFS=. read -r min_major min_minor min_patch <<< "$MIN_SUPPORTED"
    if ((
        major < min_major
        || major >= MAX_MAJOR_EXCLUSIVE
        || (major == min_major && minor < min_minor)
        || (major == min_major && minor == min_minor && patch < min_patch)
    )); then
        echo "unsupported GnuCOBOL $major.$minor.$patch; required >=$MIN_SUPPORTED,<$MAX_MAJOR_EXCLUSIVE (version of record: $VERSION_OF_RECORD)" >&2
        return 1
    fi

    echo "$banner"
    echo "policy: >=$MIN_SUPPORTED,<$MAX_MAJOR_EXCLUSIVE; version of record: $VERSION_OF_RECORD"
}

COBC_BIN=${COBC:-}
if [[ -z $COBC_BIN ]] && command -v cobc >/dev/null 2>&1; then
    COBC_BIN=$(command -v cobc)
fi
if [[ -n $COBC_BIN ]]; then
    echo "cobc already present: $COBC_BIN"
    verify_cobc "$COBC_BIN"
    exit 0
fi

# Install the distribution's supported default. Ubuntu LTS may resolve this to
# 3.1.2 while current distributions resolve it to 3.2.x; both satisfy BL-9.
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo apt-get install -y gnucobol
else
    echo "apt-get not found. Install GnuCOBOL $VERSION_OF_RECORD for your platform," >&2
    echo "then ensure the supported 'cobc' is on PATH (or set COBC)." >&2
    echo "  macOS:   brew install gnu-cobol" >&2
    echo "  Windows: pacman -S mingw-w64-ucrt-x86_64-gnucobol  (msys2 ucrt64)" >&2
    exit 1
fi

echo "installed:"
verify_cobc "$(command -v cobc)"
