"""
Regenerate the ADO-wiki package in ../wiki/ from the source docs in "KT learning/".

    python rebuild-wiki-package.py

What it does
    1. Renders every images/*.svg to PNG @2x using headless Chrome/Edge (no extra installs).
    2. Copies the PNGs (+ 13-ner-approach.png) into ../wiki/.attachments/ with an "ner-kt-" prefix.
    3. Converts each markdown doc to ADO-wiki flavour:
         ```mermaid  ->  ::: mermaid ... :::
         subgraph x  ->  subgraph "x"
         images/*    ->  /.attachments/ner-kt-*.png
         cross-links ->  relative ADO page links
       and renames the pages to Title-Case-With-Dashes (ADO derives page titles from file names).
    4. Writes the .order files.

Section 14 (future approach) is deliberately excluded - see EXCLUDE below.
"""
import os, re, shutil, glob, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, "..", ".."))          # "KT learning"
IMG = os.path.join(BASE, "images")
OUT = os.path.abspath(os.path.join(HERE, ".."))                 # "ado-wiki"
WIKI = os.path.join(OUT, "wiki")
PARENT = "NER-Knowledge-Transfer"
CHILD_DIR = os.path.join(WIKI, PARENT)
ATT = os.path.join(WIKI, ".attachments")
PREFIX = "ner-kt-"
SCALE = 2

BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# source md -> (ADO page file name without .md, is_landing_page)
PAGES = [
    ("00-README-START-HERE.md",            PARENT,                           True),
    ("01-explain-like-im-5.md",            "01-Explain-Like-Im-5",           False),
    ("02-big-picture-architecture.md",     "02-Big-Picture-Architecture",    False),
    ("03-step-by-step-flow.md",            "03-Step-By-Step-Flow",           False),
    ("04-file-by-file.md",                 "04-File-By-File",                False),
    ("05-worked-example.md",               "05-Worked-Example",              False),
    ("06-all-diagrams.md",                 "06-All-Diagrams",                False),
    ("07-glossary.md",                     "07-Glossary",                    False),
    ("08-how-to-test-locally.md",          "08-How-To-Test-Locally",         False),
    ("09-missing-files.md",                "09-Missing-Files",               False),
    ("11-rulebased-vs-llm.md",             "11-Rule-Based-vs-LLM",           False),
    ("12-bug-217995-zytel-casestudy.md",   "12-Bug-217995-Zytel-Case-Study", False),
    ("13-how-ner-prediction-works.md",     "13-How-NER-Prediction-Works",    False),
    ("images/README-images.md",            "Diagram-Gallery",                False),
]
NAME_MAP = {src.split("/")[-1]: (dst, landing) for src, dst, landing in PAGES}

EXTRA_PNGS = ["13-ner-approach.png"]
EXCLUDE = ("14-future-architecture",)          # section 14 - future approach: not published


def find_browser():
    for b in BROWSERS:
        if os.path.exists(b):
            return b
    sys.exit("No Chrome/Edge found - install one, or convert the SVGs to PNG by hand.")


def svg_to_png(svg_path, png_path, browser, tmp):
    data = open(svg_path, encoding="utf-8").read()
    m = re.search(r'viewBox="([\d.\-\s]+)"', data)
    if not m:
        sys.exit("No viewBox in %s - cannot infer size." % svg_path)
    vb = [float(x) for x in m.group(1).split()]
    w, h = int(vb[2]), int(vb[3])
    html = os.path.join(tmp, os.path.basename(svg_path) + ".html")
    with open(html, "w", encoding="utf-8") as f:
        f.write("<html><head><meta charset='utf-8'><style>"
                "html,body{margin:0;padding:0;background:#fff;}"
                "svg{display:block;width:%dpx;height:%dpx;}</style></head><body>%s</body></html>"
                % (w, h, data))
    subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--default-background-color=FFFFFFFF",
                    "--force-device-scale-factor=%d" % SCALE,
                    "--screenshot=" + png_path,
                    "--window-size=%d,%d" % (w, h),
                    "file:///" + html.replace("\\", "/")],
                   capture_output=True, text=True)
    if not os.path.exists(png_path):
        sys.exit("Render failed for " + svg_path)


# ---------- markdown transforms ----------
def fix_mermaid(text):
    out, in_block = [], False
    for line in text.split("\n"):
        if not in_block and re.match(r"^\s*```mermaid\s*$", line):
            out.append("::: mermaid"); in_block = True; continue
        if in_block and re.match(r"^\s*```\s*$", line):
            out.append(":::"); in_block = False; continue
        if in_block:
            m = re.match(r"^(\s*)subgraph\s+(?!\")(.+?)\s*$", line)
            if m:
                line = '%ssubgraph "%s"' % (m.group(1), m.group(2))
        out.append(line)
    return "\n".join(out)


def fix_images(text):
    def repl(m):
        stem = os.path.splitext(os.path.basename(m.group(2)))[0]
        return "![%s](/.attachments/%s%s.png)" % (m.group(1), PREFIX, stem)
    return re.sub(r"!\[([^\]]*)\]\((?:images/)?([^)]*\.(?:svg|png))\)", repl, text)


def fix_links(text, from_landing):
    def repl(m):
        label, target = m.group(1), m.group(2)
        anchor = ""
        if "#" in target:
            target, anchor = target.split("#", 1)
            anchor = "#" + anchor
        fname = target.split("/")[-1]
        if fname not in NAME_MAP:
            return m.group(0)
        dst, landing = NAME_MAP[fname]
        if landing:
            path = ("./%s.md" % PARENT) if from_landing else ("../%s.md" % PARENT)
        else:
            path = ("./%s/%s.md" % (PARENT, dst)) if from_landing else ("./%s.md" % dst)
        return "[%s](%s%s)" % (label, path, anchor)
    return re.sub(r"\[([^\]]*)\]\(([^)]+\.md(?:#[^)]*)?)\)", repl, text)


def relabel(text):
    for src, (dst, _) in NAME_MAP.items():
        text = text.replace("`%s`" % src, "`%s`" % dst)
    return text


VIEW_OLD = """## 💡 How to view the diagrams

The diagrams use two formats:
- **Mermaid** (```` ```mermaid ````) — renders automatically in **GitHub**, **VS Code** (with the
  *Markdown Preview Mermaid* extension), Obsidian, and many markdown viewers.
- **ASCII art** — works *everywhere*, even Notepad.

If a Mermaid diagram shows as plain text, install a Mermaid-enabled previewer — or just read the ASCII version right beside it."""

VIEW_NEW = """## 💡 How to view the diagrams

The diagrams come in three formats, all of which work inside this wiki:
- **Mermaid** (`::: mermaid` blocks) — rendered natively by Azure DevOps Wiki.
- **PNG images** — the hand-drawn architecture/UML/domain diagrams, stored as wiki
  attachments. See [`Diagram-Gallery`](./NER-Knowledge-Transfer/Diagram-Gallery.md).
- **ASCII art** — works *everywhere*, even in a plain-text editor.

If a Mermaid block ever shows as plain text (older Azure DevOps Server versions), just read the
ASCII version right beside it — every Mermaid diagram in this KT has an ASCII twin."""

GALLERY_OLD = """All diagrams are **SVG** (vector images) — they open in any web browser, VS Code, or image
viewer, render crisply at any zoom, and embed directly in markdown (shown below).

> **Want PNGs?** Open any `.svg` in a browser and "Save as image", or run a converter
> (e.g. `npx svgexport file.svg file.png 2x`, or Inkscape / ImageMagick if installed).
> No SVG renderer was available in this environment, so only SVGs were generated."""

GALLERY_NEW = """All diagrams are stored as **PNG** wiki attachments (rendered at 2x for crisp zooming) under
`/.attachments/`, so they display in Azure DevOps Wiki, in the mobile app, and in PDF exports.

> **Need the editable source?** The original vector `.svg` / Mermaid `.mmd` sources live in the
> repo at `flat-repo-ner/KT learning/images/`. Edit there, re-export to PNG, and re-upload the
> attachment with the same file name to update every page at once."""

GALLERY_EXTRA = """### 12. NER Approach — data, training & serving
End-to-end view of the data sources, fine-tuning loop and the serving path used for prediction.
![NER approach — data, training, serving](/.attachments/ner-kt-13-ner-approach.png)

---

"""

PAGE_PATCHES = {
    PARENT: [
        ("| # | File | What you'll learn | Level |", "| # | Page | What you'll learn | Level |"),
        ("[`images/README-images.md`]", "[`Diagram-Gallery`]"),
        ("**Diagram gallery** — 11 SVG diagrams (architecture, UML, domain)",
         "**Diagram gallery** — all 12 image diagrams (architecture, UML, domain)"),
        (VIEW_OLD, VIEW_NEW),
    ],
    "Diagram-Gallery": [
        (GALLERY_OLD, GALLERY_NEW),
        ("---\n\n| # | File | View type |\n|---|------|-----------|",
         GALLERY_EXTRA + "| # | Attachment | View type |\n|---|------------|-----------|"),
    ],
}


def apply_patches(name, text):
    for old, new in PAGE_PATCHES.get(name, []):
        if old not in text:
            sys.exit("Patch no longer matches in page '%s' (source doc changed):\n%s" % (name, old[:90]))
        text = text.replace(old, new)
    if name == "Diagram-Gallery":
        text = re.sub(r"`(\d\d-[a-z0-9\-]+)\.svg`", "`" + PREFIX + r"\1.png`", text)
        row11 = "| 11 | `%s11-rulebased-vs-llm.png` | Rule-based vs LLM resolution |" % PREFIX
        text = text.replace(row11, row11 + "\n| 12 | `%s13-ner-approach.png` | Approach — data / training / serving |" % PREFIX)
    return text


def main():
    for d in (ATT, CHILD_DIR):
        os.makedirs(d, exist_ok=True)

    browser = find_browser()
    tmp = tempfile.mkdtemp(prefix="svg2png-")
    print("Rendering SVG -> PNG with", os.path.basename(browser))
    for svg in sorted(glob.glob(os.path.join(IMG, "*.svg"))):
        stem = os.path.splitext(os.path.basename(svg))[0]
        if stem.startswith(EXCLUDE):
            print("  skip (excluded):", stem); continue
        dst = os.path.join(ATT, PREFIX + stem + ".png")
        svg_to_png(svg, dst, browser, tmp)
        print("  ok:", os.path.basename(dst))
    shutil.rmtree(tmp, ignore_errors=True)

    for p in EXTRA_PNGS:
        if p.startswith(EXCLUDE):
            continue
        shutil.copyfile(os.path.join(IMG, p), os.path.join(ATT, PREFIX + p))
        print("  ok:", PREFIX + p)

    print("\nWriting pages")
    for src, dst, landing in PAGES:
        raw = open(os.path.join(BASE, src.replace("/", os.sep)), encoding="utf-8").read()
        t = apply_patches(dst, relabel(fix_links(fix_images(fix_mermaid(raw)), landing)))
        path = os.path.join(WIKI, dst + ".md") if landing else os.path.join(CHILD_DIR, dst + ".md")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(t)
        print("  ", os.path.relpath(path, OUT))

    with open(os.path.join(WIKI, ".order"), "w", encoding="utf-8", newline="\n") as f:
        f.write(PARENT + "\n")
    with open(os.path.join(CHILD_DIR, ".order"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(d for s, d, landing in PAGES if not landing) + "\n")

    print("\nDone -> %s\nNext: see ..\\README-HOW-TO-PUBLISH.md" % WIKI)


if __name__ == "__main__":
    main()
