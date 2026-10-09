import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    tracked = (
        subprocess.run(
            ["git", "ls-files", "-z", "--", "*.md"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        .stdout.decode("utf-8")
        .split("\0")
    )
    files = [root / name for name in tracked if name]
    failures = []
    for source in files:
        if not source.resolve().is_relative_to(root):
            failures.append((source, "Markdown file resolves outside the repository"))
            continue
        content = source.read_text(encoding="utf-8")
        for match in re.finditer(r"!?\[[^\]]*\]\((<[^>]*>|[^\s)]+)(?:\s+[^)]*)?\)", content):
            target = match.group(1).strip("<>")
            if target.startswith(("#", "//")) or urlsplit(target).scheme:
                continue
            local = unquote(target.split("#", 1)[0])
            if not local:
                continue
            destination = (source.parent / local).resolve()
            if not destination.is_relative_to(root) or not destination.exists():
                line = content.count("\n", 0, match.start()) + 1
                failures.append((source, f"Line {line}: local link has no repository target"))
    for source, message in failures:
        print(f"{source.relative_to(root).as_posix()}: {message}", file=sys.stderr)
    if failures:
        return 1
    print(f"Local inline documentation links checked across {len(files)} tracked Markdown files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
