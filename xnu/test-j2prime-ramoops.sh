#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
out=$(mktemp)
trap 'rm -f "$out"' EXIT
cc -std=c11 -O2 -Wall -Wextra -Werror \
  -I"$root/xnu" \
  "$root/xnu/j2prime_ramoops.c" \
  "$root/xnu/test_j2prime_ramoops.c" \
  -o "$out"
"$out"
