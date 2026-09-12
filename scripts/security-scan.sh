#!/bin/sh
set -eu
IMAGE="${1:-haushaltpro:0.21.0}"
command -v pip-audit >/dev/null 2>&1 || { echo "pip-audit fehlt: python -m pip install pip-audit" >&2; exit 2; }
command -v trivy >/dev/null 2>&1 || { echo "trivy fehlt: https://trivy.dev/latest/getting-started/installation/" >&2; exit 2; }
echo "== pip-audit =="
pip-audit -r requirements.txt --strict
echo "== Trivy filesystem =="
trivy fs --scanners vuln,misconfig,secret --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 .
echo "== Trivy image =="
trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 "$IMAGE"
