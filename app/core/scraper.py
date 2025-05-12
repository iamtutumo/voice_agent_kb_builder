# app/core/scraper.py
from trafilatura import fetch_url, extract, extract_metadata
from urllib.parse import urljoin, urlparse
from typing import Dict, Any, Set, List
import logging
from bs4 import BeautifulSoup
import re
import httpx
import asyncio

class WebsiteScraper:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.base_domain = ""
        self.visited_urls: Set[str] = set()

    def _is_same_domain(self, url: str) -> bool:
        """Check if URL belongs to the same domain as base_domain"""
        return urlparse(url).netloc == self.base_domain

    def _normalize_url(self, url: str) -> str:
        """Normalize URL by removing fragments, query parameters, and handling trailing slashes consistently"""
        # Remove fragments and query parameters
        clean_url = re.sub(r'#.*$', '', url)
        clean_url = re.sub(r'\?.*$', '', clean_url)
        
        # Parse the URL
        parsed = urlparse(clean_url)
        
        # Clean up the path - remove multiple slashes and handle trailing slash
        path = re.sub(r'/+', '/', parsed.path)  # Replace multiple slashes with single slash
        path = path.rstrip('/')  # Remove trailing slash
        
        # Special case: if it's just domain with no path, return without trailing slash
        if not path:
            return f"{parsed.scheme}://{parsed.netloc}"
        
        # Return with cleaned path
        return f"{parsed.scheme}://{parsed.netloc}{path}"

    def _extract_urls(self, html_content: str, base_url: str) -> Set[str]:
        """Extract all URLs from HTML content that belong to the same domain"""
        soup = BeautifulSoup(html_content, 'html.parser')
        urls = set()
        
        for link in soup.find_all('a'):
            href = link.get('href')
            if href:
                absolute_url = urljoin(base_url, href)
                if self._is_same_domain(absolute_url):
                    normalized_url = self._normalize_url(absolute_url)
                    urls.add(normalized_url)
        
        return urls

    async def discover_urls(self, start_url: str, status_callback=None) -> List[Dict[str, str]]:
        """First phase: Discover all URLs on the site"""
        self.base_domain = urlparse(start_url).netloc
        self.visited_urls = set()
        start_url = self._normalize_url(start_url)
        urls_to_visit = {start_url}
        discovered_urls = []
        failed_urls = []

        if status_callback:
            status_callback(f"Starting scan from: {start_url}")

        while urls_to_visit:
            current_url = urls_to_visit.pop()
            normalized_current_url = self._normalize_url(current_url)
            
            if normalized_current_url in self.visited_urls:
                continue

            try:
                if status_callback:
                    status_callback(f"Scanning: {normalized_current_url}")

                # Basic technical validation - just check if we can download the page
                downloaded = fetch_url(normalized_current_url)
                if not downloaded:
                    if status_callback:
                        status_callback(f"⚠️ Could not access: {normalized_current_url}")
                    failed_urls.append(normalized_current_url)
                    continue

                # Get basic metadata
                metadata = extract_metadata(downloaded)
                
                # Add to discovered URLs if we can access it
                url_info = {
                    "url": normalized_current_url,
                    "title": metadata.title if metadata else None,
                    "type": self._guess_page_type(normalized_current_url)
                }
                discovered_urls.append(url_info)

                if status_callback:
                    status_callback(f"✅ Found: {metadata.title if metadata else normalized_current_url}")

                # Find new URLs to visit
                new_urls = self._extract_urls(downloaded, normalized_current_url)
                new_urls = new_urls - self.visited_urls
                urls_to_visit.update(new_urls)
                self.visited_urls.add(normalized_current_url)

            except Exception as e:
                self.logger.error(f"Error discovering {normalized_current_url}: {str(e)}")
                if status_callback:
                    status_callback(f"❌ Error on {normalized_current_url}: {str(e)}")
                failed_urls.append(normalized_current_url)
                continue

        # Simple summary of failed URLs
        if failed_urls and status_callback:
            status_callback("\nURLs that could not be accessed:")
            for url in failed_urls:
                status_callback(f"  - {url}")

        return discovered_urls

    def _guess_page_type(self, url: str) -> str:
        """Helper to categorize URLs based on their path"""
        path = urlparse(url).path.lower()
        
        if '/product' in path:
            return 'product'
        elif '/service' in path or '/treatment' in path:
            return 'service'
        elif '/blog' in path or '/article' in path or '/news' in path:
            return 'article'
        elif '/about' in path:
            return 'about'
        elif '/contact' in path:
            return 'contact'
        elif '/faq' in path or '/faqs' in path:
            return 'faq'
        else:
            return 'page'

    async def scrape_pages(self, urls_to_scrape: List[str], progress_callback=None) -> Dict[str, Any]:
        """Second phase: Scrape only selected URLs"""
        all_content = {}
        total_urls = len(urls_to_scrape)

        for index, url in enumerate(urls_to_scrape, 1):
            try:
                normalized_url = self._normalize_url(url)
                if progress_callback:
                    progress_callback(f"Scraping {index}/{total_urls}: {normalized_url}", index/total_urls)
                
                # Download and extract content
                downloaded = fetch_url(normalized_url)
                if not downloaded:
                    continue

                # Extract text content
                text_content = extract(downloaded, 
                                    include_comments=False,
                                    include_tables=True,
                                    no_fallback=False)
                
                if text_content:
                    metadata = extract_metadata(downloaded)
                    all_content[normalized_url] = {
                        "content": text_content,
                        "metadata": {
                            "title": metadata.title if metadata else None,
                            "description": metadata.description if metadata else None,
                            "type": self._guess_page_type(normalized_url)
                        }
                    }

                await httpx.AsyncClient().aclose()
                
            except Exception as e:
                self.logger.error(f"Error scraping {normalized_url}: {str(e)}")
                continue

        return all_content