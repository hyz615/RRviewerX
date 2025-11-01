from typing import Optional, List
from pypdf import PdfReader
from docx import Document
import pandas as pd
import io
import re
from bs4 import BeautifulSoup
try:
    import os
    import pytesseract
    from PIL import Image
    # Allow overriding tesseract path via env (Windows common)
    _tc = os.getenv("TESSERACT_CMD")
    if _tc:
        try:
            pytesseract.pytesseract.tesseract_cmd = _tc
        except Exception:
            pass
except Exception:
    pytesseract = None
    Image = None


def sniff_and_read(filename: str, raw: bytes) -> Optional[str]:
    name = (filename or "").lower()
    try:
        if name.endswith(".pdf"):
            reader = PdfReader(io.BytesIO(raw))
            chunks = []
            for page in reader.pages:
                chunks.append(page.extract_text() or "")
            return "\n".join(chunks).strip()
        if name.endswith(".docx"):
            doc = Document(io.BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs)
        if name.endswith(".xlsx"):
            df = pd.read_excel(io.BytesIO(raw))
            return df.to_csv(index=False)
        if name.endswith(".csv"):
            return raw.decode(errors="ignore")
        if name.endswith(".txt"):
            return raw.decode(errors="ignore")
    except Exception:
        return None
    return None
from typing import Optional


def read_pdf_bytes(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        texts = []
        for page in reader.pages:
            txt = page.extract_text() or ""
            texts.append(txt)
        return "\n".join(texts)
    except Exception:
        return ""


def read_docx_bytes(data: bytes) -> str:
    try:
        import io
        from docx import Document
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception:
        return ""


def read_xlsx_bytes(data: bytes) -> str:
    try:
        import io
        import pandas as pd
        with pd.ExcelFile(io.BytesIO(data)) as xl:
            texts = []
            for sheet in xl.sheet_names:
                df = xl.parse(sheet)
                texts.append(df.to_csv(index=False))
        return "\n".join(texts)
    except Exception:
        return ""


def read_pptx_bytes(data: bytes) -> str:
    """Extract text from PPTX slides and tables."""
    try:
        import io
        from pptx import Presentation
        prs = Presentation(io.BytesIO(data))
        chunks: List[str] = []
        for slide in prs.slides:
            # Shapes with text
            for shape in slide.shapes:
                # Text bodies
                if hasattr(shape, "text") and shape.text:
                    chunks.append(str(shape.text))
                # Tables
                try:
                    if getattr(shape, "has_table", False):
                        tbl = shape.table
                        for r in tbl.rows:
                            row_cells = []
                            for c in r.cells:
                                try:
                                    row_cells.append(c.text or "")
                                except Exception:
                                    row_cells.append("")
                            if any(t.strip() for t in row_cells):
                                chunks.append("\t".join(row_cells))
                except Exception:
                    # ignore non-table shapes
                    pass
                # Pictures -> OCR if available
                try:
                    if getattr(shape, "shape_type", None) and str(shape.shape_type).lower().endswith("picture"):
                        image = getattr(getattr(shape, "image", None), "blob", None)
                        if image and pytesseract and Image:
                            txt = ocr_image_bytes(image)
                            if txt and txt.strip():
                                chunks.append(txt.strip())
                except Exception:
                    pass
        return "\n".join([c for c in chunks if c is not None]).strip()
    except Exception:
        return ""


def read_html_bytes(data: bytes) -> str:
    """Extract meaningful text from HTML, avoiding boilerplate.
    - Keeps <title>
    - Removes script/style/noscript/svg/math/nav/header/footer/aside elements
    - Prefers main/article, falls back to body
    - Captures headings, paragraphs, list items
    - Includes <img alt> and figcaption as hints
    """
    try:
        # try utf-8 first; fallback to chardetless ignore
        try:
            html = data.decode('utf-8')
        except Exception:
            html = data.decode(errors='ignore')
        soup = BeautifulSoup(html, 'html.parser')
        # Drop noise
        for tag in soup(['script','style','noscript','template','svg','canvas','math','iframe','header','footer','nav','aside']):
            tag.decompose()
        title = (soup.title.string or '').strip() if soup.title else ''
        main = soup.find(['main','article']) or soup.body or soup
        parts: List[str] = []
        if title:
            parts.append(title)
        # Collect structured text
        def push(s: str):
            s = (s or '').strip()
            if s:
                parts.append(re.sub(r"\s+", " ", s))
        for el in main.find_all(['h1','h2','h3','h4','h5','h6','p','li','figcaption']):
            # images -> alt
            for img in el.find_all('img'):
                alt = (img.get('alt') or '').strip()
                if alt:
                    push(alt)
            text = el.get_text(separator=' ', strip=True)
            push(text)
        # Fallback if nothing collected: use body text
        if not parts:
            txt = main.get_text(separator=' ', strip=True)
            push(txt)
        # Join and trim excessive whitespace
        out = '\n'.join([p for p in parts if p])
        out = re.sub(r"\n{3,}", "\n\n", out)
        return out.strip()
    except Exception:
        return ""


def ocr_image_bytes(data: bytes) -> str:
    if not pytesseract or not Image:
        return ""
    try:
        img = Image.open(io.BytesIO(data))
        return pytesseract.image_to_string(img)
    except Exception:
        return ""


def sniff_and_read(filename: str, data: bytes) -> str:
    lower = filename.lower()
    # HTML
    if lower.endswith('.html') or lower.endswith('.htm'):
        return read_html_bytes(data)
    if lower.endswith(".pdf"):
        # Try text first; optionally OCR if nearly empty
        text = read_pdf_bytes(data)
        if len(text.strip()) < 10:
            # Try naive OCR of first page raster if available (best-effort)
            # Many PDFs need specialized libs; here only fallback if data itself is an image
            ocr = ocr_image_bytes(data)
            if ocr:
                return ocr
        return text
    if lower.endswith(".docx"):
        return read_docx_bytes(data)
    if lower.endswith(".xlsx") or lower.endswith(".xls"):
        return read_xlsx_bytes(data)
    if lower.endswith(".pptx"):
        return read_pptx_bytes(data)
    if lower.endswith(".ppt"):
        # Legacy PPT not directly supported; best-effort: try decode
        try:
            return data.decode("utf-8", errors="ignore")
        except Exception:
            return ""
    if any(lower.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")):
        # Try OCR for images
        text = ocr_image_bytes(data)
        if text:
            # Normalize whitespace
            return re.sub(r"[ \t\x0b\f\r]+", " ", text).strip()
        return ""
    # fallback: try decode
    # If looks like HTML, run html extractor
    try:
        head = data[:512].decode('utf-8', errors='ignore').lower()
        if '<html' in head or '<!doctype html' in head:
            return read_html_bytes(data)
    except Exception:
        pass
    try:
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""
