#!/usr/bin/env python3
"""
Interaktives Startscript für den Web Scraper
Fragt alle Optionen ab und startet dann den Scraper.
"""

import subprocess
import sys


def ask(prompt: str, default: str = "") -> str:
    """Fragt den Benutzer nach Eingabe mit optionalem Default."""
    if default:
        result = input(f"{prompt} [{default}]: ").strip()
        return result if result else default
    else:
        return input(f"{prompt}: ").strip()


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    """Fragt Ja/Nein Frage."""
    default_str = "J/n" if default else "j/N"
    result = input(f"{prompt} ({default_str}): ").strip().lower()
    if not result:
        return default
    return result in ("j", "ja", "y", "yes", "1", "true")


def ask_number(prompt: str, default: int) -> int:
    """Fragt nach einer Zahl."""
    result = input(f"{prompt} [{default}]: ").strip()
    if not result:
        return default
    try:
        return int(result)
    except ValueError:
        print(f"  ⚠️  Ungültige Zahl, verwende {default}")
        return default


def main():
    print()
    print("=" * 60)
    print("🕷️  Web Scraper für LLM-Kontext - Interaktiver Modus")
    print("=" * 60)
    print()
    
    # 1. URL abfragen
    url = ""
    while not url:
        url = ask("📌 URL zum Scrapen")
        if not url:
            print("  ❌ URL ist erforderlich!")
    
    # URL normalisieren
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    print()
    
    # 2. Modus: Einzelseite oder Crawl?
    print("📋 Modus auswählen:")
    print("   1) Nur diese eine Seite scrapen")
    print("   2) Website crawlen (mehrere Seiten)")
    mode = ask("   Auswahl", "1")
    crawl = mode == "2"
    
    # Optionen sammeln
    args = [sys.executable, "scraper.py", url]
    
    if crawl:
        args.append("--crawl")
        print()
        
        # 3. Crawl-Optionen
        max_pages = ask_number("📊 Maximale Anzahl Seiten", 50)
        args.extend(["--max", str(max_pages)])
        
        # Tiefe
        use_depth = ask_yes_no("🔽 Crawl-Tiefe begrenzen?", False)
        if use_depth:
            depth = ask_number("   Maximale Tiefe (1 = nur direkte Links)", 1)
            args.extend(["--depth", str(depth)])
        
        # Prefix
        use_prefix = ask_yes_no("📁 Nur bestimmten Pfad crawlen (z.B. /docs/)?", False)
        if use_prefix:
            prefix = ask("   Pfad-Prefix (z.B. /docs/api/)")
            if prefix:
                args.extend(["--prefix", prefix])
        
        print()
        
        # 4. Output-Format
        print("💾 Ausgabe-Format:")
        print("   1) Eine kombinierte Markdown-Datei")
        print("   2) Separate Dateien in einem Ordner")
        output_mode = ask("   Auswahl", "1")
        if output_mode == "2":
            args.append("--separate")
    
    print()
    
    # 5. Erweiterte Optionen
    print("⚙️  Erweiterte Optionen:")
    
    expand_tabs = ask_yes_no("   Tab-Inhalte durch Klicken erfassen?", False)
    if expand_tabs:
        args.append("--expand-tabs")
    
    force_browser = ask_yes_no("   Browser-Rendering erzwingen?", False)
    if force_browser:
        args.append("--force-browser")
    
    verbose = ask_yes_no("   Ausführliche Ausgabe (Details pro Seite)?", True)
    if verbose:
        args.append("--verbose")
    
    # 6. Zusammenfassung und Start
    print()
    print("=" * 60)
    print("🚀 Starte Scraper mit folgenden Einstellungen:")
    print("=" * 60)
    print(f"   URL: {url}")
    print(f"   Modus: {'Crawl' if crawl else 'Einzelseite'}")
    if crawl:
        print(f"   Max Seiten: {max_pages}")
        if use_depth:
            print(f"   Tiefe: {depth}")
        if use_prefix and prefix:
            print(f"   Prefix: {prefix}")
        print(f"   Format: {'Separate Dateien' if output_mode == '2' else 'Kombinierte Datei'}")
    if expand_tabs:
        print("   Tab-Expansion: Ja")
    if force_browser:
        print("   Browser erzwungen: Ja")
    print(f"   Verbose: {'Ja' if verbose else 'Nein'}")
    print()
    
    # Befehl anzeigen
    cmd_display = " ".join(args).replace(sys.executable, "python")
    print(f"📝 Befehl: {cmd_display}")
    print()
    
    # Bestätigung
    start = ask_yes_no("▶️  Jetzt starten?", True)
    if not start:
        print("❌ Abgebrochen.")
        sys.exit(0)
    
    print()
    print("-" * 60)
    print()
    
    # Scraper starten
    result = subprocess.run(args)
    
    print()
    print("-" * 60)
    if result.returncode == 0:
        print("✅ Scraping erfolgreich abgeschlossen!")
    else:
        print(f"❌ Scraping mit Fehlercode {result.returncode} beendet")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Abgebrochen durch Benutzer")
        sys.exit(130)

