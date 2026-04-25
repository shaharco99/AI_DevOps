"""Website Content Scraping and Ingestion Pipeline.

Provides tools to scrape website content and ingest it into the RAG system.

Supported scrapers:
- BeautifulSoup: For simple HTML parsing
- Playwright: For JavaScript-heavy sites

Example:
    >>> from ai_devops_assistant.rag.scraper import WebScraper
    >>> scraper = WebScraper()
    >>> content = await scraper.scrape_url("https://example.com")
    >>> await scraper.ingest_content(content, source_url)
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class ScrapedContent:
    """Scraped web content."""

    url: str
    title: str
    content: str
    metadata: dict
    links: list[str]
    source_type: str = "web"


class WebScraper:
    """Web scraping interface using BeautifulSoup."""

    def __init__(
        self,
        user_agent: str = "AI-DevOps-Assistant/1.0",
        timeout: int = 30,
        max_workers: int = 5,
    ):
        """Initialize web scraper.

        Args:
            user_agent: User agent string
            timeout: Request timeout in seconds
            max_workers: Maximum concurrent workers
        """
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_workers = max_workers
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None:
            headers = {"User-Agent": self.user_agent}
            self.session = aiohttp.ClientSession(headers=headers)
        return self.session

    async def scrape_url(self, url: str, include_links: bool = True) -> Optional[ScrapedContent]:
        """Scrape content from a single URL.

        Args:
            url: URL to scrape
            include_links: Whether to extract links

        Returns:
            ScrapedContent or None if failed
        """
        try:
            session = await self._get_session()

            async with session.get(url, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                if resp.status != 200:
                    logger.warning(f"Failed to fetch {url}: {resp.status}")
                    return None

                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")

                # Extract title
                title = ""
                title_tag = soup.find("title")
                if title_tag:
                    title = title_tag.get_text(strip=True)

                # Extract main content
                content = self._extract_text(soup)

                # Extract links
                links = []
                if include_links:
                    links = self._extract_links(soup, url)

                # Extract metadata
                metadata = self._extract_metadata(soup, url)

                return ScrapedContent(
                    url=url,
                    title=title,
                    content=content,
                    metadata=metadata,
                    links=links,
                )

        except asyncio.TimeoutError:
            logger.error(f"Timeout scraping {url}")
            return None
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return None

    def _extract_text(self, soup: BeautifulSoup) -> str:
        """Extract readable text from HTML.

        Args:
            soup: BeautifulSoup object

        Returns:
            Extracted text
        """
        # Remove script and style tags
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()

        # Get text
        lines = (line.strip() for line in soup.stripped_strings)
        text = "\n".join(lines)

        # Clean up extra whitespace
        text = "\n".join(line for line in text.split("\n") if line.strip())

        return text

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """Extract links from HTML.

        Args:
            soup: BeautifulSoup object
            base_url: Base URL for relative links

        Returns:
            List of absolute URLs
        """
        links = []
        seen = set()

        for link in soup.find_all("a", href=True):
            href = link["href"]

            # Skip fragments and anchors
            if href.startswith("#"):
                continue

            # Convert relative to absolute
            absolute_url = urljoin(base_url, href)

            # Only include same domain
            if (
                urlparse(absolute_url).netloc == urlparse(base_url).netloc
                and absolute_url not in seen
            ):
                links.append(absolute_url)
                seen.add(absolute_url)

        return links[:50]  # Limit to 50 links

    def _extract_metadata(self, soup: BeautifulSoup, url: str) -> dict:
        """Extract metadata from HTML.

        Args:
            soup: BeautifulSoup object
            url: URL

        Returns:
            Metadata dictionary
        """
        metadata = {"url": url}

        # Extract description
        desc = soup.find("meta", {"name": "description"})
        if desc:
            metadata["description"] = desc.get("content", "")

        # Extract keywords
        keywords = soup.find("meta", {"name": "keywords"})
        if keywords:
            metadata["keywords"] = keywords.get("content", "").split(",")

        # Extract language
        html_tag = soup.find("html")
        if html_tag:
            metadata["language"] = html_tag.get("lang", "en")

        return metadata

    async def scrape_urls(self, urls: list[str]) -> list[ScrapedContent]:
        """Scrape multiple URLs concurrently.

        Args:
            urls: List of URLs to scrape

        Returns:
            List of ScrapedContent objects
        """
        semaphore = asyncio.Semaphore(self.max_workers)

        async def scrape_with_semaphore(url):
            async with semaphore:
                return await self.scrape_url(url)

        results = await asyncio.gather(
            *[scrape_with_semaphore(url) for url in urls], return_exceptions=True
        )

        return [r for r in results if isinstance(r, ScrapedContent)]

    async def close(self):
        """Clean up session."""
        if self.session:
            await self.session.close()


class SitemapScraper:
    """Scraper for sitemap-based discovery."""

    def __init__(self, scraper: WebScraper):
        """Initialize with WebScraper.

        Args:
            scraper: WebScraper instance
        """
        self.scraper = scraper

    async def scrape_from_sitemap(
        self, sitemap_url: str, max_pages: int = 100
    ) -> list[ScrapedContent]:
        """Scrape pages from sitemap.

        Args:
            sitemap_url: URL to sitemap.xml
            max_pages: Maximum pages to scrape

        Returns:
            List of ScrapedContent objects
        """
        try:
            session = await self.scraper._get_session()

            # Fetch sitemap
            async with session.get(
                sitemap_url,
                timeout=aiohttp.ClientTimeout(total=self.scraper.timeout),
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to fetch sitemap: {resp.status}")
                    return []

                xml = await resp.text()

            # Parse URLs from sitemap
            soup = BeautifulSoup(xml, "xml")
            urls = []

            for loc in soup.find_all("loc"):
                url = loc.get_text(strip=True)
                if url and len(urls) < max_pages:
                    urls.append(url)

            logger.info(f"Found {len(urls)} URLs in sitemap")

            # Scrape all URLs
            return await self.scraper.scrape_urls(urls)

        except Exception as e:
            logger.error(f"Error scraping sitemap: {e}")
            return []


class RobotsTxtParser:
    """Parser for robots.txt to respect crawling rules."""

    def __init__(self, scraper: WebScraper):
        """Initialize with WebScraper.

        Args:
            scraper: WebScraper instance
        """
        self.scraper = scraper

    async def is_url_allowed(self, url: str) -> bool:
        """Check if URL is allowed by robots.txt.

        Args:
            url: URL to check

        Returns:
            True if URL is allowed to be crawled
        """
        try:
            parsed = urlparse(url)
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

            session = await self.scraper._get_session()

            async with session.get(
                robots_url,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    # If robots.txt not found, allow crawling
                    return True

                content = await resp.text()

                # Simple check: if /disallow: / is present, don't crawl
                if "/disallow: /" in content.lower():
                    logger.debug(f"URL {url} disallowed by robots.txt")
                    return False

                return True

        except Exception as e:
            logger.warning(f"Error checking robots.txt: {e}")
            # Allow crawling on error
            return True
