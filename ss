#!/bin/zsh
# Command-line search: ss the slides about attention from last semester
cd "${0:A:h}" && exec .venv/bin/python -m semsearch.cli "$@"
