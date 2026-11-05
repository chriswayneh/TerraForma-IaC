#!/usr/bin/env bash
# Re-record docs/assets/demo.gif from TerraForma-IaC v0.3.0 offline generate.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/terraforma-demo-XXXXXX")"
VENV="$STAGE/venv"
WORK="$STAGE/work"

cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT

command -v vhs >/dev/null || { echo "vhs is required" >&2; exit 1; }
command -v ttyd >/dev/null || { echo "ttyd is required by vhs" >&2; exit 1; }

mkdir -p "$WORK"
cp "$ROOT/scripts/demo.tape" "$WORK/demo.tape"
# Fixture used by the tape (fictional account id 123456789012).
mkdir -p "$WORK/examples"
cp "$ROOT/examples/aws-web.project.json" "$WORK/examples/"

python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install -q "git+https://github.com/chriswayneh/TerraForma-IaC.git@v0.3.0"

export TF_BIN_DIR="$VENV/bin"
export TF_DEMO_HOME="$WORK"
export PATH="$TF_BIN_DIR:$PATH"

# Offline sanity: no cloud credentials.
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN \
  AZURE_CLIENT_ID AZURE_CLIENT_SECRET AZURE_TENANT_ID \
  GOOGLE_APPLICATION_CREDENTIALS TF_TOKEN_app_terraform_io || true
"$VENV/bin/python" -m terraforma.cli --version >/dev/null
OUT="$STAGE/gen"
"$VENV/bin/python" -m terraforma.cli generate --spec "$WORK/examples/aws-web.project.json" --dir "$OUT" >/dev/null

( cd "$WORK" && vhs demo.tape )

mkdir -p "$ROOT/docs/assets"
cp "$WORK/demo.gif" "$ROOT/docs/assets/demo.gif"
echo "Wrote $ROOT/docs/assets/demo.gif"
