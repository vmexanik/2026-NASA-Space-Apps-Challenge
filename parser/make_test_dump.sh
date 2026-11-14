#!/usr/bin/env bash
# Builds the test dump package of Ukraine into data/dump/test-ukraine (the developer's test data is Ukraine only).
# Further arguments go to export_dump.py, for example:
#
#   ./make_test_dump.sh --jobs 8 --method v0-raw --method v1-2026-11-14
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
exec python3 export_dump.py --out data/dump/test-ukraine --name test-ukraine --countries Ukraine "$@"
