"""
Ingestion & Document Cleaning Engine
────────────────────────────────────
High-performance text extraction for niche research:
- Web scraping extraction via trafilatura (strips cookies, ads, navigation, headers).
- Academic PDF text extraction via pypdf (handles ArXiv & open-access preprints).
- Jina AI Reader proxy integration (https://r.jina.ai/<url>) for pristine LLM markdown.
- Paragraph-aware semantic chunking with overlap.
"""

import io
import re
import logging
from typing import Optional, List
import httpx

try:
    import trafilatura
except ImportError:
    trafilatura = None

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) ZhenyiResearchBot/2.0 (Clean Ingestion Engine)"


class DocumentCleaner:
    """Extracts high-signal readable text from raw web HTML, PDFs, and remote URLs."""

    @staticmethod
    def clean_html(html_text: str, base_url: str = "") -> str:
        """
        Extract clean article body text using trafilatura.
        Strips navigation, ads, footers, scripts, and boilerplate.
        """
        if not html_text or not html_text.strip():
            return ""

        if trafilatura is not None:
            try:
                extracted = trafilatura.extract(
                    html_text,
                    url=base_url or None,
                    include_comments=False,
                    include_tables=True,
                    no_fallback=False,
                    favor_precision=True,
                )
                if extracted and len(extracted.strip()) > 50:
                    return extracted.strip()
            except Exception as e:
                logger.debug(f"[DocumentCleaner] trafilatura extraction failed: {e}")

        # Fallback regex-based clean
        return DocumentCleaner._fallback_html_strip(html_text)

    @staticmethod
    def _fallback_html_strip(html_text: str) -> str:
        """Lightweight regex stripper for HTML when trafilatura is unavailable or yields empty."""
        text = re.sub(r"<(script|style|header|footer|nav)[\s\S]*?</\1>", " ", html_text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&[a-z]+;", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def clean_pdf(pdf_bytes: bytes, max_pages: int = 8) -> str:
        """
        Extract clean text from PDF binary data (e.g. ArXiv preprints).
        Extracts up to max_pages to focus on abstract, methods, results, and conclusion.
        """
        if not pdf_bytes or PdfReader is None:
            return ""

        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            extracted_pages = []
            total_pages = len(reader.pages)
            pages_to_read = min(total_pages, max_pages)

            for i in range(pages_to_read):
                page = reader.pages[i]
                text = page.extract_text() or ""
                if text.strip():
                    extracted_pages.append(text.strip())

            full_text = "\n\n".join(extracted_pages)
            # Normalize whitespace and hyphenated line breaks
            full_text = re.sub(r"(\w+)-\n(\w+)", r"\1\2", full_text)
            full_text = re.sub(r"[ \t]+", " ", full_text)
            return full_text.strip()
        except Exception as e:
            logger.warning(f"[DocumentCleaner] PDF extraction error: {e}")
            return ""

    @staticmethod
    async def fetch_jina_markdown(target_url: str, timeout: float = 12.0) -> Optional[str]:
        """
        Fetch webpage through Jina AI Reader (https://r.jina.ai/<url>).
        100% free proxy that converts complex Javascript / HTML pages into clean markdown.
        """
        if not target_url or not target_url.startswith("http"):
            return None

        jina_url = f"https://r.jina.ai/{target_url}"
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                res = await client.get(
                    jina_url,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "text/plain, text/markdown",
                        "X-No-Cache": "true",
                    }
                )
                if res.status_code == 200 and len(res.text.strip()) > 80:
                    return res.text.strip()
        except Exception as e:
            logger.debug(f"[DocumentCleaner] Jina reader failed for {target_url}: {e}")

        return None

    @staticmethod
    def chunk_text(
        text: str,
        max_chunk_chars: int = 1500,
        overlap_chars: int = 150
    ) -> List[str]:
        """
        Split a long document into clean, paragraph-delimited chunks with overlap.
        Preserves complete paragraphs or sentences whenever possible.
        """
        if not text or len(text) <= max_chunk_chars:
            return [text.strip()] if text and text.strip() else []

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks = []
        current_chunk = []
        current_len = 0

        for para in paragraphs:
            para_len = len(para)
            if current_len + para_len + 2 > max_chunk_chars:
                if current_chunk:
                    chunk_str = "\n\n".join(current_chunk)
                    chunks.append(chunk_str)
                    overlap_seed = chunk_str[-overlap_chars:] if len(chunk_str) > overlap_chars else ""
                    current_chunk = [overlap_seed, para] if overlap_seed else [para]
                    current_len = sum(len(p) for p in current_chunk) + len(current_chunk) * 2
                else:
                    sentences = re.split(r"(?<=[.!?])\s+", para)
                    sub_chunk = []
                    sub_len = 0
                    for sent in sentences:
                        if sub_len + len(sent) > max_chunk_chars:
                            if sub_chunk:
                                chunks.append(" ".join(sub_chunk))
                            sub_chunk = [sent]
                            sub_len = len(sent)
                        else:
                            sub_chunk.append(sent)
                            sub_len += len(sent) + 1
                    if sub_chunk:
                        chunks.append(" ".join(sub_chunk))
                    current_chunk = []
                    current_len = 0
            else:
                current_chunk.append(para)
                current_len += para_len + 2

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return [c.strip() for c in chunks if len(c.strip()) > 30]
