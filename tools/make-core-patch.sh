#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Writes the working tree's core changes that are not in the maintained patches below NAME as
# tools/eglantine-patches/NAME.patch: apply every lower-numbered patch to a clean copy of the
# submodule's commit and diff this tree against it.
#   tools/make-core-patch.sh 0006-description
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
name=$1
number=${name%%-*}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
git -C "$root/Eglantine" archive --format=tar HEAD | tar -x -C "$work"
git -C "$work" init -q && git -C "$work" add -A && git -C "$work" -c user.name=p -c user.email=p commit -q -m base
for patch in "$root"/tools/eglantine-patches/*.patch; do
    patch_number=$(basename "$patch"); patch_number=${patch_number%%-*}
    [[ $patch_number < $number ]] || continue
    git -C "$work" apply "$patch"
done
git -C "$work" add -A && git -C "$work" -c user.name=p -c user.email=p commit -q -m lower
rsync -a --delete --exclude .git "$root/Eglantine/" "$work/"
git -C "$work" add -A
git -C "$work" diff --cached --no-color > "$root/tools/eglantine-patches/$name.patch"
wc -l "$root/tools/eglantine-patches/$name.patch"
