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

    def _parse_url_path(self, url: str) -> List[str]:
        """Parse URL into path segments for tree building"""
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        
        if not path:
            return ['home']
        
        segments = [seg for seg in path.split('/') if seg]
        return segments

    def _calculate_importance(self, url: str, page_type: str, title: str = None) -> int:
        """Calculate importance score: 3=high, 2=medium, 1=low"""
        path_segments = self._parse_url_path(url)
        depth = len(path_segments)
        
        # Start with base score based on depth
        if depth <= 1:  # Root or one level deep
            score = 3
        elif depth <= 3:  # 2-3 levels deep
            score = 2
        else:  # Very deep
            score = 1
        
        # Boost important page types
        important_types = {'product', 'service', 'about', 'contact', 'faq'}
        if page_type in important_types:
            score = min(3, score + 1)
        
        # Penalty for very generic/common paths
        generic_paths = {'privacy', 'terms', 'legal', 'sitemap', 'search'}
        if any(generic in url.lower() for generic in generic_paths):
            score = max(1, score - 1)
        
        return score

    def _build_tree_structure(self, url_data: List[Dict]) -> Dict:
        """Build hierarchical tree structure from flat URL list"""
        # Create tree nodes
        tree_nodes = {}
        root_nodes = []
        
        for item in url_data:
            url = item['url']
            path_segments = self._parse_url_path(url)
            
            # Create node
            node = {
                'url': url,
                'title': item['title'],
                'type': item['type'],
                'importance': item['importance'],
                'depth': len(path_segments),
                'path_segments': path_segments,
                'children': [],
                'parent_url': None
            }
            
            tree_nodes[url] = node
        
        # Build parent-child relationships
        for url, node in tree_nodes.items():
            segments = node['path_segments']
            
            if len(segments) <= 1:
                # Root level page
                root_nodes.append(node)
            else:
                # Find parent by removing last segment
                parent_segments = segments[:-1]
                
                # Try to find exact parent match
                parent_url = None
                for potential_parent_url, potential_parent in tree_nodes.items():
                    if potential_parent['path_segments'] == parent_segments:
                        parent_url = potential_parent_url
                        break
                
                if parent_url:
                    # Found exact parent
                    tree_nodes[parent_url]['children'].append(node)
                    node['parent_url'] = parent_url
                else:
                    # No exact parent found, try to find closest parent
                    best_parent = None
                    best_match_length = 0
                    
                    for potential_parent_url, potential_parent in tree_nodes.items():
                        parent_path = potential_parent['path_segments']
                        if (len(parent_path) < len(segments) and 
                            segments[:len(parent_path)] == parent_path and
                            len(parent_path) > best_match_length):
                            best_parent = potential_parent_url
                            best_match_length = len(parent_path)
                    
                    if best_parent:
                        tree_nodes[best_parent]['children'].append(node)
                        node['parent_url'] = best_parent
                    else:
                        # No parent found, add to root
                        root_nodes.append(node)
        
        # Sort children by importance, then by name
        for node in tree_nodes.values():
            node['children'].sort(key=lambda x: (-x['importance'], x['title'] or x['url']))
        
        # Sort root nodes
        root_nodes.sort(key=lambda x: (-x['importance'], x['title'] or x['url']))
        
        return {
            'root_nodes': root_nodes,
            'all_nodes': tree_nodes
        }

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
                page_type = self._guess_page_type(normalized_current_url)
                
                # Calculate importance score
                importance = self._calculate_importance(
                    normalized_current_url, 
                    page_type, 
                    metadata.title if metadata else None
                )
                
                # Add to discovered URLs if we can access it
                url_info = {
                    "url": normalized_current_url,
                    "title": metadata.title if metadata else None,
                    "type": page_type,
                    "importance": importance
                }
                discovered_urls.append(url_info)

                if status_callback:
                    stars = "★" * importance + "☆" * (3 - importance)
                    status_callback(f"✅ Found: {metadata.title if metadata else normalized_current_url} ({stars})")

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

    def build_tree_structure(self, discovered_urls: List[Dict]) -> Dict:
        """Build tree structure from discovered URLs - separate method for flexibility"""
        return self._build_tree_structure(discovered_urls)

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