#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <frontend-url>" >&2
  exit 1
fi

frontend_url="${1%/}"
html_file="$(mktemp)"
trap 'rm -f "${html_file}"' EXIT

status="$(curl -sS -o "${html_file}" -w '%{http_code}' "${frontend_url}")"
if [[ "${status}" != "200" ]]; then
  echo "Frontend smoke test failed with status ${status}" >&2
  cat "${html_file}" >&2
  exit 1
fi

if ! grep -Eq 'Get started for free|Sign in|AI-powered ticket assignment' "${html_file}"; then
  echo "Frontend smoke test could not find expected landing-page content" >&2
  cat "${html_file}" >&2
  exit 1
fi

echo "Frontend smoke test passed"
