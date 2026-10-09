import subprocess
import sys
from pathlib import Path


def run_checker(tmp_path, document):
    directory = tmp_path / "repository"
    scripts = directory / ".github/scripts"
    scripts.mkdir(parents=True)
    script = scripts / "check_doc_links.py"
    script.write_bytes(
        (Path(__file__).resolve().parents[1] / ".github/scripts/check_doc_links.py").read_bytes()
    )
    (directory / "README.md").write_text(document, encoding="utf-8")
    (directory / "guide with spaces.md").write_text("# Guide\n", encoding="utf-8")
    subprocess.run(["git", "init", "--quiet", str(directory)], check=True, capture_output=True)
    subprocess.run(
        ["git", "add", "README.md", "guide with spaces.md"],
        cwd=directory,
        check=True,
        capture_output=True,
    )
    return subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, check=False
    )


def test_checker_handles_local_inline_links_and_external_references(tmp_path):
    result = run_checker(
        tmp_path,
        "[Guide](guide%20with%20spaces.md#heading)\n[Guide](<guide with spaces.md>)\n[Heading](#heading)\n[External](https://example.invalid/guide)\n",
    )
    assert result.returncode == 0, result.stderr
    assert "2 tracked Markdown files" in result.stdout


def test_checker_reports_broken_screenshot_without_echoing_target(tmp_path):
    result = run_checker(tmp_path, "# Heading\n\n![Example](images/private-inventory.png)\n")
    assert result.returncode == 1
    assert "README.md: Line 3" in result.stderr
    assert "private-inventory" not in result.stderr


def test_checker_rejects_existing_file_outside_repository(tmp_path):
    (tmp_path / "outside.md").write_text("existing unrelated file", encoding="utf-8")
    result = run_checker(tmp_path, "[Outside](../outside.md)\n")
    assert result.returncode == 1
    assert "README.md: Line 1" in result.stderr
    assert (tmp_path / "outside.md").read_text(encoding="utf-8") == "existing unrelated file"
