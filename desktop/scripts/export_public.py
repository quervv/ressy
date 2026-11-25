from __future__ import annotations

import ast
import io
import re
import shutil
import subprocess
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

INCLUDE = [
    "README.md", "LICENSE", ".gitignore",
    "desktop/ressy", "desktop/installer", "desktop/scripts", "desktop/tests",
    "desktop/requirements.txt", "desktop/requirements-dev.txt",
    "server/ressy_server", "server/tests", "server/Dockerfile", "server/.dockerignore", "server/.env.example",
    "server/pyproject.toml", "server/requirements.txt", "server/requirements-dev.txt",
    "deploy", "web",
]
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".venv", "build", "dist", "download", "node_modules"}
SKIP_FILES = {".env", "build_release.log"}
SKIP_SUFFIXES = {".pyc", ".log", ".db", ".sqlite3", ".spec", ".part"}


def strip_python(source: str) -> str:
    tree = ast.parse(source)
    doc_lines: set[int] = set()
    holders: list[ast.AST] = [tree]
    holders += [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    emptied: dict[int, tuple[int, int]] = {}
    for node in holders:
        body = getattr(node, "body", [])
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            doc = body[0]
            doc_lines.update(range(doc.lineno, doc.end_lineno + 1))
            if len(body) == 1:
                emptied[doc.lineno] = (doc.col_offset, doc.end_lineno)

    lines = source.splitlines(keepends=True)
    cuts: dict[int, int] = {}
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            row, col = tok.start
            cuts[row] = min(col, cuts.get(row, col))

    out: list[str] = []
    for number, line in enumerate(lines, start=1):
        if number in doc_lines:
            if number in emptied:
                out.append(" " * emptied[number][0] + "pass\n")
            continue
        if number in cuts:
            kept = line[:cuts[number]].rstrip()
            if not kept:
                continue
            line = kept + "\n"
        out.append(line)
    text = "".join(out)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.lstrip("\n")


def strip_html(source: str) -> str:
    return re.sub(r"<!--(?!\[if).*?-->\s*", "", source, flags=re.S)


def strip_with_esbuild(paths: list[Path]) -> None:
    if not paths:
        return
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if npx is None:
        raise SystemExit("serve Node.js (npx) per togliere i commenti da JS e CSS")
    for path in paths:
        loader = "css" if path.suffix == ".css" else "js"
        result = subprocess.run(
            [npx, "-y", "esbuild@0.25.10", f"--loader={loader}", "--legal-comments=none", "--charset=utf8"],
            input=path.read_bytes(), capture_output=True, check=True,
        )
        text = result.stdout.decode("utf-8").replace("/* @__PURE__ */ ", "")
        text = "".join(line for line in text.splitlines(keepends=True) if not line.lstrip().startswith("//"))
        path.write_bytes(text.encode("utf-8"))


def copy_tree(dest: Path) -> list[Path]:
    copied: list[Path] = []
    for item in INCLUDE:
        src = ROOT / item
        if not src.exists():
            continue
        files = [src] if src.is_file() else [p for p in src.rglob("*") if p.is_file()]
        for file in files:
            rel = file.relative_to(ROOT)
            if any(part in SKIP_DIRS for part in rel.parts) or file.name in SKIP_FILES \
                    or file.suffix in SKIP_SUFFIXES:
                continue
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, target)
            copied.append(target)
    return copied


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    dest = Path(sys.argv[1]).resolve()
    if ROOT in dest.parents or dest == ROOT:
        raise SystemExit("la destinazione deve stare fuori dal progetto")
    if dest.exists():
        keep = {".git"}
        for child in dest.iterdir():
            if child.name in keep:
                continue
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    dest.mkdir(parents=True, exist_ok=True)
    files = copy_tree(dest)
    web_assets = []
    for file in files:
        if file.suffix == ".py":
            file.write_text(strip_python(file.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
        elif file.suffix == ".html":
            file.write_text(strip_html(file.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
        elif file.suffix in (".js", ".css"):
            web_assets.append(file)
    strip_with_esbuild(web_assets)
    for file in files:
        if file.suffix == ".py":
            compile(file.read_text(encoding="utf-8"), str(file), "exec")
    print(f"{len(files)} file in {dest}")


if __name__ == "__main__":
    main()
