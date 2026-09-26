"""pdftotext -layout wrapper (poppler). Offline only."""
import os
import shutil
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
LOCAL_POPPLER = BACKEND / ".tools" / "poppler" / "Library" / "bin" / "pdftotext.exe"


def pdftotext_bin():
    """PDFTOTEXT env var, then a local poppler copy, then PATH. The parsing rules assume poppler's layout
    (xpdf's pdftotext 4.x scrambles the DESC cost rows)."""
    for cand in (os.environ.get("PDFTOTEXT"), str(LOCAL_POPPLER) if LOCAL_POPPLER.exists() else None,
                 shutil.which("pdftotext")):
        if cand:
            return cand
    raise RuntimeError("pdftotext (poppler-utils) not found. Install poppler or set PDFTOTEXT.")


def pdf_to_text(pdf_path, out_path=None):
    """Layout text of the PDF. Pages are separated by form feeds (\\f)."""
    pdf_path = Path(pdf_path)
    out_path = Path(out_path) if out_path else pdf_path.with_suffix(".txt")
    if not out_path.exists() or out_path.stat().st_mtime < pdf_path.stat().st_mtime:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([pdftotext_bin(), "-layout", str(pdf_path), str(out_path)], check=True)
    return out_path.read_text(encoding="utf-8", errors="replace")
