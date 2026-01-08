#!/usr/bin/env python3
"""
Web Scraper/Crawler für LLM-Kontext
Extrahiert Text und interne Links aus Webseiten und speichert sie als Markdown.
Kann rekursiv alle verlinkten Unterseiten crawlen.
Erkennt automatisch, ob JavaScript-Rendering benötigt wird.
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Comment

# Playwright wird nur bei Bedarf importiert (lazy loading)
_playwright = None
_browser = None


def get_browser():
    """Lazy-load Playwright Browser nur wenn benötigt."""
    global _playwright, _browser
    if _browser is None:
        from playwright.sync_api import sync_playwright
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(headless=True)
    return _browser


def close_browser():
    """Browser und Playwright sauber schließen."""
    global _playwright, _browser
    if _browser:
        _browser.close()
        _browser = None
    if _playwright:
        _playwright.stop()
        _playwright = None


# Realistische Browser-Header (Chrome 120 auf macOS)
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def fetch_with_httpx(url: str, referer: str = None, timeout: int = 10) -> tuple[str, int]:
    """Schneller Fetch mit httpx."""
    headers = DEFAULT_HEADERS.copy()
    if referer:
        headers["Referer"] = referer
        headers["Sec-Fetch-Site"] = "same-origin"
    
    response = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    return response.text, response.status_code


def fetch_with_browser(url: str, timeout: int = 30000, expand_tabs: bool = False) -> str:
    """Fetch mit echtem Browser für JS-gerenderte Seiten."""
    browser = get_browser()
    page = browser.new_page()
    try:
        # "domcontentloaded" ist schneller als "networkidle" und funktioniert bei den meisten Seiten
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        # Warte etwas länger, damit JS fertig rendern kann
        page.wait_for_timeout(2000)
        
        if expand_tabs:
            # Sammle Content von allen Tabs
            content = expand_all_tabs(page)
        else:
            content = page.content()
    finally:
        page.close()
    return content


def expand_all_tabs(page) -> str:
    """
    Klickt alle Tab-Elemente durch und sammelt den gesamten Content.
    Gibt das kombinierte HTML zurück.
    """
    # Sammle initialen Content
    all_contents = [page.content()]
    
    # Finde alle Tab-Elemente mit verschiedenen Selektoren
    tab_selectors = [
        '[role="tab"]',
        '[data-tab]',
        '.tab-button',
        '.tabs button',
        '[class*="tab"][class*="button"]',
        'button[class*="tab"]',
    ]
    
    clicked_tabs = set()
    
    for selector in tab_selectors:
        try:
            tabs = page.query_selector_all(selector)
            for tab in tabs:
                try:
                    # Überspringe bereits geklickte Tabs
                    tab_text = tab.inner_text()
                    if tab_text in clicked_tabs:
                        continue
                    clicked_tabs.add(tab_text)
                    
                    # Klicke auf den Tab
                    tab.click()
                    page.wait_for_timeout(500)  # Kurz warten für Content-Laden
                    
                    # Sammle neuen Content
                    new_content = page.content()
                    if new_content not in all_contents:
                        all_contents.append(new_content)
                        
                except Exception:
                    continue  # Tab konnte nicht geklickt werden
        except Exception:
            continue  # Selector nicht gefunden
    
    # Kombiniere alle HTML-Inhalte
    # Extrahiere nur die Body-Inhalte und füge sie zusammen
    from bs4 import BeautifulSoup
    combined_soup = BeautifulSoup(all_contents[0], "lxml")
    
    for html_content in all_contents[1:]:
        soup = BeautifulSoup(html_content, "lxml")
        # Finde neue pre/code Blöcke die im Original nicht vorhanden sind
        for pre in soup.find_all("pre"):
            pre_text = pre.get_text()
            # Prüfe ob dieser Code-Block bereits existiert
            existing = combined_soup.find("pre", string=lambda t: t and pre_text[:50] in t if t else False)
            if not existing and pre_text.strip():
                # Füge neuen Code-Block zum Body hinzu
                body = combined_soup.find("body")
                if body:
                    # Erstelle einen Container für den neuen Code
                    new_div = combined_soup.new_tag("div")
                    new_div["class"] = "expanded-tab-content"
                    new_pre = combined_soup.new_tag("pre")
                    new_code = combined_soup.new_tag("code")
                    new_code.string = pre_text
                    new_pre.append(new_code)
                    new_div.append(new_pre)
                    body.append(new_div)
    
    return str(combined_soup)


def is_js_rendered(html: str, soup: BeautifulSoup) -> bool:
    """
    Heuristik: Ist die Seite wahrscheinlich JS-gerendert?
    """
    body = soup.find("body")
    if not body:
        return False
    
    # Text im Body extrahieren (ohne Scripts)
    for script in body.find_all(["script", "style"]):
        script.decompose()
    
    text = body.get_text(strip=True)
    text_length = len(text)
    
    # Zähle Script-Tags im Original-HTML
    script_count = html.lower().count("<script")
    
    # Typische SPA-Container
    spa_indicators = [
        soup.find(id="app"),
        soup.find(id="root"),
        soup.find(id="__next"),  # Next.js
        soup.find(id="__nuxt"),  # Nuxt.js
    ]
    has_spa_container = any(spa_indicators)
    
    if text_length < 500 and script_count > 5:
        return True
    if text_length < 200 and has_spa_container:
        return True
    
    return False


def extract_text(soup: BeautifulSoup) -> str:
    """Extrahiert sauberen Text aus HTML."""
    soup = BeautifulSoup(str(soup), "lxml")
    
    # Entferne unerwünschte Elemente
    for element in soup.find_all([
        "script", "style", "nav", "footer", "header", 
        "aside", "noscript", "iframe", "svg"
    ]):
        element.decompose()
    
    # Entferne Kommentare
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    
    # Versuche Hauptinhalt zu finden
    main_content = (
        soup.find("main") or 
        soup.find("article") or 
        soup.find(id="content") or
        soup.find(class_="content") or
        soup.find("body")
    )
    
    if not main_content:
        main_content = soup
    
    lines = []
    seen_elements = set()  # Vermeidet doppelte Verarbeitung
    
    for element in main_content.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th", "blockquote", "pre", "code"]):
        # Überspringe bereits verarbeitete Elemente (z.B. code innerhalb von pre)
        if id(element) in seen_elements:
            continue
        
        # Code-Blöcke (<pre> oder <pre><code>)
        if element.name == "pre":
            seen_elements.add(id(element))
            # Auch innere code-Elemente markieren
            for code in element.find_all("code"):
                seen_elements.add(id(code))
            
            code_text = element.get_text()
            if code_text.strip():
                # Versuche Sprache aus class zu erkennen
                lang = ""
                code_elem = element.find("code")
                if code_elem and code_elem.get("class"):
                    classes = code_elem.get("class", [])
                    for cls in classes:
                        if cls.startswith("language-"):
                            lang = cls.replace("language-", "")
                            break
                lines.append(f"\n```{lang}\n{code_text.strip()}\n```\n")
            continue
        
        # Inline-Code (nur wenn nicht in <pre>)
        if element.name == "code":
            if element.parent and element.parent.name == "pre":
                continue  # Überspringe, wird von pre behandelt
            text = element.get_text(strip=True)
            if text:
                lines.append(f"`{text}`")
            continue
        
        text = element.get_text(strip=True)
        if not text:
            continue
            
        if element.name.startswith("h") and len(element.name) == 2:
            level = int(element.name[1])
            lines.append(f"\n{'#' * level} {text}\n")
        elif element.name == "li":
            lines.append(f"- {text}")
        elif element.name == "blockquote":
            lines.append(f"> {text}")
        else:
            lines.append(text)
    
    if not lines:
        text = main_content.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text
    
    return "\n".join(lines)


def extract_internal_links(soup: BeautifulSoup, base_url: str, path_prefix: str = None) -> list[dict]:
    """Extrahiert alle internen Links (gleiche Domain, optional nur bestimmter Pfad)."""
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc
    
    links = []
    seen_urls = set()
    
    # Dateierweiterungen, die wir überspringen wollen
    skip_extensions = {'.pdf', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', 
                       '.mp3', '.mp4', '.avi', '.mov', '.zip', '.rar', '.exe', 
                       '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'}
    
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        
        # Relative URLs auflösen
        full_url = urljoin(base_url, href)
        parsed_url = urlparse(full_url)
        
        # Nur HTTP(S) Links
        if parsed_url.scheme not in ("http", "https"):
            continue
        
        # Nur gleiche Domain
        if parsed_url.netloc != base_domain:
            continue
        
        # Pfad-Prefix prüfen (falls angegeben)
        if path_prefix and not parsed_url.path.startswith(path_prefix):
            continue
        
        # Anker-Links ignorieren
        clean_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
        if parsed_url.query:
            clean_url += f"?{parsed_url.query}"
        
        # Dateien überspringen
        path_lower = parsed_url.path.lower()
        if any(path_lower.endswith(ext) for ext in skip_extensions):
            continue
        
        # Duplikate vermeiden
        if clean_url in seen_urls:
            continue
        seen_urls.add(clean_url)
        
        link_text = a_tag.get_text(strip=True) or parsed_url.path
        
        links.append({
            "url": clean_url,
            "text": link_text
        })
    
    return links


def get_page_title(soup: BeautifulSoup) -> str:
    """Extrahiert den Seitentitel."""
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        return title_tag.string.strip()
    
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        return og_title["content"]
    
    return "Unbekannter Titel"


def generate_page_markdown(url: str, title: str, content: str) -> str:
    """Generiert Markdown für eine einzelne Seite (für kombinierte Datei)."""
    lines = [
        f"## 📄 {title}",
        f"**URL:** {url}",
        "",
        content,
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def generate_single_file_markdown(url: str, title: str, content: str, links: list[dict] = None) -> str:
    """Generiert vollständiges Markdown für eine einzelne Seite (separate Datei)."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    lines = [
        "---",
        f"url: {url}",
        f"scraped_at: {now}",
        f"title: {title}",
        "---",
        "",
        f"# {title}",
        "",
        content,
        "",
    ]
    
    if links:
        lines.extend(["## Interne Links", ""])
        for link in links:
            lines.append(f"- [{link['text']}]({link['url']})")
    
    return "\n".join(lines)


def page_url_to_filename(url: str) -> str:
    """Generiert einen sauberen Dateinamen aus einer Seiten-URL."""
    parsed = urlparse(url)
    # Pfad verwenden, oder 'index' für Startseite
    path = parsed.path.strip('/') or 'index'
    name = re.sub(r"[^\w\-]", "_", path)
    name = re.sub(r"_+", "_", name)
    name = name.strip("_") or "index"
    return f"{name}.md"


def generate_combined_markdown(base_url: str, pages: list[dict], all_links: list[dict]) -> str:
    """Generiert kombiniertes Markdown für alle gecrawlten Seiten."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    parsed = urlparse(base_url)
    domain = parsed.netloc
    
    md_lines = [
        "---",
        f"source: {domain}",
        f"start_url: {base_url}",
        f"scraped_at: {now}",
        f"pages_crawled: {len(pages)}",
        "---",
        "",
        f"# 🌐 {domain}",
        "",
        f"*Gecrawlt am {now} - {len(pages)} Seiten*",
        "",
        "---",
        "",
    ]
    
    # Inhaltsverzeichnis
    md_lines.append("## 📑 Inhaltsverzeichnis\n")
    for i, page in enumerate(pages, 1):
        # Anker-freundlicher Titel
        anchor = re.sub(r'[^\w\s-]', '', page['title'].lower())
        anchor = re.sub(r'[\s]+', '-', anchor)
        md_lines.append(f"{i}. [{page['title']}](#{anchor})")
    md_lines.append("\n---\n")
    
    # Alle Seiteninhalte
    for page in pages:
        md_lines.append(generate_page_markdown(page['url'], page['title'], page['content']))
    
    return "\n".join(md_lines)


# Ausgabe-Ordner
OUTPUT_DIR = Path("scraper_results")


def url_to_filename(url: str, suffix: str = "") -> Path:
    """Generiert einen sauberen Dateinamen aus der URL mit Zeitstempel."""
    parsed = urlparse(url)
    name = parsed.netloc + parsed.path
    name = re.sub(r"[^\w\-]", "_", name)
    name = re.sub(r"_+", "_", name)
    name = name.strip("_")
    
    # Zeitstempel hinzufügen
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    if suffix:
        filename = f"{name}_{suffix}_{timestamp}.md"
    else:
        filename = f"{name}_{timestamp}.md"
    
    return OUTPUT_DIR / filename


def normalize_url(url: str) -> str:
    """Normalisiert URL für Duplikat-Erkennung."""
    parsed = urlparse(url)
    # Trailing Slash entfernen
    path = parsed.path.rstrip('/')
    normalized = f"{parsed.scheme}://{parsed.netloc}{path}"
    if parsed.query:
        normalized += f"?{parsed.query}"
    return normalized


def scrape_page(url: str, referer: str = None, path_prefix: str = None, force_browser: bool = False, expand_tabs: bool = False, verbose: bool = False) -> tuple[str, str, list[dict], bool]:
    """
    Scraped eine einzelne Seite.
    Gibt zurück: (title, content, links, success)
    """
    try:
        # Bei expand_tabs immer Browser verwenden
        if expand_tabs:
            if verbose:
                print(f"  🔄 Tab-Expansion aktiv, nutze Browser...")
            html = fetch_with_browser(url, expand_tabs=True)
            soup = BeautifulSoup(html, "lxml")
        elif not force_browser:
            try:
                html, status = fetch_with_httpx(url, referer=referer)
                if status != 200:
                    raise Exception(f"HTTP {status}")
                
                soup = BeautifulSoup(html, "lxml")
                
                if is_js_rendered(html, BeautifulSoup(html, "lxml")):
                    if verbose:
                        print(f"  🔄 JS erkannt, nutze Browser...")
                    html = fetch_with_browser(url)
                    soup = BeautifulSoup(html, "lxml")
                    
            except Exception as e:
                if verbose:
                    print(f"  ⚠️ Fallback zu Browser: {e}")
                html = fetch_with_browser(url)
                soup = BeautifulSoup(html, "lxml")
        else:
            html = fetch_with_browser(url)
            soup = BeautifulSoup(html, "lxml")
        
        title = get_page_title(soup)
        content = extract_text(soup)
        links = extract_internal_links(soup, url, path_prefix=path_prefix)
        
        return title, content, links, True
        
    except Exception as e:
        if verbose:
            print(f"  ❌ Fehler: {e}")
        return "", "", [], False


def crawl(start_url: str, max_pages: int = 50, max_depth: int = None, path_prefix: str = None, force_browser: bool = False, expand_tabs: bool = False, verbose: bool = False) -> tuple[list[dict], list[dict]]:
    """
    Crawlt eine Website rekursiv.
    
    Args:
        start_url: Start-URL
        max_pages: Maximale Anzahl zu crawlender Seiten
        max_depth: Maximale Tiefe (None = unbegrenzt, 1 = nur Startseite + direkte Links, etc.)
        path_prefix: Nur Links mit diesem Pfad-Prefix folgen (z.B. '/docs/')
        force_browser: Browser-Rendering erzwingen
        expand_tabs: Alle Tab-Inhalte durch Klicken erfassen
        verbose: Ausführliche Ausgabe
    
    Returns:
        (pages, all_links) - Liste der gecrawlten Seiten und aller gefundenen Links
    """
    visited = set()
    # Queue enthält Tupel: (url, depth, referer)
    to_visit = [(normalize_url(start_url), 0, None)]
    pages = []
    all_links = []
    
    parsed_start = urlparse(start_url)
    base_domain = parsed_start.netloc
    
    while to_visit and len(pages) < max_pages:
        url, depth, referer = to_visit.pop(0)
        
        # Bereits besucht?
        if url in visited:
            continue
        
        # Domain-Check (für den Fall dass ein Link durch normalization durchgerutscht ist)
        if urlparse(url).netloc != base_domain:
            continue
        
        # Pfad-Prefix prüfen
        if path_prefix and not urlparse(url).path.startswith(path_prefix):
            continue
            
        visited.add(url)
        
        depth_info = f" (Level {depth})" if max_depth is not None else ""
        if verbose:
            print(f"[{len(pages) + 1}/{max_pages}] 📡 {url}{depth_info}")
        
        title, content, links, success = scrape_page(url, referer=referer, path_prefix=path_prefix, force_browser=force_browser, expand_tabs=expand_tabs, verbose=verbose)
        
        if success and content.strip():
            pages.append({
                'url': url,
                'title': title,
                'content': content
            })
            
            # Neue Links zur Queue hinzufügen (nur wenn Tiefe erlaubt)
            if max_depth is None or depth < max_depth:
                for link in links:
                    normalized = normalize_url(link['url'])
                    if normalized not in visited and normalized not in [u for u, d, r in to_visit]:
                        # Aktuelle URL als Referer für den neuen Link
                        to_visit.append((normalized, depth + 1, url))
                        all_links.append(link)
            
            if verbose:
                print(f"  ✅ {len(content)} Zeichen, {len(links)} Links")
        elif verbose:
            print(f"  ⏭️  Übersprungen (kein Inhalt)")
    
    if verbose:
        print(f"\n📊 Fertig: {len(pages)} Seiten gecrawlt")
    
    return pages, all_links


def main():
    parser = argparse.ArgumentParser(
        description="Web Scraper/Crawler für LLM-Kontext - Extrahiert Text als Markdown",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python3 scraper.py https://example.com                    # Nur Startseite
  python3 scraper.py https://example.com --crawl            # Alle verlinkten Seiten
  python3 scraper.py https://example.com --crawl --max 20   # Max 20 Seiten
  python3 scraper.py https://example.com -c -m 100 -b -v    # Kompakt mit allen Optionen
        """
    )
    parser.add_argument(
        "url",
        help="Die zu scrapende Start-URL"
    )
    parser.add_argument(
        "-o", "--output",
        help="Ausgabedatei (Standard: generiert aus URL)"
    )
    parser.add_argument(
        "-c", "--crawl",
        action="store_true",
        help="Auch alle verlinkten Unterseiten crawlen"
    )
    parser.add_argument(
        "-m", "--max",
        type=int,
        default=50,
        help="Maximale Anzahl Seiten beim Crawlen (Standard: 50)"
    )
    parser.add_argument(
        "-d", "--depth",
        type=int,
        default=None,
        help="Maximale Crawl-Tiefe (1 = nur direkte Links, 2 = zwei Ebenen, etc.)"
    )
    parser.add_argument(
        "-s", "--separate",
        action="store_true",
        help="Jede Seite als separate Datei in eigenem Ordner speichern"
    )
    parser.add_argument(
        "-p", "--prefix",
        type=str,
        default=None,
        help="Nur Links mit diesem Pfad-Prefix folgen (z.B. '/docs/api/')"
    )
    parser.add_argument(
        "-t", "--expand-tabs",
        action="store_true",
        help="Alle Tab-Inhalte durch Klicken erfassen (langsamer, aber vollständiger)"
    )
    parser.add_argument(
        "-b", "--force-browser",
        action="store_true",
        help="Browser-Rendering erzwingen (für JS-lastige Seiten)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Ausführliche Ausgabe"
    )
    
    args = parser.parse_args()
    
    # URL validieren
    if not args.url.startswith(("http://", "https://")):
        args.url = "https://" + args.url
    
    try:
        if args.crawl:
            # Rekursives Crawling
            depth_info = f", Tiefe {args.depth}" if args.depth else ""
            prefix_info = f", Prefix '{args.prefix}'" if args.prefix else ""
            tabs_info = ", Tab-Expansion" if args.expand_tabs else ""
            print(f"🕷️  Starte Crawling von {args.url} (max {args.max} Seiten{depth_info}{prefix_info}{tabs_info})...\n")
            
            pages, all_links = crawl(
                args.url,
                max_pages=args.max,
                max_depth=args.depth,
                path_prefix=args.prefix,
                force_browser=args.force_browser,
                expand_tabs=args.expand_tabs,
                verbose=args.verbose
            )
            
            if not pages:
                print("❌ Keine Seiten gefunden!")
                sys.exit(1)
            
            if args.separate:
                # Separate Dateien in eigenem Ordner
                parsed = urlparse(args.url)
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                folder_name = f"{parsed.netloc.replace('.', '_')}_{timestamp}"
                output_dir = OUTPUT_DIR / folder_name
                output_dir.mkdir(parents=True, exist_ok=True)
                
                for page in pages:
                    page_markdown = generate_single_file_markdown(
                        page['url'], 
                        page['title'], 
                        page['content']
                    )
                    page_filename = page_url_to_filename(page['url'])
                    page_path = output_dir / page_filename
                    page_path.write_text(page_markdown, encoding="utf-8")
                
                print(f"\n✅ Gespeichert: {output_dir}/")
                print(f"📊 {len(pages)} Dateien erstellt")
                return
            
            # Kombiniertes Markdown generieren
            markdown = generate_combined_markdown(args.url, pages, all_links)
            
            # Dateiname mit Zeitstempel
            output_path = args.output or url_to_filename(args.url, suffix="crawl")
            
        else:
            # Nur einzelne Seite
            if args.verbose:
                tabs_info = " (mit Tab-Expansion)" if args.expand_tabs else ""
                print(f"📡 Lade: {args.url}{tabs_info}")
            
            title, content, links, success = scrape_page(
                args.url,
                force_browser=args.force_browser,
                expand_tabs=args.expand_tabs,
                verbose=args.verbose
            )
            
            if not success:
                print("❌ Seite konnte nicht geladen werden!")
                sys.exit(1)
            
            if args.verbose:
                print(f"📝 Titel: {title}")
                print(f"📄 {len(content)} Zeichen extrahiert")
                print(f"🔗 {len(links)} interne Links gefunden")
            
            # Einfaches Markdown für einzelne Seite
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            md_lines = [
                "---",
                f"url: {args.url}",
                f"scraped_at: {now}",
                f"title: {title}",
                "---",
                "",
                f"# {title}",
                "",
                "## Inhalt",
                "",
                content,
                "",
            ]
            if links:
                md_lines.extend(["## Interne Links", ""])
                for link in links:
                    md_lines.append(f"- [{link['text']}]({link['url']})")
            
            markdown = "\n".join(md_lines)
            output_path = args.output or url_to_filename(args.url)
        
        # Ausgabe-Ordner erstellen falls nicht vorhanden
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Speichern
        output_path.write_text(markdown, encoding="utf-8")
        
        print(f"\n✅ Gespeichert: {output_path}")
        
        # Statistik bei Crawl
        if args.crawl:
            file_size = Path(output_path).stat().st_size
            print(f"📊 {len(pages)} Seiten, {file_size / 1024:.1f} KB")
        
    except KeyboardInterrupt:
        print("\n⚠️ Abgebrochen durch Benutzer")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Fehler: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        close_browser()


if __name__ == "__main__":
    main()
