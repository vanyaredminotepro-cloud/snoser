#!/usr/bin/env python3
from pathlib import Path

EXTS = {".py", ".js", ".html", ".css", ".sql", ".json"}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    total = 0
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in EXTS:
            continue
        try:
            total += len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
        except OSError:
            continue
    print(f"Total LOC ({', '.join(sorted(EXTS))}): {total}")


if __name__ == "__main__":
    main()
