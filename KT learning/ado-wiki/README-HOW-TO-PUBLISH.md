# How to publish this KT to the Azure DevOps Wiki

This folder contains the **NER Knowledge Transfer** documentation converted into the exact
layout an Azure DevOps (ADO) **wiki Git repository** expects — pages, page order, and images.

> ⚠️ Only the contents of the [`wiki/`](wiki) folder go into Azure DevOps.
> This README and the helper script stay behind in the repo.

---

## 📦 What's in here

```
ado-wiki/
├── README-HOW-TO-PUBLISH.md          ← you are here (do NOT copy to the wiki)
├── publish-to-ado-wiki.ps1           ← optional one-command publisher (do NOT copy)
├── tools/
│   └── rebuild-wiki-package.py       ← regenerates wiki/ from the source docs (do NOT copy)
└── wiki/                             ← ✅ copy the CONTENTS of this folder to the wiki repo
    ├── .order                        ← root page order (1 line: NER-Knowledge-Transfer)
    ├── NER-Knowledge-Transfer.md     ← landing page  → wiki page "NER Knowledge Transfer"
    ├── NER-Knowledge-Transfer/       ← its 13 sub-pages
    │   ├── .order                    ← sub-page order (01 → 13 → Diagram Gallery)
    │   ├── 01-Explain-Like-Im-5.md
    │   ├── 02-Big-Picture-Architecture.md
    │   ├── 03-Step-By-Step-Flow.md
    │   ├── 04-File-By-File.md
    │   ├── 05-Worked-Example.md
    │   ├── 06-All-Diagrams.md
    │   ├── 07-Glossary.md
    │   ├── 08-How-To-Test-Locally.md
    │   ├── 09-Missing-Files.md
    │   ├── 11-Rule-Based-vs-LLM.md
    │   ├── 12-Bug-217995-Zytel-Case-Study.md
    │   ├── 13-How-NER-Prediction-Works.md
    │   └── Diagram-Gallery.md
    └── .attachments/                 ← 12 PNG diagrams (ADO's standard image folder)
        └── ner-kt-*.png
```

**Section 14 (future approach) is intentionally excluded** — neither
`14-future-architecture.png` nor `14-future-architecture.mmd` is included, and no page
references it.

---

## ✅ Method 1 — Push to the wiki Git repo (recommended, 2 minutes)

Every ADO project wiki *is* a Git repo named `<Project>.wiki`.

```powershell
# 1. clone the wiki repo (URL pattern below)
git clone https://dev.azure.com/<org>/<project>/_git/<project>.wiki
cd <project>.wiki

# 2. copy the contents of ado-wiki\wiki\ into the clone
#    (Copy-Item needs -Force to include the dot-folders .order / .attachments)
Copy-Item -Path "D:\sarath_interview_study_material_v2\celanese-knowledge-base\flat-repo-ner\KT learning\ado-wiki\wiki\*" `
          -Destination . -Recurse -Force

# 3. commit & push
git add -A
git commit -m "Add NER Knowledge Transfer KT section"
git push
```

The pages appear in the wiki tree immediately after the push.

> 💡 Or just run [`publish-to-ado-wiki.ps1`](publish-to-ado-wiki.ps1), which does all of the
> above **and** safely merges the `.order` file (see below):
> ```powershell
> .\publish-to-ado-wiki.ps1 -WikiRepoUrl "https://dev.azure.com/<org>/<project>/_git/<project>.wiki"
> # add -Push to publish; without it, it stages the commit locally for you to review
> ```

### ⚠️ If your wiki already has pages — merge `.order`, don't overwrite it

`wiki/.order` here contains a single line: `NER-Knowledge-Transfer`.
If the wiki root already has a `.order`, **append that line** to the existing file instead of
replacing it (the file simply lists root pages, top to bottom). The helper script does this
automatically. `NER-Knowledge-Transfer/.order` is new, so it can be copied as-is.

### Want it nested under an existing page instead of at the root?

Put `NER-Knowledge-Transfer.md` and the `NER-Knowledge-Transfer/` folder inside that parent's
folder (e.g. `Engineering/NER-Knowledge-Transfer.md` + `Engineering/NER-Knowledge-Transfer/`),
and add the line to `Engineering/.order` instead of the root `.order`. All cross-page links are
**relative**, so they keep working at any depth. `.attachments/` must stay at the **wiki root**.

---

## ✅ Method 2 — Upload through the ADO web UI (no Git)

1. Wiki → **⋯** next to the wiki name → **Upload file(s)** isn't available for pages, so:
2. Create the parent page: **New page** → name it `NER Knowledge Transfer` → open the **editor**,
   paste the contents of `wiki/NER-Knowledge-Transfer.md` → Save.
3. For each file in `wiki/NER-Knowledge-Transfer/`: **⋯** on the parent page → **Add sub-page** →
   name it exactly as the file name **without the `.md`, with dashes replaced by spaces**
   (e.g. `04-File-By-File.md` → page name `04 File By File`) → paste the file contents → Save.
4. Images: in any page editor, use the **paperclip / Insert image** button and upload every PNG
   from `wiki/.attachments/`. ADO stores them under `/.attachments/` with the **same file name**,
   which is exactly what the pages already reference — so uploading them once fixes every page.
   Keep the `ner-kt-` prefixes; do not rename.
5. Drag pages in the tree to reorder (this rewrites `.order` for you).

Method 1 is much faster — 14 pages by hand is tedious.

---

## ✅ Method 3 — "Publish code as wiki" (docs-as-code)

If you'd rather keep the docs versioned in the product repo and let ADO render them:

1. Commit this `ado-wiki/wiki` folder to your Git repo.
2. Wiki → dropdown at the top → **Publish code as wiki**.
3. Repository = your repo, Folder = `/flat-repo-ner/KT learning/ado-wiki/wiki`, Branch = `main`,
   Wiki name = `NER KT`.

Trade-off: published-code wikis are **read-only in the wiki UI** (edits go through the repo/PRs),
and the `/.attachments/...` image paths resolve from the **repo root**, not the published folder.
So if you choose this method, either move `.attachments` to the repo root, or run a find/replace
of `/.attachments/` → `../.attachments/` in the sub-pages and `./.attachments/` in the landing
page. Method 1 needs none of that.

---

## 🔧 What was changed during conversion (and why)

| Change | Reason |
|---|---|
| ```` ```mermaid ```` fences → `::: mermaid` blocks | ADO Wiki only renders Mermaid in `:::` blocks |
| `subgraph score.py` → `subgraph "score.py"` | ADO's older Mermaid build needs quoted titles containing dots |
| 11 SVG diagrams → PNG @ 2x | SVG rendering in ADO Wiki is unreliable; PNG always renders and exports to PDF |
| Images moved to `.attachments/`, prefixed `ner-kt-` | ADO's fixed image location; the prefix prevents collisions with existing wiki attachments |
| Image links → `/.attachments/ner-kt-*.png` | Absolute-from-wiki-root is what ADO itself generates |
| File names → `Title-Case-With-Dashes` | ADO derives the page title from the file name (dash → space) |
| Cross-links rewritten to `./Page.md` / `../Parent.md` | Relative links survive being re-parented anywhere in the tree |
| `00-README-START-HERE.md` → landing page `NER-Knowledge-Transfer.md` | Becomes the section's parent page, with the reading order as its index |
| `images/README-images.md` → `Diagram-Gallery.md` | Real page name in the tree; also gained the NER-approach diagram as #12 |
| Section 14 (future approach) dropped | As requested |

The originals under `flat-repo-ner/KT learning/` are untouched — this is a generated copy.

---

## 🔁 Updating later

Edit the source docs in `flat-repo-ner/KT learning/`, then re-run the converter:

```powershell
python .\tools\rebuild-wiki-package.py
```

It re-renders the SVGs to PNG (headless Chrome/Edge — nothing to install), rewrites every page,
and refreshes `wiki/` in place. Then repeat Method 1
(`git add -A; git commit; git push`). Re-uploading an attachment with the same file name updates
it everywhere it's referenced.
