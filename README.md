# 🕷️ Web Scraper für LLM-Kontext

Ein Python-basierter Web Scraper/Crawler, der Webseiten-Inhalte extrahiert und als sauberes Markdown speichert – perfekt als Kontext für LLM-Chats.

## Features

- **Auto-Detection**: Erkennt automatisch, ob JavaScript-Rendering benötigt wird
- **Schneller Modus**: Nutzt `httpx` für statische Seiten
- **Browser-Fallback**: Verwendet Playwright für JS-gerenderte Seiten (React, Vue, etc.)
- **Rekursives Crawling**: Kann alle verlinkten Unterseiten einer Domain crawlen
- **LLM-optimiertes Markdown**: Sauberer Output mit Metadaten und Inhaltsverzeichnis

---

## Installation

### Voraussetzungen

- Python 3.10+

### Setup

```bash
# Repository klonen
git clone <repo-url>
cd scraper

# Virtuelle Umgebung erstellen und aktivieren
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# oder: venv\Scripts\activate  # Windows

# Dependencies installieren
pip install -r requirements.txt

# Playwright Browser installieren
playwright install chromium
```

---

## Nutzung

### Virtuelle Umgebung aktivieren

```bash
cd /path/to/scraper
source venv/bin/activate
```

### Einzelne Seite scrapen

```bash
python scraper.py https://example.com
```

### Ganze Website crawlen

```bash
python scraper.py https://example.com --crawl
```

---

## Optionen

| Option | Kurz | Beschreibung |
|--------|------|--------------|
| `--crawl` | `-c` | Rekursives Crawling aller verlinkten Unterseiten |
| `--max N` | `-m N` | Maximale Anzahl Seiten beim Crawlen (Standard: 50) |
| `--depth N` | `-d N` | Maximale Crawl-Tiefe (1 = nur direkte Links, 2 = zwei Ebenen, etc.) |
| `--separate` | `-s` | Jede Seite als separate Datei in eigenem Ordner speichern |
| `--output FILE` | `-o FILE` | Ausgabedatei festlegen |
| `--force-browser` | `-b` | Browser-Rendering erzwingen (für JS-lastige Seiten) |
| `--verbose` | `-v` | Ausführliche Ausgabe |

---

## Beispiele

```bash
# Einfach: Nur Startseite
python scraper.py https://docs.python.org

# Crawlen mit max 20 Seiten und ausführlicher Ausgabe
python scraper.py https://example.com --crawl --max 20 -v

# Nur 1 Ebene tief crawlen (Startseite + direkte Links)
python scraper.py https://example.com --crawl --depth 1

# Maximal 2 Ebenen tief
python scraper.py https://example.com --crawl --depth 2 --max 50

# Separate Dateien pro Seite (statt einer großen Datei)
python scraper.py https://example.com --crawl --separate

# Browser erzwingen für React/Vue Apps
python scraper.py https://spa-website.com --crawl --force-browser

# Eigenen Dateinamen festlegen
python scraper.py https://example.com -c -o meine_doku.md

# Kompakt: Alle Optionen kombiniert
python scraper.py https://example.com -c -m 100 -d 2 -b -v -o output.md
```

---

## Output-Format

### Einzelne Seite

```markdown
---
url: https://example.com
scraped_at: 2026-01-08 14:00
title: Example Domain
---

# Example Domain

## Inhalt

[Extrahierter Text...]

## Interne Links

- [Link Text](https://example.com/page)
```

### Gecrawlte Website

```markdown
---
source: example.com
start_url: https://example.com
scraped_at: 2026-01-08 14:00
pages_crawled: 15
---

# 🌐 example.com

## 📑 Inhaltsverzeichnis

1. [Startseite](#startseite)
2. [Über uns](#über-uns)
...

---

## 📄 Startseite
**URL:** https://example.com

[Inhalt...]

---

## 📄 Über uns
**URL:** https://example.com/about

[Inhalt...]
```

---

## Projektstruktur

```
scraper/
├── venv/              # Virtuelle Umgebung (nicht in Git)
├── scraper_results/   # Ausgabe-Ordner für Markdown-Dateien
│   ├── example_com_2026-01-08_14-00-24.md
│   └── example_com_crawl_2026-01-08_14-00-37.md
├── scraper.py         # Haupt-Skript
├── requirements.txt   # Python Dependencies
├── .gitignore
└── README.md
```

---

## Lizenz

MIT

