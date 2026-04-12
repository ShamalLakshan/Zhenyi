"""
SEC EDGAR Scraper
─────────────────
Accesses SEC EDGAR (Electronic Data Gathering) for company filings.
No API key required. Rate limit: 10 req/sec (strictly enforced).
Reliability: Extremely High (US SEC official system).

EDGAR is the official repository of US company financial reports: 10-K (annual),
10-Q (quarterly), 8-K (material events), proxy statements, etc.
"""

import asyncio
import logging
import time
from typing import Optional

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

SEC_API_URL = "https://data.sec.gov/api/xrls"
SEC_COMPANY_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
HEADERS = {
    "User-Agent": "LLM Research Agent (github.com/council-bot) contact@example.com"
}


class SecEdgarScraper(BaseScraper):
    """Search SEC EDGAR for company financial filings."""

    def __init__(self, config: dict):
        super().__init__("sec_edgar", config)
        self._last_request_time = 0

    async def _fetch(self, query: str) -> list[dict]:
        """
        Search SEC EDGAR for financial filings.
        """
        try:
            results = await asyncio.to_thread(
                self._search_sec,
                query,
                self.results_per_query
            )
            logger.info(f"[sec_edgar] Found {len(results)} filings for: {query[:50]}")
            return results
        
        except Exception as e:
            logger.warning(f"[sec_edgar] Error searching: {e}")
            return []

    def _search_sec(self, query: str, max_results: int) -> list[dict]:
        """
        Search SEC EDGAR for company filings.
        Enforces rate limit: max 10 req/sec.
        Run in thread pool to avoid blocking.
        """
        try:
            import requests
            from urllib.parse import quote
            
            q = query.lower()
            
            # Check if query is SEC-related
            sec_keywords = ["sec", "filing", "10-k", "10-q", "8-k", "stock", "earnings", "ticker", "cik"]
            if not any(kw in q for kw in sec_keywords):
                logger.debug(f"[sec_edgar] Query not SEC-related: {query}")
                return []
            
            # Try to extract company name or ticker
            # Simple heuristic: grab capitalized words or the last word
            company = None
            parts = query.split()
            for part in parts:
                if part.isupper() and len(part) <= 5:  # Likely a ticker
                    company = part
                    break
            
            if not company:
                # Try to find a capitalized term
                for part in parts:
                    if part[0].isupper() and len(part) > 2:
                        company = part
                        break
            
            if not company:
                logger.warning(f"[sec_edgar] Cannot extract company from query: {query}")
                return []
            
            # Search for company CIK
            search_params = {
                "company": company,
                "owner": "exclude",
                "action": "getcompany",
            }
            
            # Enforce rate limit
            now = time.time()
            time_since_last = now - self._last_request_time
            if time_since_last < 0.1:  # 10 req/sec = 0.1s minimum
                time.sleep(0.1 - time_since_last)
            
            logger.debug(f"[sec_edgar] Searching for company: {company}")
            search_resp = requests.get(
                SEC_COMPANY_URL,
                params=search_params,
                headers=HEADERS,
                timeout=self.timeout_seconds
            )
            self._last_request_time = time.time()
            search_resp.raise_for_status()
            
            # Parse HTML to find CIK (very basic parsing)
            html = search_resp.text
            cik = None
            
            # Look for CIK pattern in HTML
            import re
            matches = re.findall(r'/cgi-bin/browse-edgar\?action=getcompany&CIK=(\d+)', html)
            if matches:
                cik = matches[0]
            
            if not cik:
                logger.warning(f"[sec_edgar] CIK not found for: {company}")
                return []
            
            logger.debug(f"[sec_edgar] Found CIK: {cik}")
            
            # Get recent filings for this company
            filings_params = {
                "action": "getcompany",
                "CIK": cik,
                "type": "",  # All types
                "dateb": "",
                "owner": "exclude",
                "count": max_results,
                "search_text": "",
            }
            
            # Rate limit again
            now = time.time()
            time_since_last = now - self._last_request_time
            if time_since_last < 0.1:
                time.sleep(0.1 - time_since_last)
            
            filings_resp = requests.get(
                SEC_COMPANY_URL,
                params=filings_params,
                headers=HEADERS,
                timeout=self.timeout_seconds
            )
            self._last_request_time = time.time()
            filings_resp.raise_for_status()
            
            results = []
            
            # Very basic HTML parsing
            html = filings_resp.text
            lines = html.split('\n')
            
            filing_pattern = re.compile(r'<td[^>]*>([^<]+)</td>')
            
            current_filing = {}
            for line in lines:
                if '10-K' in line or '10-Q' in line or '8-K' in line:
                    parts = filing_pattern.findall(line)
                    if len(parts) >= 4:
                        current_filing = {
                            "source": "sec_edgar",
                            "title": f"{company} - {parts[0].strip()}",
                            "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}",
                            "content": f"Filing Type: {parts[0]}\nDate: {parts[1]}\nCIK: {cik}",
                        }
                        results.append(current_filing)
                        
                        if len(results) >= max_results:
                            break
            
            return results
        
        except Exception as e:
            logger.error(f"[sec_edgar] Search failed: {e}")
            return []
