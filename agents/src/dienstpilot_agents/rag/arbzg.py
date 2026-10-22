"""Convert the official ArbZG XML (gesetze-im-internet.de) to the corpus format.

    python -m dienstpilot_agents.rag.arbzg SOURCE.xml [--retrieved YYYY-MM-DD]

The statute is an official work and free to use (§ 5 UrhG). The converter keeps the text word for
word; it only flattens markup. The XML itself is kept in ``agents/rag/source/`` with its SHA-256.
"""

import argparse
import hashlib
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from dienstpilot_agents.rag.corpus import CORPUS_DIR

SOURCE_URL = "https://www.gesetze-im-internet.de/arbzg/"
SOURCE_DIR = CORPUS_DIR.parent / "source"


def _flat(el: ET.Element) -> str:
    parts: list[str] = []

    def walk(e: ET.Element) -> None:
        if e.tag == "BR":
            parts.append(" ")
        if e.tag in ("DT", "LA"):
            parts.append(" ")
        if e.text:
            parts.append(e.text)
        for c in e:
            walk(c)
            if c.tail:
                parts.append(c.tail)

    walk(el)
    return " ".join("".join(parts).split())


def convert(xml_path: Path, retrieved: str) -> str:
    """Return the corpus Markdown of the statute."""
    root = ET.parse(xml_path).getroot()
    builddate = root.attrib["builddate"]
    stand = ""
    for norm in root.findall("norm"):
        meta = norm.find("metadaten")
        if meta is not None and (k := meta.find("standangabe/standkommentar")) is not None:
            stand = (k.text or "").strip()
    version = f"Stand {builddate[:4]}-{builddate[4:6]}-{builddate[6:8]}"
    out = [
        "---",
        "id: arbzg",
        "title: Arbeitszeitgesetz (ArbZG)",
        "language: de",
        "synthetic: false",
        f'version: "{version}"',
        f"source: {SOURCE_URL}",
        f"retrieved: {retrieved}",
        f'note: "Amtlicher Gesetzestext, unverändert; {stand}"',
        "---",
        "",
    ]
    for norm in root.findall("norm"):
        meta = norm.find("metadaten")
        if meta is None or (enbez := meta.find("enbez")) is None:
            continue
        label = (enbez.text or "").strip()
        titel = meta.find("titel")
        title = _flat(titel) if titel is not None else ""
        content = norm.find("textdaten/text/Content")
        if content is None:
            continue
        paras = [_flat(p) for p in content.findall("P") if _flat(p)]
        if not paras:
            continue
        out.append(f"## [{label}] {title}".rstrip())
        for i, p in enumerate(paras, start=1):
            has_n = re.match(r"^\(\d+[a-z]?\)\s", p)
            out.append(p if has_n or len(paras) == 1 else f"({i}) {p}")
        out.append("")
    return "\n".join(out)


def main() -> None:
    """Write the corpus file and keep the source XML with its hash."""
    ap = argparse.ArgumentParser()
    ap.add_argument("xml", type=Path)
    ap.add_argument("--retrieved", required=True)
    args = ap.parse_args()
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.xml, SOURCE_DIR / "arbzg.xml")
    digest = hashlib.sha256(args.xml.read_bytes()).hexdigest()
    (SOURCE_DIR / "arbzg.xml.sha256").write_text(f"{digest}  arbzg.xml\n")
    (CORPUS_DIR / "arbzg.de.md").write_text(convert(args.xml, args.retrieved), encoding="utf-8")


if __name__ == "__main__":
    main()
