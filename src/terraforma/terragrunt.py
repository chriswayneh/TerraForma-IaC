import os
import re
from pathlib import Path

from terraforma.artifacts import PROJECT_GITIGNORE, checksum_document, digest_text, json_document
from terraforma.generator import ArtifactCleanupError, TerraformGenerator
from terraforma.hcl import value_hcl
from terraforma.project import ProjectSpecification, compile_project


def terragrunt_artifacts(units: dict[str, ProjectSpecification]) -> dict[str, str]:
    if not 1 <= len(units) <= 12:
        raise ValueError("Choose between one and twelve independently configured units.")
    files = {".gitignore": PROJECT_GITIGNORE + ".terragrunt-cache/\n"}
    summaries = []
    for name, specification in sorted(units.items()):
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", name) or name in {
            "con",
            "prn",
            "aux",
            "nul",
            *(f"com{i}" for i in range(1, 10)),
            *(f"lpt{i}" for i in range(1, 10)),
        }:
            raise ValueError(
                "Use a short lowercase unit name without paths or reserved device names."
            )
        project = compile_project(specification)
        module = TerraformGenerator(specification.recipe).generate()
        module_id = digest_text(json_document(module))
        for filename, content in module.items():
            files[f"modules/{module_id}/{filename}"] = content
        unit_path = f"units/{name}"
        source = "../../modules/" + module_id
        files[f"{unit_path}/terragrunt.hcl"] = (
            'terragrunt_version_constraint = "= 1.1.6"\n'
            'terraform_version_constraint  = ">= 1.6, < 2.0"\n\n'
            'terraform {\n  source = "${get_terragrunt_dir()}/'
            + source
            + '"\n}\n\n'
            + "inputs = "
            + value_hcl(project["terraform_inputs"])
            + "\n"
        )
        files[f"{unit_path}/terraforma.project.json"] = json_document(project["specification"])
        summaries.append(
            {
                "name": name,
                "module": module_id,
                "target": project["target"],
                "required_secret_environment_variables": project[
                    "required_secret_environment_variables"
                ],
            }
        )
    files["terraforma.units.json"] = json_document(
        {
            "schema_version": 1,
            "units": summaries,
            "state": "local-per-unit-cache",
            "execution": "not-performed",
            "dependencies": "not-inferred",
        }
    )
    files["README.md"] = (
        "# TerraForma environment units\n\n"
        "Each unit contains its validated non-secret configuration. Identical recipes share a local module. "
        "Unit names organize configurations; they do not change account, region, resource names or environment inputs.\n\n"
        "Review terraforma.units.json and each saved project before running anything. "
        "Install Terragrunt separately and select Terraform explicitly with TG_TF_PATH. "
        "No command was executed during export.\n\n"
        "State remains local in each unit's .terragrunt-cache. Preserve that directory across runs; "
        "deleting it can lose the state needed to manage created resources. "
        "Configure reviewed remote state before team or production use. This export creates no backend, "
        "dependency, hook, credential or permission. Never run all units without reviewing every target.\n\n"
        "Supply each unit's declared TF_VAR secrets externally. Environment values can override Terragrunt inputs. "
        "Plan files and state can contain secrets. Keep them out of source control.\n"
    )
    files["SHA256SUMS.txt"] = checksum_document(files)
    return files


def write_terragrunt_bundle(files: dict[str, str], directory: Path) -> Path:
    if not files:
        raise ValueError("Bundle content must not be empty.")
    for name, content in files.items():
        parts = name.split("/")
        if any(part in {"", ".", ".."} for part in parts) or "\\" in name or ":" in name:
            raise ValueError("Bundle paths must stay inside the selected directory.")
        if not isinstance(content, str):
            raise TypeError("Bundle content must be text.")
    destination = directory.absolute()
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    created_files = []
    created_dirs = {destination}
    try:
        for name, content in files.items():
            path = destination / name
            for parent in reversed(path.parent.parents):
                if (
                    parent == destination or destination in parent.parents
                ) and parent not in created_dirs:
                    parent.mkdir(mode=0o700)
                    created_dirs.add(parent)
            if path.parent not in created_dirs:
                path.parent.mkdir(mode=0o700)
                created_dirs.add(path.parent)
            with open(
                path,
                "x",
                encoding="utf-8",
                newline="\n",
                opener=lambda name, flags: os.open(name, flags, 0o600),
            ) as stream:
                created_files.append(path)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
    except BaseException as failure:
        remaining = []
        for path in reversed(created_files):
            try:
                path.unlink()
            except OSError:
                remaining.append(str(path.relative_to(destination)))
        for path in sorted(created_dirs, key=lambda item: len(item.parts), reverse=True):
            try:
                path.rmdir()
            except OSError:
                remaining.append(str(path.relative_to(destination)))
        if remaining:
            raise ArtifactCleanupError(remaining) from failure
        raise
    return destination
