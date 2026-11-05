# Terminal demo

The README GIF replays actual output captured from the published
`TerraForma-IaC` **v0.3.0** package on 2026-11-05 (America/Chicago). It uses only
the fictional example project under `examples/aws-web.project.json` (AWS account
ID `123456789012`, private `10.0.0.0/16`). No cloud credentials are read, and
TerraForma does not deploy or plan against a live account. Timing is adjusted
for README readability.

## What it shows

1. Confirm the installed version (`0.3.0`).
2. `doctor` — local dependency availability (generation works offline).
3. `describe --spec examples/aws-web.project.json` — configuration choices for
   the fictional static/web example.
4. `generate --spec … --dir $(mktemp -d)` — writes `main.tf`, `variables.tf`,
   `outputs.tf`, and receipts into a throwaway directory, then shows the head of
   `main.tf`.

## Run it yourself

Use Python 3.11 or newer in an isolated environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install "git+https://github.com/chriswayneh/TerraForma-IaC.git@v0.3.0"

git clone --branch v0.3.0 --depth 1 https://github.com/chriswayneh/TerraForma-IaC.git
cd TerraForma-IaC

.venv/bin/python -m terraforma.cli --version
.venv/bin/python -m terraforma.cli doctor
.venv/bin/python -m terraforma.cli describe --spec examples/aws-web.project.json
OUT="$(mktemp -d)"
.venv/bin/python -m terraforma.cli generate --spec examples/aws-web.project.json --dir "$OUT"
ls "$OUT"
head -n 20 "$OUT/main.tf"
```

Do not set cloud credentials for this walkthrough. TerraForma does not call AWS,
Azure, or Google Cloud during generation.

## Re-record the GIF

Requires [vhs](https://github.com/charmbracelet/vhs) (and `ttyd`):

```bash
./scripts/record-demo.sh
```

The script stages a throwaway directory with `mktemp -d`, installs v0.3.0 into a
temporary venv, records `docs/assets/demo.gif`, and starts no Docker containers.
It never passes credentials on the command line.

## Text alternative

The [Quick start](../README.md#quick-start) first-project steps use the same
fictional account ID in the local web UI.
