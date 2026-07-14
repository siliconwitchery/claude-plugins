#!/usr/bin/env python3
"""Generate skill reference files from the Silicon Witchery docs site sources.

Converts the Jekyll/kramdown pages in the siliconwitchery/docs repo into plain
markdown reference files bundled with the Claude plugin skills:

    pages/superstack/lua.md -> plugins/superstack/skills/s2-lua/references/lua-api.md
    pages/superstack/api.md -> plugins/superstack/skills/superstack-api/references/rest-api.md

What it does:
  - strips Jekyll frontmatter
  - strips Liquid/kramdown inline attribute lines ({: .no_toc}, {: .label-*}, ...)
  - removes the kramdown "1. TOC\n{:toc}" block and generates a plain markdown
    table of contents from the ## / ### headings instead
  - converts "> " callout blocks following {: .note-title} / {: .warning-title}
    / {: .note} / {: .warning} markers into plain markdown with bold labels
  - drops site-relative images (/assets/...) that cannot ship with the skill
  - applies the correction patches in PATCHES below
  - prepends a GENERATED header comment

Usage:
    python3 scripts/generate-references.py --docs <path-to-docs-checkout> --write
    python3 scripts/generate-references.py --docs <path-to-docs-checkout> --check

--check verifies the committed reference files match the regenerated output and
exits 1 on drift. Note: the originally committed reference files were produced
by hand following the same rules, so purely cosmetic drift on --check
(whitespace, blank-line, or phrasing differences that do not change meaning) is
acceptable for that first generation. The output of --write is authoritative
going forward: run --write, review the diff, and commit.

Requires only the Python 3 standard library.
"""

import argparse
import difflib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# docs-repo-relative source -> plugin-repo-relative output
SOURCES = {
    "pages/superstack/lua.md": "plugins/superstack/skills/s2-lua/references/lua-api.md",
    "pages/superstack/api.md": "plugins/superstack/skills/superstack-api/references/rest-api.md",
}

# Correction patches applied to the generated markdown, keyed by output file
# basename. Each entry is an (old, new) pair; `old` must occur exactly once in
# the generated text or the script errors out (so a stale patch is noticed as
# soon as the upstream docs change). Empty since the time.get_unix_time()
# example fix landed upstream in siliconwitchery/docs — keep the mechanism for
# future doc bugs that can't be fixed upstream immediately.
PATCHES = {}

TOC_PLACEHOLDER = "@@TOC@@"

MARKER_RE = re.compile(r"^\{:\s*\.?([\w-]*)[^}]*\}\s*$")
IMAGE_RE = re.compile(r"^!\[[^\]]*\]\(/assets/[^)]*\)\s*$")
HEADING_RE = re.compile(r"^(#{2,3}) (.+?)\s*$")


def strip_frontmatter(lines):
    """Remove a leading Jekyll frontmatter block delimited by --- lines."""
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return lines[i + 1:]
    return lines


def dequote(line):
    """Remove one level of markdown blockquote prefix from a line."""
    return re.sub(r"^\s*> ?", "", line, count=1).rstrip()


def render_callout(cls, quote):
    """Turn a dequoted callout body into plain markdown with a bold label."""
    while quote and not quote[0].strip():
        quote.pop(0)
    while quote and not quote[-1].strip():
        quote.pop()

    if cls in ("note-title", "warning-title"):
        title = quote.pop(0).strip() if quote else ""
        while quote and not quote[0].strip():
            quote.pop(0)
        label = f"**{title}**" if cls == "note-title" else f"**Warning: {title}**"
        block = [label]
        if quote:
            block.append("")
            block.extend(quote)
        return block

    label = "Note" if cls == "note" else "Warning"
    if quote:
        quote[0] = f"**{label}:** {quote[0]}"
    return quote


def transform(lines):
    """Convert kramdown/Liquid-flavoured markdown lines to plain markdown."""
    out = []
    i = 0
    n = len(lines)
    while i < n:
        stripped = lines[i].strip()

        # kramdown auto-TOC block -> placeholder for the generated TOC
        if stripped == "1. TOC" and i + 1 < n and lines[i + 1].strip() == "{:toc}":
            out.append(TOC_PLACEHOLDER)
            i += 2
            continue

        m = MARKER_RE.match(stripped)
        if m:
            cls = m.group(1)
            i += 1
            if cls in ("note-title", "warning-title", "note", "warning"):
                while i < n and not lines[i].strip():
                    i += 1
                if i < n and lines[i].lstrip().startswith(">"):
                    quote = []
                    while i < n and lines[i].lstrip().startswith(">"):
                        quote.append(dequote(lines[i]))
                        i += 1
                    out.extend(render_callout(cls, quote))
                elif cls in ("note", "warning") and i < n:
                    # {: .note} may be followed by a plain paragraph
                    para = []
                    while i < n and lines[i].strip():
                        para.append(lines[i].rstrip())
                        i += 1
                    if para:
                        label = "Note" if cls == "note" else "Warning"
                        para[0] = f"**{label}:** {para[0]}"
                        out.extend(para)
            # all other markers ({: .no_toc}, {: .label-*}, ...) are dropped
            continue

        # site-relative images cannot ship with the skill
        if IMAGE_RE.match(stripped):
            i += 1
            continue

        out.append(lines[i].rstrip())
        i += 1
    return out


def slugify(text):
    """GitHub-style anchor for a heading."""
    text = re.sub(r"[^\w\s-]", "", text.strip().lower())
    return re.sub(r"\s+", "-", text)


def build_toc(lines):
    """Generate a markdown TOC from ## / ### headings (outside code fences)."""
    toc = []
    in_fence = False
    for line in lines:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            text = m.group(2)
            if text.lower() == "contents":
                continue
            toc.append("  " * (level - 2) + f"- [{text}](#{slugify(text)})")
    return toc


def tidy(lines):
    """Collapse runs of blank lines and trim leading/trailing blanks."""
    out = []
    for line in lines:
        if not line.strip() and out and not out[-1].strip():
            continue
        out.append(line)
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return out


def generated_header(source_rel):
    return [
        "<!--",
        "  GENERATED FILE - DO NOT EDIT BY HAND.",
        f"  Generated from {source_rel} in the siliconwitchery/docs repo by",
        "  scripts/generate-references.py. To update, edit the docs and run:",
        "      python3 scripts/generate-references.py --docs <docs-checkout> --write",
        "-->",
        "",
    ]


def apply_patches(out_name, text):
    for old, new in PATCHES.get(out_name, []):
        count = text.count(old)
        if count == 0:
            sys.exit(
                f"error: patch for {out_name} no longer applies (fixed upstream?).\n"
                f"Remove the stale entry from PATCHES in {__file__}.\n"
                f"Patch text:\n{old}"
            )
        if count > 1:
            sys.exit(f"error: patch for {out_name} matches {count} times; must be unique")
        text = text.replace(old, new)
    return text


def generate(docs_root, source_rel):
    source = docs_root / source_rel
    lines = source.read_text(encoding="utf-8").splitlines()
    lines = strip_frontmatter(lines)
    body = tidy(transform(lines))

    toc = build_toc(body)
    body = [line if line != TOC_PLACEHOLDER else "\n".join(toc) for line in body]

    out_name = Path(SOURCES[source_rel]).name
    text = "\n".join(generated_header(source_rel) + body) + "\n"
    return apply_patches(out_name, text)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--docs", required=True,
                        help="path to a checkout of the siliconwitchery/docs repo")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true",
                      help="verify committed reference files match; exit 1 on drift")
    mode.add_argument("--write", action="store_true",
                      help="write the regenerated reference files")
    args = parser.parse_args()

    docs_root = Path(args.docs).resolve()
    if not docs_root.is_dir():
        sys.exit(f"error: --docs path not found: {docs_root}")

    drift = False
    for source_rel, output_rel in SOURCES.items():
        generated = generate(docs_root, source_rel)
        output = REPO_ROOT / output_rel

        if args.write:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(generated, encoding="utf-8")
            print(f"wrote {output_rel}")
            continue

        committed = output.read_text(encoding="utf-8") if output.exists() else ""
        if committed != generated:
            drift = True
            print(f"DRIFT: {output_rel} does not match regenerated output")
            sys.stdout.writelines(difflib.unified_diff(
                committed.splitlines(keepends=True),
                generated.splitlines(keepends=True),
                fromfile=f"committed/{output_rel}",
                tofile=f"generated/{output_rel}",
            ))
        else:
            print(f"ok: {output_rel}")

    if drift:
        sys.exit(1)


if __name__ == "__main__":
    main()
