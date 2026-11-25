"""One-time helper: what is inside e-learning courses (SCORM, cmi5, xAPI, AICC or plain HTML; .zip files, zips inside
zips, unpacked folders, folders inside folders), so the reader for them can be built.

    uv run --no-project python $HOME\\Downloads\\scorm_inspect.py "$HOME\\Downloads\\Scrum"

Everything in one run. Prints, and saves to scorm_report.txt next to this script:
  - the format and the tool that made each course, the structure of its manifest
  - where the readable text is (pages, data files, data hidden in scripts, captions) and how much, in which language
  - the shape of the data files: field names and how many of each, never a value
  - every video and audio: length, size, whether it has captions and in which language; links to outside videos
  - pictures by size (icons or slides), documents, signs of a quiz
  - problems: locked or damaged zips, packing the browser cannot open, Mac copies, paths too long for Windows
No titles, no text, no names of the course's own files are printed.
"""
from __future__ import annotations

import base64
import binascii
import io
import json
import re
import struct
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

GROUPS = {"page (html)": {".html", ".htm", ".xhtml"}, "script (js)": {".js"}, "data (json)": {".json"},
          "data (xml)": {".xml"}, "video": {".mp4", ".webm", ".mov", ".m4v", ".avi", ".wmv", ".flv"},
          "audio": {".mp3", ".m4a", ".wav", ".ogg", ".aac", ".wma"},
          "captions": {".vtt", ".srt", ".ttml", ".dfxp", ".sbv", ".ass"},
          "image": {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp"},
          "document": {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".txt", ".rtf"},
          "font/style": {".woff", ".woff2", ".ttf", ".otf", ".eot", ".css"}, "schema (xsd/dtd)": {".xsd", ".dtd"},
          "flash": {".swf", ".flv"}, "zip": {".zip"}}
TOOLS = [("Articulate Storyline", r"(^|/)story(_html5)?\.html$|(^|/)story_content/|html5/data/js/data\.js$"),
         ("Articulate Rise", r"(^|/)scormcontent/|(^|/)lib/rise/"),
         ("Articulate Presenter/Studio", r"(^|/)data/player\.xml$|presentation_content/"),
         ("Adobe Captivate", r"(^|/)assets/js/cpm\.js$|captivate|(^|/)cp_.*\.js$"),
         ("iSpring", r"(^|/)data/player\.js$|ispring"), ("Lectora", r"trivantis|(^|/)a001index\.html$"),
         ("Elucidat", r"elucidat"), ("Adapt Learning", r"(^|/)adapt/js/|(^|/)course/[a-z]{2}/(blocks|components)\.json$"),
         ("Easygenerator", r"easygenerator"), ("Evolve", r"evolve"), ("Gomo", r"gomo"), ("dominKnow", r"dominknow|claro"),
         ("H5P", r"h5p"), ("Camtasia", r"techsmith|camtasia"), ("Adobe Presenter", r"presenter"),
         ("SAP Enable Now", r"enable.?now|(^|/)tour\.html$"), ("Rustici SCORM driver", r"scormdriver"),
         ("pipwerks SCORM wrapper", r"pipwerks|scorm_api_wrapper")]
QUIZ_KEYS = re.compile(r"question|answer|correct|distract|feedback|choice|option|score|quiz|assess|knowledge.?check|"
                       r"interaction|attempt|mastery", re.I)
MEDIA_KEYS = re.compile(r"video|audio|src|poster|transcript|caption|subtitle|track|media", re.I)
TEXT_KEYS = re.compile(r"text|title|body|html|content|heading|description|note|label|caption|paragraph", re.I)
ENGLISH = {"the", "and", "of", "to", "is", "in", "for", "with", "this", "that", "you", "are", "be", "on", "it", "can"}
GERMAN = {"der", "die", "und", "das", "ist", "nicht", "mit", "für", "sie", "ein", "eine", "zu", "den", "von", "werden",
          "auf", "auch", "wir", "sind", "oder"}
WORD = re.compile(r"[a-zäöüß]+")
BAD_METHODS = {9: "Deflate64 (Windows 'compressed folder' over 2 GB)", 12: "bzip2", 14: "LZMA", 95: "XZ", 98: "PPMd",
               99: "AES encryption"}
MAX_TEXT = 40_000_000       # bytes of pages, data and scripts read per course
MAX_NESTED = 600_000_000    # a zip inside a zip is opened in memory up to this size
MANIFESTS = ("imsmanifest.xml", "tincan.xml", "cmi5.xml")


# --- a course's files, wherever they are: a folder, a zip, a zip inside a zip ------------------------------------
@dataclass
class Source:
    """The files of one course (a folder or a zip) and how to read them."""
    kind: str                    # folder | zip | zip in zip
    label: str                   # where it is, without names: "folder 2", "zip 1 in folder 3", ...
    files: list[tuple[str, int]] = field(default_factory=list)
    folder: Path | None = None
    archive: zipfile.ZipFile | None = None
    problems: list[str] = field(default_factory=list)

    def open(self, name: str) -> BinaryIO:
        """One file, to read (seekable)."""
        if self.folder is not None:
            return (self.folder / name).open("rb")
        assert self.archive is not None
        return self.archive.open(name)

    def read(self, name: str, limit: int = MAX_TEXT) -> bytes:
        """One file's bytes (at most `limit`)."""
        with self.open(name) as f:
            return f.read(limit)


def zip_source(z: zipfile.ZipFile, kind: str, label: str) -> Source:
    """A zip's files, with what the browser or Python cannot unpack."""
    src = Source(kind, label, archive=z)
    methods: Counter[str] = Counter()
    locked = 0
    for i in z.infolist():
        if i.is_dir():
            continue
        src.files.append((i.filename.replace("\\", "/"), i.file_size))
        if i.flag_bits & 0x1:
            locked += 1
        if i.compress_type in BAD_METHODS:
            methods[BAD_METHODS[i.compress_type]] += 1
    if locked:
        src.problems.append(f"{locked} files are password-protected")
    for m, n in methods.items():
        src.problems.append(f"{n} files packed with {m}: unpack the zip on Windows first")
    if any(i.file_size >= 0xFFFFFFFF or i.compress_size >= 0xFFFFFFFF for i in z.infolist()) or len(z.infolist()) >= 0xFFFF:
        src.problems.append("a very large zip (ZIP64)")
    return src


def is_course(names: list[str]) -> bool:
    """A course: a manifest (SCORM, xAPI, cmi5, AICC) or a start page with scripts."""
    low = [n.lower() for n in names]
    return any(n.rsplit("/", 1)[-1] in MANIFESTS or n.endswith((".au", ".crs")) for n in low)


def find_sources(root: Path) -> tuple[list[Source], list[str]]:
    """Every course under root: folders with a manifest, zips (and zips inside them), and the other folders."""
    sources: list[Source] = []
    notes: list[str] = []
    tops = sorted(d for d in root.iterdir() if d.is_dir()) if root.is_dir() else []

    def where(p: Path) -> str:
        top = next((n for n, d in enumerate(tops, 1) if p == d or d in p.parents), 0)
        return f"folder {top} of {len(tops)}" if top else "the top folder"

    course_dirs: list[Path] = []
    if root.is_dir():
        for m in sorted(root.rglob("*")):
            if m.is_file() and m.name.lower() in MANIFESTS and not any(d in m.parents for d in course_dirs):
                course_dirs.append(m.parent)
    for d in course_dirs:
        files = [(p.relative_to(d).as_posix(), p.stat().st_size) for p in d.rglob("*") if p.is_file()]
        src = Source("folder", f"unpacked course in {where(d)}", files, folder=d)
        long_paths = sum(len(str(d / n)) > 240 for n, _ in files)
        if long_paths:
            src.problems.append(f"{long_paths} paths longer than Windows likes (240+ characters)")
        sources.append(src)
    zips = [root] if root.suffix.lower() == ".zip" else sorted(p for p in root.rglob("*.zip") if p.is_file()) if root.is_dir() else []
    per_place: Counter[str] = Counter()
    for zp in zips:
        per_place[where(zp)] += 1
        label = f"zip {per_place[where(zp)]} in {where(zp)}"
        try:
            z = zipfile.ZipFile(zp)
        except (zipfile.BadZipFile, OSError) as e:
            notes.append(f"{label}: cannot be opened ({type(e).__name__}): damaged, or not really a zip")
            continue
        sources += zip_and_inner(z, label, 1, notes)
    if root.is_dir():   # top folders with no course in them: what they hold
        for d in tops:
            if not any(s.folder is not None and (s.folder == d or d in s.folder.parents) for s in sources) and \
                    not any(where(z) == where(d) for z in zips):
                files = [(p.relative_to(d).as_posix(), p.stat().st_size) for p in d.rglob("*") if p.is_file()]
                sources.append(Source("folder", f"{where(d)} (no course manifest)", files, folder=d))
    return sources, notes


def zip_and_inner(z: zipfile.ZipFile, label: str, depth: int, notes: list[str]) -> list[Source]:
    """A zip as a course (when it is one) and every zip inside it, three levels deep."""
    src = zip_source(z, "zip" if depth == 1 else "zip in zip", label)
    out = [src] if is_course([n for n, _ in src.files]) or depth == 1 else []
    inner = [(n, s) for n, s in src.files if n.lower().endswith(".zip") and "__macosx" not in n.lower()]
    for k, (name, size) in enumerate(inner, 1):
        sub = f"zip {k} inside {label}"
        if depth >= 3:
            notes.append(f"{sub}: more than three zips deep, not opened")
            continue
        if size > MAX_NESTED:
            notes.append(f"{sub}: {size / 2**20:.0f} MB, too big to open inside the other zip: unpack it first")
            continue
        try:
            out += zip_and_inner(zipfile.ZipFile(io.BytesIO(z.read(name))), sub, depth + 1, notes)
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError) as e:
            notes.append(f"{sub}: cannot be opened ({type(e).__name__})")
    return out


# --- text and language ---------------------------------------------------------------------------------------------
def language_of(text: str) -> str:
    """English, German or mixed, from how often their most common small words appear (no text is printed)."""
    words = Counter(WORD.findall(text.lower()))
    en, de = sum(words[w] for w in ENGLISH), sum(words[w] for w in GERMAN)
    if en + de < 30:
        return "too little text to tell"
    share = de / (en + de)
    return "German" if share > 0.7 else "English" if share < 0.3 else f"mixed (about {share:.0%} German)"


def human(strings: list[str]) -> list[str]:
    """The strings that read like sentences (4+ words, mostly letters), with HTML tags taken out."""
    out = []
    for s in strings:
        s = re.sub(r"<[^>]+>", " ", s)
        words = s.split()
        if len(words) >= 4 and sum(c.isalpha() for c in s) > 0.6 * max(1, len(s.replace(" ", ""))):
            out.append(s)
    return out


def strings_in(value: Any) -> list[str]:
    """Every string value in JSON data."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings_in(v)]
    if isinstance(value, list):
        return [s for v in value for s in strings_in(v)]
    return []


def json_in(text: str) -> Any:
    """JSON in a file or a script ("var data = {...};"), or None."""
    for candidate in (text.strip(), text[text.find("{"):text.rfind("}") + 1] if "{" in text else ""):
        if candidate:
            try:
                return json.loads(candidate)
            except ValueError:
                continue
    return None


BASE64 = re.compile(r"[\"']([A-Za-z0-9+/=]{800,})[\"']")
JS_STRING = re.compile(r"\"((?:[^\"\\\n]|\\.){20,})\"|'((?:[^'\\\n]|\\.){20,})'")


def hidden_json(text: str) -> list[Any]:
    """JSON hidden in a script as base64 (Articulate Rise keeps a whole course like that)."""
    out = []
    for m in BASE64.finditer(text):
        try:
            data = json.loads(base64.b64decode(m.group(1)).decode("utf-8"))
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        out.append(data)
    return out


# --- shape of data -------------------------------------------------------------------------------------------------
def shape(value: Any, depth: int = 0, key: str = "") -> list[str]:
    """Field names and how many of each, never a value (lists: the shape of their first item)."""
    pad = "      " + "  " * depth
    safe = key if re.fullmatch(r"[A-Za-z_$][\w$-]{0,30}: ", key) or not key else "(other key): "
    if isinstance(value, dict):
        out = [f"{pad}{safe}{{{len(value)} fields}}"] if depth else []
        if depth < 5:
            for k, v in list(value.items())[:30]:
                out += shape(v, depth + 1, f"{k}: ")
        return out
    if isinstance(value, list):
        first = next((v for v in value if isinstance(v, (dict, list))), None)
        return [f"{pad}{safe}[{len(value)} items]"] + (shape(first, depth + 1) if first is not None and depth < 5 else [])
    return [f"{pad}{safe}{type(value).__name__}"] if depth else []


def keys_in(value: Any) -> list[str]:
    """Every field name in JSON data."""
    if isinstance(value, dict):
        return list(value) + [k for v in value.values() for k in keys_in(v)]
    if isinstance(value, list):
        return [k for v in value for k in keys_in(v)]
    return []


# --- media length, pictures' size ----------------------------------------------------------------------------------
def mp4_seconds(f: BinaryIO, size: int) -> float | None:
    """The length of an MP4/M4A/MOV from its 'mvhd' box (the boxes are skipped, not read)."""
    pos = 0
    try:
        while pos + 8 <= size:
            f.seek(pos)
            head = f.read(8)
            if len(head) < 8:
                return None
            box, kind = struct.unpack(">I4s", head)
            if box == 1:
                box = struct.unpack(">Q", f.read(8))[0]
            if kind == b"moov":
                end, pos = pos + box, pos + 8
                while pos + 8 <= end:
                    f.seek(pos)
                    sub, sub_kind = struct.unpack(">I4s", f.read(8))
                    if sub_kind == b"mvhd":
                        version = f.read(1)[0]
                        f.read(3)
                        if version == 1:
                            f.read(16)
                            scale, length = struct.unpack(">IQ", f.read(12))
                        else:
                            f.read(8)
                            scale, length = struct.unpack(">II", f.read(8))
                        return length / scale if scale else None
                    if sub < 8:
                        return None
                    pos += sub
                return None
            if box < 8:
                return None
            pos += box
    except (OSError, struct.error, IndexError):
        return None
    return None


MP3_RATES = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]


def mp3_seconds(head: bytes, size: int) -> float | None:
    """About how long an MP3 is, from its first frame's bit rate."""
    start = head.find(b"\xff\xfb")
    if start < 0 or start + 3 > len(head):
        return None
    rate = MP3_RATES[head[start + 2] >> 4] if (head[start + 2] >> 4) < len(MP3_RATES) else 0
    return size * 8 / (rate * 1000) if rate else None


def picture_size(head: bytes) -> tuple[int, int] | None:
    """Width and height of a PNG, GIF, JPEG or WebP, from its first bytes."""
    try:
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", head[16:24])
        if head[:6] in (b"GIF87a", b"GIF89a"):
            return struct.unpack("<HH", head[6:10])
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            if head[12:16] == b"VP8 ":
                w, h = struct.unpack("<HH", head[26:30])
                return w & 0x3FFF, h & 0x3FFF
            if head[12:16] == b"VP8X":
                return 1 + int.from_bytes(head[24:27], "little"), 1 + int.from_bytes(head[27:30], "little")
        if head[:2] == b"\xff\xd8":
            i = 2
            while i + 9 < len(head):
                if head[i] != 0xFF:
                    i += 1
                    continue
                marker, length = head[i + 1], struct.unpack(">H", head[i + 2:i + 4])[0]
                if marker in (0xC0, 0xC1, 0xC2):
                    h, w = struct.unpack(">HH", head[i + 5:i + 9])
                    return w, h
                i += 2 + length
    except (struct.error, IndexError):
        return None
    return None


def clock(seconds: float) -> str:
    """75 -> '1:15', 3725 -> '1:02:05'."""
    s = int(round(seconds))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def caption_facts(text: str) -> tuple[int, float]:
    """How many lines a captions file has and up to which time it runs."""
    times = re.findall(r"(\d{1,2}:)?(\d{1,2}):(\d{2})[.,](\d{1,3})\s*-->", text)
    last = 0.0
    for h, m, s, _ in times:
        last = max(last, int(h[:-1] or 0) * 3600 + int(m) * 60 + int(s))
    return len(times), last


# --- one course ------------------------------------------------------------------------------------------------------
def group_of(name: str) -> str:
    """The kind of file (page, script, video ...) from its type."""
    ext = Path(name).suffix.lower()
    return next((g for g, exts in GROUPS.items() if ext in exts), f"other ({ext or 'no type'})")


def mac_or_junk(name: str) -> bool:
    """A Mac copy (__MACOSX, ._name) or a system file (.DS_Store, Thumbs.db)."""
    low = name.lower()
    return "__macosx/" in low or Path(low).name.startswith("._") or Path(low).name in (".ds_store", "thumbs.db")


def manifest_facts(src: Source, names: list[str]) -> list[str]:
    """The format (SCORM, xAPI, cmi5, AICC) and what the manifest holds."""
    out = []
    man = next((n for n in names if Path(n.lower()).name in MANIFESTS), "")
    aicc = [n for n in names if n.lower().endswith((".au", ".crs"))]
    if not man:
        return ["- format: " + ("AICC" if aicc else "no course manifest (plain files)")]
    text = src.read(man, 5_000_000).decode("utf-8", errors="ignore")
    low = Path(man.lower()).name
    if low == "imsmanifest.xml":
        version = re.search(r"<(?:\w+:)?schemaversion>\s*([^<]+)", text, re.I)
        out.append(f"- format: SCORM {version.group(1).strip() if version else '(version not given)'}")
    else:
        out.append(f"- format: {'xAPI (Tin Can)' if low == 'tincan.xml' else 'cmi5'}")
    items = len(re.findall(r"<(?:\w+:)?item[\s/>]", text))
    resources = len(re.findall(r"<(?:\w+:)?resource[\s/>]", text))
    scos = len(re.findall(r"scormtype\s*=\s*[\"']sco[\"']", text, re.I))
    listed = len(re.findall(r"<(?:\w+:)?file[\s/>]", text))
    out.append(f"- manifest: {items} lessons/pages, {resources} resources, {scos} SCOs, {listed} files listed")
    flags = [w for w, p in (("pass mark", r"masteryscore|minnormalizedmeasure"), ("sequencing rules", r"imsss:|sequencing"),
                            ("time limit", r"maxtimeallowed|attemptabsoluteduration")) if re.search(p, text, re.I)]
    if flags:
        out.append(f"- manifest also sets: {', '.join(flags)}")
    return out


@dataclass
class Text:
    """What the pages, data files and scripts of a course hold."""
    chunks: dict[str, list[str]] = field(default_factory=lambda: {
        "pages": [], "data files": [], "scripts": [], "data hidden in scripts": [], "xml": []})
    datas: list[tuple[str, Any]] = field(default_factory=list)
    generators: set[str] = field(default_factory=set)
    external: Counter[str] = field(default_factory=Counter)


VIDEO_HOSTS = ("youtube", "youtu.be", "vimeo", "kaltura", "brightcove", "wistia", "vidyard", "microsoftstream",
               "sharepoint", "jwplayer")


def read_one(t: Text, name: str, size: int, raw: str) -> None:
    """The text, data and outside video links of one page, data file or script."""
    ext = Path(name).suffix.lower()
    for host in re.findall(r"https?://([a-z0-9.-]+)", raw, re.I):
        found = next((h for h in VIDEO_HOSTS if h in host.lower()), "")
        if found:
            t.external[found] += 1
    if ext in (".html", ".htm", ".xhtml"):
        t.generators.update(g.strip() for g in re.findall(
            r"<meta[^>]+name=[\"']generator[\"'][^>]+content=[\"']([^\"']{1,60})", raw, re.I))
        t.chunks["pages"] += human([re.sub(r"<(script|style)[\s\S]*?</\1>", " ", raw, flags=re.I)])
    elif ext == ".json":
        data = json_in(raw)
        if data is not None:
            t.datas.append((f"data file ({size / 2**10:.0f} KB)", data))
            t.chunks["data files"] += human(strings_in(data))
    elif ext == ".xml" and Path(name.lower()).name not in MANIFESTS:
        t.chunks["xml"] += human(re.findall(r">([^<>]{20,})<", raw))
    elif ext == ".js":
        data = json_in(raw) if size < 20_000_000 and re.search(r"=\s*\{", raw[:2000]) else None
        if isinstance(data, (dict, list)) and len(json.dumps(data)) > 2000:
            t.datas.append((f"data inside a script ({size / 2**10:.0f} KB)", data))
            t.chunks["data hidden in scripts"] += human(strings_in(data))
        for hidden in hidden_json(raw):
            t.datas.append((f"base64 data inside a script ({size / 2**10:.0f} KB)", hidden))
            t.chunks["data hidden in scripts"] += human(strings_in(hidden))
        t.chunks["scripts"] += human([a or b for a, b in JS_STRING.findall(raw)])


def text_part(src: Source, files: list[tuple[str, int]]) -> tuple[list[str], Text]:
    """Where the readable text is, in which language, and the shape of the data."""
    t = Text()
    budget = MAX_TEXT
    for name, size in sorted(files, key=lambda f: f[1]):
        if Path(name).suffix.lower() in {".html", ".htm", ".xhtml", ".json", ".js", ".xml"} and budget > 0:
            raw = src.read(name, budget).decode("utf-8", errors="ignore")
            budget -= len(raw)
            read_one(t, name, size, raw)
    out = ["- readable text (words, language):"]
    for where, chunks in t.chunks.items():
        if chunks:
            out.append(f"    in {where}: {sum(len(c.split()) for c in chunks):,} words, {language_of(' '.join(chunks))}")
    if len(out) == 1:
        out.append("    none found in pages, data or scripts (the text may be only in pictures, videos or captions)")
    for label, data in sorted(t.datas, key=lambda d: -len(json.dumps(d[1])))[:3]:
        keys = keys_in(data)
        quiz, media, text = (sum(bool(r.search(k)) for k in keys) for r in (QUIZ_KEYS, MEDIA_KEYS, TEXT_KEYS))
        out.append(f"- shape of the {label}: {len(keys)} fields; quiz-like {quiz}, media-like {media}, text-like {text}")
        out += shape(data)[:45]
    return out, t


def media_part(src: Source, files: list[tuple[str, int]]) -> list[str]:
    """Captions (language, length) and every video and audio (length, size, its captions)."""
    out = []
    by_stem: dict[str, list[str]] = {}
    stem_of = lambda n: re.sub(r"[._-]?(en|de|eng|ger|deu|english|german)$", "", Path(n).stem.lower())  # noqa: E731
    for n, _ in files:
        if group_of(n) == "captions":
            text = src.read(n, 5_000_000).decode("utf-8", errors="ignore")
            lines, last = caption_facts(text)
            lang = language_of(re.sub(r"\d{1,2}:\d{2}[:.,\d]*|-->", " ", text))
            by_stem.setdefault(stem_of(n), []).append(lang)
            out.append(f"- captions file ({Path(n).suffix}): {lang}, {lines} lines, runs to {clock(last)}")
    total = 0.0
    for kind in ("video", "audio"):
        for k, (n, s) in enumerate(sorted((f for f in files if group_of(f[0]) == kind), key=lambda f: f[0]), 1):
            ext = Path(n).suffix.lower()
            try:
                with src.open(n) as f:
                    secs = (mp4_seconds(f, s) if ext in (".mp4", ".m4v", ".mov", ".m4a")
                            else mp3_seconds(f.read(4096), s) if ext == ".mp3" else None)
            except (OSError, RuntimeError, NotImplementedError, zipfile.BadZipFile) as e:
                out.append(f"- {kind} {k}: cannot be read ({type(e).__name__})")
                continue
            total += secs or 0
            caps = by_stem.get(stem_of(n))
            out.append(f"- {kind} {k}: {clock(secs) if secs else 'length unknown'}, {s / 2**20:.0f} MB, "
                       f"captions with the same name: {', '.join(caps) if caps else 'none'}")
    if total:
        out.append(f"- all video and audio together: {clock(total)}")
    return out


def pictures_part(src: Source, files: list[tuple[str, int]]) -> list[str]:
    """Pictures by size (icons or slides) and documents inside."""
    sizes: Counter[str] = Counter()
    for n, _ in files:
        if group_of(n) != "image":
            continue
        if n.lower().endswith(".svg"):
            sizes["drawings (svg)"] += 1
            continue
        dims = picture_size(src.read(n, 65_536))
        w = max(dims) if dims else 0
        sizes["size unknown" if not dims else "small, under 200 px (icons, buttons)" if w < 200 else "medium" if w < 800
              else "large, 800 px or more (slides, diagrams, screenshots)"] += 1
    out = ["- pictures: " + "; ".join(f"{k} {v}" for k, v in sizes.most_common())] if sizes else []
    docs = Counter(Path(n).suffix.lower() for n, _ in files if group_of(n) == "document")
    return out + ([f"- documents inside: {dict(docs)}"] if docs else [])


def describe(src: Source) -> list[str]:
    """Everything about one course, as lines to print."""
    junk = [n for n, _ in src.files if mac_or_junk(n)]
    files = [(n, s) for n, s in src.files if not mac_or_junk(n)]
    names = [n for n, _ in files]
    out = [f"\n=== {src.label} ==="] + manifest_facts(src, names)
    text_lines, t = text_part(src, files)
    tools = [name for name, pattern in TOOLS if re.search(pattern, "\n".join(n.lower() for n in names), re.M | re.I)]
    out.append(f"- made with: {', '.join(sorted(tools)) or 'not recognised'}"
               + (f"; pages say generator: {', '.join(sorted(t.generators))}" if t.generators else ""))
    players = sorted((Path(n).name for n in names if Path(n).suffix.lower() in (".js", ".html", ".htm")), key=str.lower)
    if players:
        out.append(f"- page and script file names: {', '.join(players[:25])}{' ...' if len(players) > 25 else ''}")
    kinds: Counter[str] = Counter(group_of(n) for n in names)
    sizes: Counter[str] = Counter()
    for n, s in files:
        sizes[group_of(n)] += s
    out.append(f"- files: {len(files)}, {sum(s for _, s in files) / 2**20:.1f} MB")
    out += [f"    {g}: {kinds[g]} ({sizes[g] / 2**20:.1f} MB)" for g in sorted(kinds, key=lambda g: -kinds[g])]
    out += text_lines + media_part(src, files) + pictures_part(src, files)
    if t.external:
        out.append(f"- links to outside video services: {', '.join(f'{h} {n}' for h, n in t.external.most_common())}")
    quiz_fields = sum(bool(QUIZ_KEYS.search(k)) for _, d in t.datas for k in keys_in(d))
    out.append(f"- signs of a quiz: {sum(bool(QUIZ_KEYS.search(Path(n).stem)) for n in names)} file names"
               + (f", {quiz_fields} data fields" if t.datas else ""))
    problems = list(src.problems) + ([f"{len(junk)} Mac copies or system files (__MACOSX, ._*, .DS_Store): left out"]
                                     if junk else []) + (["Flash files (.swf): cannot be played any more"]
                                                         if kinds.get("flash") else [])
    return out + [f"- note: {p}" for p in problems]


def summary_row(src: Source, lines: list[str]) -> str:
    """One line per course for the table at the end."""
    text = "\n".join(lines)

    def grab(pattern: str, default: str = "-") -> str:
        m = re.search(pattern, text)
        return m.group(1).strip() if m else default
    fmt, tool = grab(r"- format: ([^\n]+)"), grab(r"- made with: ([^;\n]+)")
    media, quiz = grab(r"together: ([^\n]+)", "0:00"), grab(r"signs of a quiz: ([^\n]+)")
    videos, captions = text.count("- video "), text.count("- captions file")
    return f"{src.label} | {fmt} | {tool} | videos {videos} | all media {media} | captions {captions} | quiz signs {quiz}"


def main() -> int:
    """Describe every course under the folder or zip given; print it and save it to scorm_report.txt."""
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    root = Path(" ".join(a for a in sys.argv[1:] if not a.startswith("--")).strip().strip('"'))
    if not root.exists():
        print(f"Not found: {root}")
        return 1
    sources, notes = find_sources(root)
    report = [f"Courses found: {len(sources)}"]
    rows = []
    for src in sources:
        try:
            lines = describe(src)
        except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError, ValueError) as e:
            lines = [f"\n=== {src.label} ===", f"- could not be read: {type(e).__name__}"]
        report += lines
        rows.append(summary_row(src, lines))
    if notes:
        report += ["\n=== zips that were not opened ==="] + [f"- {n}" for n in notes]
    report += ["\n=== in short ===", "where | format | made with | videos | all media | captions files | quiz signs"] + rows
    text = "\n".join(report)
    print(text)
    out = Path(__file__).resolve().parent / "scorm_report.txt"
    try:
        out.write_text(text + "\n", encoding="utf-8")
        print(f"\nSaved to {out}")
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
