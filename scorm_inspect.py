"""One-time helper: what is inside e-learning packages (SCORM .zip files or unpacked folders), so the reader for
them can be built. Prints only structure and counts: no titles, no text, no file names from the package.

    uv run --no-project python $HOME\\Downloads\\scorm_inspect.py "C:\\path\\to\\a package.zip"
    uv run --no-project python $HOME\\Downloads\\scorm_inspect.py "C:\\path\\to\\a folder with packages"
"""
from __future__ import annotations

import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

GROUPS = {"page (html)": {".html", ".htm", ".xhtml"}, "script (js)": {".js"}, "data (json/xml)": {".json", ".xml"},
          "video": {".mp4", ".webm", ".mov", ".m4v"}, "audio": {".mp3", ".m4a", ".wav", ".ogg", ".aac"},
          "captions": {".vtt", ".srt"}, "image": {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"},
          "pdf/office": {".pdf", ".docx", ".pptx", ".xlsx"}, "font/style": {".woff", ".woff2", ".ttf", ".otf", ".css"}}
# the authoring tool that made the package, by the files it always writes
TOOLS = [("Articulate Storyline", r"(^|/)story(_html5)?\.html$|(^|/)story_content/|html5/data/js/data\.js$"),
         ("Articulate Rise", r"(^|/)scormcontent/|(^|/)lib/rise/"),
         ("Adobe Captivate", r"(^|/)assets/js/CPM\.js$|captivate"),
         ("iSpring", r"(^|/)data/player\.js$|ispring"),
         ("Lectora", r"trivantis|(^|/)a001index\.html$"),
         ("Elucidat", r"elucidat")]
QUIZ = re.compile(r"quiz|question|assessment|answer|interaction", re.I)
ITEM = re.compile(r"<item[\s>]")


def files_of(path: Path) -> list[tuple[str, int]]:
    """(path inside the package, size) of every file of a .zip or a folder."""
    if path.is_dir():
        return [(p.relative_to(path).as_posix(), p.stat().st_size) for p in path.rglob("*") if p.is_file()]
    with zipfile.ZipFile(path) as z:
        return [(i.filename, i.file_size) for i in z.infolist() if not i.is_dir()]


def manifest_of(path: Path) -> str:
    """The text of imsmanifest.xml ('' when there is none)."""
    if path.is_dir():
        m = next(path.rglob("imsmanifest.xml"), None)
        return m.read_text(encoding="utf-8", errors="ignore") if m else ""
    with zipfile.ZipFile(path) as z:
        name = next((n for n in z.namelist() if n.lower().endswith("imsmanifest.xml")), "")
        return z.read(name).decode("utf-8", errors="ignore") if name else ""


def describe(path: Path) -> list[str]:
    """The structure of one package, as lines to print."""
    files = files_of(path)
    manifest = manifest_of(path)
    version = re.search(r"<schemaversion>\s*([^<]+)", manifest, re.I)
    names = "\n".join(n.lower() for n, _ in files)
    tools = [t for t, pattern in TOOLS if re.search(pattern, names, re.M | re.I)]
    kinds: Counter[str] = Counter()
    sizes: Counter[str] = Counter()
    for name, size in files:
        ext = Path(name).suffix.lower()
        group = next((g for g, exts in GROUPS.items() if ext in exts), f"other ({ext or 'no type'})")
        kinds[group] += 1
        sizes[group] += size
    scorm = ("yes, version " + version.group(1).strip()) if version else ("yes" if manifest else "no imsmanifest.xml")
    items = len(ITEM.findall(manifest))
    out = [f"- SCORM: {scorm}",
           f"- made with: {', '.join(tools) or 'not recognised'}",
           f"- lessons/pages in the manifest: {items}",
           f"- files: {len(files)}, {sum(s for _, s in files) / 2**20:.1f} MB"]
    out += [f"    {g}: {kinds[g]} ({sizes[g] / 2**20:.1f} MB)" for g in sorted(kinds, key=lambda g: -kinds[g])]
    out.append(f"- files whose name points to a quiz: {sum(bool(QUIZ.search(n)) for n, _ in files)}")
    return out


def main() -> int:
    """Describe every package given (a .zip, a folder, or a folder of them). Returns the exit code."""
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    root = Path(sys.argv[1].strip().strip('"'))
    if not root.exists():
        print(f"Not found: {root}")
        return 1
    is_package = root.suffix.lower() == ".zip" or (root.is_dir() and any(root.glob("imsmanifest.xml")))
    packages = [root] if is_package else sorted(root.rglob("*.zip")) + sorted(
        p.parent for p in root.rglob("imsmanifest.xml") if p.parent != root)
    if not packages:
        print("No .zip files or SCORM folders found here.")
        return 1
    for i, pkg in enumerate(packages, 1):
        print(f"\nPackage {i} of {len(packages)}")
        try:
            print("\n".join(describe(pkg)))
        except (OSError, zipfile.BadZipFile) as e:
            print(f"- could not be read: {type(e).__name__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
