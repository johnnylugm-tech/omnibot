#!/usr/bin/env bash
# Temporary script to invoke ruff and dump output to a file.
set -u
exec /Users/johnny/Library/Python/3.9/bin/ruff check 03-development/src/ > /tmp/ruff_out.txt 2>&1
