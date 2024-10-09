#!/usr/bin/env bash
set -eu -o pipefail

# echo to stderr
eecho() { echo "$@" 1>&2; }

DEST_DIR=$(mktemp -d)

(
  cd "${DEST_DIR}"
  mkdir python
  docker run --rm -u "${UID}:${UID}" -v "${DEST_DIR}:/work" -w /work "python:3.12" pip install aiohttp -t ./python >&2
  find python \( -name '__pycache__' -o -name '*.dist-info' \) -type d -print0 | xargs -0 rm -rf
  rm -rf python/bin
  jq -n --arg path "${DEST_DIR}" '{"path":$path}'
)