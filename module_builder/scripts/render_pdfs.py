"""Rasterize every PDF beneath a directory for visual QA."""
from pathlib import Path
import sys

import fitz

root = Path(sys.argv[1])
total = 0
for pdf in sorted(root.rglob("*.pdf")):
    document = fitz.open(pdf)
    page_dir = pdf.parent / "pages"
    page_dir.mkdir(exist_ok=True)
    for index, page in enumerate(document):
        page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).save(page_dir / f"page-{index + 1:03d}.png")
        total += 1
    print(f"{pdf.name}: {len(document)} pages")
print(f"Rendered {total} pages")
