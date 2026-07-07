import logging
import json
import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Comment

from app.discovery.content_fetcher import fetch_page_html

logger = logging.getLogger(__name__)


@dataclass
class ArticleDocument:
    url: str
    title: Optional[str]
    html: str
    body_html: str
    body_text: str
    metadata_text: Optional[str] = None
    content_source: str = "bs4"


class ArticleUnderstandingEngine:
    """Cleans page HTML and isolates the content that actually describes startups."""

    REMOVE_SELECTORS = [
        "nav",
        "footer",
        "header",
        "aside",
        "script",
        "style",
        "noscript",
        "form",
        "button",
        "svg",
        "canvas",
        "iframe",
    ]

    NOISE_PATTERNS = re.compile(
        r"(cookie|subscribe|newsletter|advertis|sponsored|related article|read more|"
        r"comments?|sign in|log in|trending|popular posts|share on|accept cookies)",
        re.I,
    )

    def load(self, url: str, html: Optional[str] = None) -> Optional[ArticleDocument]:
        html = html or fetch_page_html(url)
        if not html:
            return None

        readable_html, readable_text = self._extract_readable_content(url, html)
        content_source = "trafilatura" if readable_text else "bs4"
        if readable_text:
            body_text = readable_text
            body_html = readable_html or ""
        else:
            soup = BeautifulSoup(html, "html.parser")
            self._strip_noise(soup)
            main_node = self._select_main_node(soup)
            if not main_node:
                return None

            body_html = str(main_node)
            body_text = main_node.get_text(" ", strip=True)
            readable_html = body_html

        soup = BeautifulSoup(html, "html.parser")
        metadata_text = self._extract_metadata_text(soup)
        if metadata_text and len(body_text) < 200:
            body_text = f"{metadata_text} {body_text}".strip()
        logger.info(
            json.dumps(
                {
                    "stage": "article_engine",
                    "event": "article_readable_content",
                    "article_url": url,
                    "article_title": self._extract_title(soup, url),
                    "original_html_size": len(html),
                    "article_body_length": len(body_text),
                    "cleaned_text_preview": body_text[:500],
                    "content_source": content_source,
                }
            ),
        )
        return ArticleDocument(
            url=url,
            title=self._extract_title(soup, url),
            html=html,
            body_html=body_html,
            body_text=body_text,
            metadata_text=metadata_text,
            content_source=content_source,
        )

    def clean_text(self, url: str, html: Optional[str] = None) -> str:
        document = self.load(url, html)
        return document.body_text if document else ""

    def _strip_noise(self, soup: BeautifulSoup) -> None:
        for selector in self.REMOVE_SELECTORS:
            for node in soup.select(selector):
                node.decompose()

        for node in soup.find_all(string=lambda text: isinstance(text, Comment)):
            node.extract()

        for node in soup.find_all(True):
            attrs = " ".join(filter(None, [
                " ".join(node.get("class", [])),
                node.get("id", ""),
                node.get("role", ""),
                node.get("aria-label", ""),
            ])).lower()
            if self.NOISE_PATTERNS.search(attrs):
                node.decompose()

    def _select_main_node(self, soup: BeautifulSoup):
        for selector in ["article", "main", "[role='main']", ".article-content", ".post-content", ".entry-content"]:
            node = soup.select_one(selector)
            if node and len(node.get_text(" ", strip=True)) > 120:
                return node

        body = soup.body or soup
        paragraphs = body.find_all(["p", "li", "h1", "h2", "h3", "h4"])
        if not paragraphs:
            return body

        text_nodes = [node for node in paragraphs if len(node.get_text(" ", strip=True)) > 20]
        if text_nodes:
            wrapper = BeautifulSoup("<div></div>", "html.parser").div
            for node in text_nodes:
                wrapper.append(node)
            return wrapper
        return body

    def _extract_title(self, soup: BeautifulSoup, url: str) -> Optional[str]:
        for selector in ["meta[property='og:title']", "title", "h1"]:
            node = soup.select_one(selector)
            if not node:
                continue
            if selector.startswith("meta"):
                content = node.get("content")
                if content:
                    return content.strip()
            else:
                text = node.get_text(strip=True)
                if text:
                    return text

        path = urlparse(url).path.rsplit("/", 1)[-1]
        return path.replace("-", " ").replace("_", " ").strip() or None

    def _extract_readable_content(self, url: str, html: str) -> tuple[Optional[str], Optional[str]]:
        try:
            import trafilatura
        except Exception:
            return None, None

        try:
            text = trafilatura.extract(
                html,
                url=url,
                include_comments=False,
                include_tables=False,
                favor_precision=True,
            )
            if not text:
                return None, None

            html_output = trafilatura.extract(
                html,
                url=url,
                include_comments=False,
                include_tables=False,
                output_format="html",
                favor_precision=True,
            )
            cleaned_text = text.strip()
            if len(cleaned_text.split()) < 40:
                return None, None
            return html_output, cleaned_text
        except Exception:
            return None, None

    def _extract_metadata_text(self, soup: BeautifulSoup) -> Optional[str]:
        values = []
        for attrs in [
            {"property": "og:title"},
            {"name": "title"},
            {"property": "og:description"},
            {"name": "description"},
            {"name": "twitter:description"},
        ]:
            node = soup.find("meta", attrs=attrs)
            if node and node.get("content"):
                value = node["content"].strip()
                if value and value not in values:
                    values.append(value)
        return " ".join(values) if values else None
