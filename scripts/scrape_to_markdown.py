#!/usr/bin/env python3
"""
Scrape ≥ 30 articles from support.optisigns.com, convert to clean Markdown, and save as <id>-<slug>.md.

Features:
- Crawls from one or more start URLs within the support.optisigns.com help center
- Collects unique article pages ("/articles/<id>-<slug>") until a target count is reached
- Extracts main content and converts to Markdown
- Preserves headings and code blocks; removes nav/ads via content extraction
- Prepends an "Article URL:" line for citation
- Optionally rewrites internal article links to local relative files when those articles are also scraped

Usage:
  # Auto-crawl and save to the repo's articles directory by default
  python scripts/scrape_to_markdown.py

  # Optional flags
  python scripts/scrape_to_markdown.py \
    --out-dir /absolute/or/relative/path/to/articles \
    --max-articles 40 \
    --locale en-us

Notes:
- Uses trafilatura for boilerplate removal and Markdown conversion
- Filenames: <id>-<slug>.md to avoid collisions
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import urllib3
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

# Suppress SSL warnings for LibreSSL compatibility
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", message=".*LibreSSL.*")

import requests
from bs4 import BeautifulSoup
import json

try:
    import trafilatura
except Exception as exc:
    raise SystemExit("Missing dependency: trafilatura. Run: pip install -r requirements.txt") from exc

try:
    from markdownify import markdownify as html_to_markdown
except Exception as exc:
    raise SystemExit("Missing dependency: markdownify. Run: pip install -r requirements.txt") from exc


HELP_CENTER_DOMAIN = "support.optisigns.com"
ARTICLE_PATH_REGEX = re.compile(r"^/hc/[^/]+/articles/(\d+)(?:-([A-Za-z0-9\-]+))?/?$")
ABS_ARTICLE_REGEX = re.compile(r"^https?://(?:www\.)?support\.optisigns\.com/hc/[^/]+/articles/(\d+)(?:-([A-Za-z0-9\-]+))?/?$")


@dataclass(frozen=True)
class ArticleRef:
    url: str
    article_id: str
    slug: str

    @property
    def filename(self) -> str:
        safe_slug = self.slug or "article"
        return f"{self.article_id}-{safe_slug}.md"


def normalize_url(href: str, base_url: str) -> Optional[str]:
    if not href:
        return None
    if href.startswith("//"):
        href = "https:" + href
    if href.startswith("http://") or href.startswith("https://"):
        return href
    # relative
    if href.startswith("/"):
        # build absolute from domain in base_url
        m = re.match(r"^(https?://[^/]+)", base_url)
        if not m:
            return None
        return m.group(1) + href
    # anchor or relative path
    if href.startswith("#"):
        return base_url.split("#")[0] + href
    # relative subpath
    if base_url.endswith("/"):
        return base_url + href
    # strip filename
    return base_url.rsplit("/", 1)[0] + "/" + href


def parse_article_ref(url: str) -> Optional[ArticleRef]:
    # Accept absolute or relative URL
    m = ABS_ARTICLE_REGEX.match(url)
    if m:
        article_id, slug = m.group(1), (m.group(2) or "").strip("-")
        return ArticleRef(url=url, article_id=article_id, slug=slug)

    # try to identify domain and path
    if HELP_CENTER_DOMAIN in url:
        try:
            path = url.split(HELP_CENTER_DOMAIN, 1)[1]
        except Exception:
            return None
        if not path.startswith("/"):
            path = "/" + path
        m = ARTICLE_PATH_REGEX.match(path)
        if m:
            article_id, slug = m.group(1), (m.group(2) or "").strip("-")
            return ArticleRef(url=url, article_id=article_id, slug=slug)
    return None


def is_same_domain(url: str) -> bool:
    return HELP_CENTER_DOMAIN in url


def extract_links(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    hrefs: List[str] = []
    for a in soup.select("a[href]"):
        abs_url = normalize_url(a["href"], base_url)
        if abs_url:
            hrefs.append(abs_url)
    return hrefs


def fetch(url: str, timeout: int = 20) -> Optional[str]:
    try:
        r = requests.get(url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (compatible; OptiBotScraper/1.0)"
        }, verify=False)  # Disable SSL verification for LibreSSL compatibility
        if r.status_code == 200:
            return r.text
        return None
    except requests.RequestException:
        return None


def crawl_article_urls(start_urls: List[str], target_count: int) -> List[ArticleRef]:
    queue: List[str] = list(dict.fromkeys(start_urls))
    seen_pages: Set[str] = set()
    collected: Dict[str, ArticleRef] = {}

    while queue and len(collected) < target_count:
        url = queue.pop(0)
        if url in seen_pages:
            continue
        seen_pages.add(url)

        html = fetch(url)
        if not html:
            continue
        for link in extract_links(html, url):
            if not is_same_domain(link):
                continue
            ref = parse_article_ref(link)
            if ref:
                collected.setdefault(ref.url, ref)
                if len(collected) >= target_count:
                    break
            else:
                # continue crawling category/section pages
                if link not in seen_pages and "/hc/" in link and "/articles/" not in link:
                    queue.append(link)
    return list(collected.values())


def extract_markdown(article_url: str) -> Optional[str]:
    downloaded = trafilatura.fetch_url(article_url)
    if not downloaded:
        return None
    md = trafilatura.extract(
        downloaded,
        output_format="markdown",
        include_links=True,
        include_formatting=True,
        no_fallback=True,
    )
    return md


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9\-\s]", "", text)
    text = re.sub(r"[\s\-]+", "-", text)
    return text.strip("-")


def fetch_articles_via_api(locale: str, max_articles: int) -> List[dict]:
    """Fetch articles using Zendesk Help Center API v2.
    
    This is the recommended approach as it:
    - Avoids rate limiting and 403 errors
    - Provides clean, structured data
    - Includes metadata like last_edited_at for change detection
    - Returns only published articles
    """
    results: List[dict] = []
    page = 1
    per_page = min(100, max_articles)
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; OptiBotScraper/1.0)",
        "Accept": "application/json",
    })

    print(f"Fetching articles from Zendesk API (locale: {locale})...")
    
    while len(results) < max_articles:
        url = f"https://{HELP_CENTER_DOMAIN}/api/v2/help_center/{locale}/articles.json?page={page}&per_page={per_page}&sort_by=updated_at&sort_order=desc"
        try:
            r = session.get(url, timeout=30, verify=False)  # Disable SSL verification for LibreSSL compatibility
            if r.status_code != 200:
                print(f"API request failed with status {r.status_code}: {r.text[:200]}")
                break
            data = r.json()
        except Exception as e:
            print(f"API request failed: {e}")
            break

        articles = data.get("articles", [])
        if not articles:
            print(f"No more articles found on page {page}")
            break
            
        # Filter for published articles only
        published_articles = [a for a in articles if a.get("draft", False) == False]
        results.extend(published_articles)
        
        print(f"Page {page}: found {len(articles)} articles, {len(published_articles)} published")
        
        if not data.get("next_page"):
            print("No more pages available")
            break
        page += 1

    print(f"Total articles fetched: {len(results)}")
    return results[:max_articles]


def convert_api_article_to_markdown(article: dict) -> Tuple[str, str]:
    """Convert Zendesk article HTML to clean Markdown.
    
    Preserves:
    - Headings (H1-H6)
    - Code blocks and inline code
    - Lists (ordered and unordered)
    - Links (with proper formatting)
    - Tables
    - Images (with alt text)
    
    Removes:
    - Navigation elements
    - Advertisements
    - Unnecessary styling
    """
    title = article.get("title") or "Untitled"
    html_body = article.get("body") or ""
    source_url = article.get("html_url") or ""
    
    # Clean HTML before conversion
    soup = BeautifulSoup(html_body, "lxml")
    
    # Remove common navigation/ad elements
    for selector in [
        "nav", ".nav", "#nav",
        ".breadcrumb", ".breadcrumbs",
        ".advertisement", ".ads", "[class*='ad']",
        ".sidebar", ".side-nav",
        ".footer", ".footer-nav",
        ".social-share", ".share-buttons"
    ]:
        for elem in soup.select(selector):
            elem.decompose()
    
    # Convert to Markdown with specific options for better formatting
    md = html_to_markdown(
        str(soup),
        heading_style="ATX",  # Use # style headings
        bullets="-",          # Use - for unordered lists
        code_language="",     # Don't add language hints to code blocks
        strip=["script", "style", "meta", "link"]  # Remove script/style tags
    )
    
    # Post-process for better formatting
    md = clean_markdown_content(md)
    md = ensure_h1(title, md or "")
    
    return md, source_url


def clean_markdown_content(md: str) -> str:
    """Post-process Markdown for better formatting and consistency."""
    if not md:
        return md
    
    lines = md.split('\n')
    cleaned_lines = []
    
    for line in lines:
        # Remove excessive whitespace
        line = line.rstrip()
        
        # Fix common markdown issues
        # Ensure proper spacing around headings
        if line.startswith('#'):
            if cleaned_lines and cleaned_lines[-1] != '':
                cleaned_lines.append('')
            cleaned_lines.append(line)
            cleaned_lines.append('')
            continue
            
        # Ensure proper spacing around lists
        if line.startswith(('- ', '* ', '+ ')) or re.match(r'^\d+\. ', line):
            if cleaned_lines and cleaned_lines[-1] != '':
                cleaned_lines.append('')
            cleaned_lines.append(line)
            continue
            
        # Ensure proper spacing around code blocks
        if line.startswith('```'):
            if cleaned_lines and cleaned_lines[-1] != '':
                cleaned_lines.append('')
            cleaned_lines.append(line)
            continue
            
        # Normal text
        cleaned_lines.append(line)
    
    # Remove trailing empty lines
    while cleaned_lines and cleaned_lines[-1] == '':
        cleaned_lines.pop()
    
    return '\n'.join(cleaned_lines)


def ensure_h1(title: str, md: str) -> str:
    text = md.lstrip()
    if text.startswith("# ") or text.startswith("#\t"):
        return md
    return f"# {title}\n\n" + md


def extract_title(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "lxml")
    # Zendesk HC articles typically have <h1 class="...">Title</h1>
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(strip=True)
    return None


def rewrite_internal_links(md: str, url_to_filename: Dict[str, str]) -> str:
    # Replace links to known internal article URLs with local relative filenames
    def repl(match: re.Match[str]) -> str:
        text = match.group(1)
        link = match.group(2)
        # normalize variants: remove trailing slash, anchors kept
        link_no_anchor, anchor = (link.split('#', 1) + [""])[:2]
        link_key = link_no_anchor.rstrip('/')
        if link_key in url_to_filename:
            local = url_to_filename[link_key]
            if anchor:
                return f"[{text}](./{local}#{anchor})"
            return f"[{text}](./{local})"
        return match.group(0)

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", repl, md)


def save_markdown(out_dir: Path, ref: ArticleRef, title: Optional[str], md: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    header = f"Article URL: {ref.url}\n\n"
    final_md = header + ensure_h1(title or ref.slug or ref.article_id, md)
    target = out_dir / ref.filename
    target.write_text(final_md, encoding="utf-8")
    return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape support.optisigns.com to Markdown")
    # Default out-dir to the repository's articles directory
    default_out = (Path(__file__).resolve().parents[1] / "articles")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=default_out,
        help=f"Output directory for Markdown files (default: {default_out})",
    )
    parser.add_argument(
        "--start-url",
        action="append",
        default=["https://support.optisigns.com/hc/en-us"],
        help="Start URL(s) for crawling (used only if API fallback is needed)",
    )
    parser.add_argument("--max-articles", type=int, default=45, help="Max number of articles to scrape")
    parser.add_argument("--locale", default="en-us", help="Help Center locale, e.g. en-us")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    # Resolve to absolute path if relative was provided
    args.out_dir = args.out_dir.resolve()

    # Prefer Zendesk API for reliability (avoids 403 on HTML pages)
    api_articles = fetch_articles_via_api(args.locale, args.max_articles)
    if not api_articles:
        print("Warning: API returned no articles; falling back to HTML crawl (may be blocked).")
        refs = crawl_article_urls(args.start_url, args.max_articles)
        if len(refs) < 30:
            print(f"Warning: Discovered only {len(refs)} article URLs; proceeding anyway.")
        # Create a stable map for rewriting links later
        url_to_filename: Dict[str, str] = {}
        for r in refs:
            url_to_filename[r.url.rstrip('/')] = r.filename
        saved = 0
        for ref in refs:
            html = fetch(ref.url)
            if not html:
                continue
            title = extract_title(html)
            md = extract_markdown(ref.url)
            if not md:
                continue
            md = rewrite_internal_links(md, url_to_filename)
            save_markdown(args.out_dir, ref, title, md)
            saved += 1
        print(f"Saved {saved} Markdown articles to {args.out_dir}")
        if saved < 30:
            sys.exit(1)
        return

    # When API works: build filename map first for link rewriting
    refs: List[ArticleRef] = []
    for art in api_articles:
        aid = str(art.get("id"))
        title = art.get("title") or ""
        slug = slugify(title) or art.get("name", "") or "article"
        url = art.get("html_url") or ""
        refs.append(ArticleRef(url=url, article_id=aid, slug=slug))

    url_to_filename: Dict[str, str] = {r.url.rstrip('/'): r.filename for r in refs if r.url}

    saved = 0
    for art, ref in zip(api_articles, refs):
        md, source_url = convert_api_article_to_markdown(art)
        md = rewrite_internal_links(md, url_to_filename)
        header = f"Article URL: {source_url}\n\n"
        out = header + md
        args.out_dir.mkdir(parents=True, exist_ok=True)
        target = args.out_dir / ref.filename
        target.write_text(out, encoding="utf-8")
        saved += 1

    print(f"Saved {saved} Markdown articles to {args.out_dir}")
    # Only exit with error if we got significantly fewer articles than requested
    if saved < min(30, args.max_articles):
        sys.exit(1)


if __name__ == "__main__":
    main()


