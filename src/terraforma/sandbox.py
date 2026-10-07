import math
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, ClassVar

from terraforma.file_input import read_regular_bytes
from terraforma.process import run_bounded


class ValidationSandbox:
    file_limit: ClassVar[int] = 8 * 1024 * 1024
    workspace_limit: ClassVar[int] = 32 * 1024 * 1024
    excluded_names: ClassVar[set[str]] = {
        ".terraform",
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".env",
        ".aws",
        ".azure",
        ".config",
        "terraform.tfstate",
        "terraform.tfstate.backup",
        "crash.log",
        ".terraformrc",
        "terraform.rc",
    }

    def __init__(
        self,
        raw_main_hcl: str | None = None,
        *,
        generated_files: dict[str, str] | None = None,
        target_dir: str | Path | None = None,
        timeout: float = 120,
    ):
        if sum(value is not None for value in (raw_main_hcl, target_dir, generated_files)) != 1:
            raise ValueError("Supply exactly one of raw_main_hcl, target_dir, or generated_files.")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Timeout must be finite and positive.")
        self.raw_main_hcl = raw_main_hcl
        self.generated_files = generated_files
        self.target_dir = Path(target_dir).resolve() if target_dir is not None else None
        self.timeout = timeout
        self.temp_dir: str | None = None

    def __enter__(self):
        self.create_environment()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.destroy_environment()

    def create_environment(self) -> str:
        if self.temp_dir is not None:
            raise RuntimeError("This sandbox already has an active workspace.")
        self.temp_dir = tempfile.mkdtemp(prefix="terraforma_sandbox_")
        try:
            destination = Path(self.temp_dir)
            if self.generated_files is not None:
                if "main.tf" not in self.generated_files or set(self.generated_files) - {
                    "main.tf",
                    "variables.tf",
                    "outputs.tf",
                }:
                    raise ValueError("Supply main.tf and only supported Terraform filenames.")
                for name, content in self.generated_files.items():
                    if len(content.encode("utf-8")) > self.file_limit:
                        raise ValueError("Generated file exceeds the 8 MiB limit.")
                    (destination / name).write_text(content, encoding="utf-8")
            elif self.target_dir is None:
                if len(self.raw_main_hcl.encode("utf-8")) > self.file_limit:
                    raise ValueError("Generated file exceeds the 8 MiB limit.")
                (destination / "main.tf").write_text(self.raw_main_hcl, encoding="utf-8")
            else:
                if not self.target_dir.is_dir():
                    raise ValueError("The target must be an existing directory.")
                if not any(self.target_dir.glob("*.tf")) and not any(
                    self.target_dir.glob("*.tf.json")
                ):
                    raise ValueError("The target has no root Terraform configuration files.")
                total = 0
                for current, directories, files in os.walk(self.target_dir, followlinks=False):
                    directories[:] = [
                        name for name in directories if name.lower() not in self.excluded_names
                    ]
                    for name in directories:
                        folder = Path(current) / name
                        if folder.is_symlink() or (
                            hasattr(folder, "is_junction") and folder.is_junction()
                        ):
                            raise ValueError(f"Linked directories are unsupported: {folder.name}")
                    output = destination / Path(current).relative_to(self.target_dir)
                    output.mkdir(parents=True, exist_ok=True)
                    for name in files:
                        normalized = name.lower()
                        if (
                            normalized in self.excluded_names
                            or normalized.endswith(
                                (
                                    ".tfstate",
                                    ".tfstate.backup",
                                    ".tfvars",
                                    ".tfvars.json",
                                    ".tfplan",
                                    ".tfplan.json",
                                    ".plan",
                                    ".plan.json",
                                    ".tfbackend",
                                )
                            )
                            or normalized.startswith(".env")
                            or (normalized.startswith("crash.") and normalized.endswith(".log"))
                        ):
                            continue
                        source = Path(current) / name
                        if source.is_symlink() or not source.is_file():
                            raise ValueError(f"Only regular files can be copied: {source.name}")
                        size = source.stat().st_size
                        if size > self.file_limit or total + size > self.workspace_limit:
                            raise ValueError(
                                "Sandbox input exceeds the 8 MiB file or 32 MiB workspace limit."
                            )
                        content = read_regular_bytes(source, self.file_limit)
                        total += len(content)
                        if len(content) > self.file_limit or total > self.workspace_limit:
                            raise ValueError(
                                "Sandbox input exceeds the 8 MiB file or 32 MiB workspace limit."
                            )
                        (output / name).write_bytes(content)
            return self.temp_dir
        except BaseException:
            self.destroy_environment()
            raise

    @staticmethod
    def _clean(value: str | bytes | None) -> str:
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        clean = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value or "")
        clean = re.sub(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)", "", clean)
        clean = clean.replace("\r\n", "\n").replace("\r", "\n")
        return "".join(
            char
            for char in clean
            if char in "\n\t"
            or (
                ord(char) >= 32
                and not 127 <= ord(char) <= 159
                and char not in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
            )
        ).strip()

    def _execute(self, arguments: list[str]) -> tuple[int, str]:
        environment = os.environ.copy()
        for name in list(environment):
            normalized = name.upper()
            if normalized.startswith(("TF_CLI_ARGS", "TF_VAR_")) or normalized in {
                "TF_DATA_DIR",
                "TF_WORKSPACE",
                "TF_LOG",
                "TF_LOG_PATH",
                "TFLINT_LOG",
                "OPENAI_API_KEY",
            }:
                environment.pop(name)
        environment.update(
            TF_IN_AUTOMATION="1", TF_INPUT="0", TF_DATA_DIR=str(Path(self.temp_dir) / ".terraform")
        )
        try:
            result = run_bounded(
                arguments,
                cwd=self.temp_dir,
                env=environment,
                timeout=self.timeout,
            )
            output = "\n".join(
                part for part in (self._clean(result.stdout), self._clean(result.stderr)) if part
            )
            if result.failure:
                output = f"{result.failure}\n{output}".strip()
            return result.returncode, output
        except OSError as error:
            return -1, f"Unable to launch {Path(arguments[0]).name}: {error.strerror}"

    def execute_checks(self) -> dict[str, Any]:
        if self.temp_dir is None or not Path(self.temp_dir).is_dir():
            raise RuntimeError("Create the sandbox environment before executing checks.")
        errors: list[dict[str, str]] = []
        logs: list[str] = []
        tools = {name: shutil.which(name) for name in ("terraform", "tflint")}
        for name, path in tools.items():
            if path is None:
                errors.append(
                    {
                        "tool": "terraform_validate" if name == "terraform" else "tflint",
                        "raw_output": f"System dependency missing: install '{name}' and add it to PATH.",
                    }
                )
        if errors:
            return {
                "is_valid": False,
                "errors": errors,
                "logs": "\n".join(item["raw_output"] for item in errors),
            }
        config = Path(self.temp_dir) / ".tflint.hcl"
        if not config.exists():
            config.write_text(
                'plugin "terraform" {\n  enabled = true\n  preset = "recommended"\n}\n',
                encoding="utf-8",
            )
        commands = [
            (
                "terraform_validate",
                "terraform init",
                [tools["terraform"], "init", "-backend=false", "-input=false", "-no-color"],
            ),
            (
                "terraform_validate",
                "terraform validate",
                [tools["terraform"], "validate", "-json", "-no-color"],
            ),
            ("tflint", "tflint init", [tools["tflint"], "--init", f"--config={config}"]),
            (
                "tflint",
                "tflint",
                [tools["tflint"], "--recursive", "--format=json", f"--config={config}"],
            ),
        ]
        terraform_ready = True
        lint_ready = True
        for tool, label, arguments in commands:
            if label == "terraform validate" and not terraform_ready:
                continue
            if label == "tflint" and not lint_ready:
                continue
            code, output = self._execute(arguments)
            logs.append(f"[{label}; exit={code}]\n{output}")
            if code != 0:
                errors.append(
                    {
                        "tool": tool,
                        "raw_output": f"{label}:\n{output or 'Command failed without output.'}",
                    }
                )
                if label == "terraform init":
                    terraform_ready = False
                if label == "tflint init":
                    lint_ready = False
        return {"is_valid": not errors, "errors": errors, "logs": "\n\n".join(logs)}

    def validate(self) -> dict[str, Any]:
        with self:
            return self.execute_checks()

    def destroy_environment(self) -> None:
        if self.temp_dir is not None:
            shutil.rmtree(self.temp_dir)
            self.temp_dir = None
