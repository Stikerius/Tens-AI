import re
import requests
import chromadb
import json
import os
import pathlib
from datetime import datetime
from scraper import lese_webseite, suche_und_lerne

# ── Hacking-Ressourcen ────────────────────────────────────────────────────────
HACKING_RESOURCES = [
    {"name": "TryHackMe",                    "link": "https://tryhackme.com/"},
    {"name": "Hack The Box Academy",          "link": "https://academy.hackthebox.com/"},
    {"name": "PortSwigger Web Security Academy", "link": "https://portswigger.net/web-security"},
    {"name": "OverTheWire Wargames",          "link": "https://overthewire.org/wargames/"},
    {"name": "Kali Linux Docs",               "link": "https://www.kali.org/docs/"},
    {"name": "OWASP Top 10",                  "link": "https://owasp.org/www-project-top-ten/"},
]

# ── ChromaDB ──────────────────────────────────────────────────────────────────
client     = chromadb.PersistentClient(path="./tens_memory")
gespraeche = client.get_or_create_collection("gespraeche")

# ── Topic keywords for fast collection routing ────────────────────────────────
TOPIC_KEYWORDS = {
    "wissen_python":      ["python", "pip", "pandas", "numpy", "pytorch", "tensorflow", "flask", "django", "fastapi", "jupyter"],
    "wissen_javascript":  ["javascript", " js ", "node.js", "nodejs", "react", "vue", "angular", "typescript", "npm", "webpack"],
    "wissen_html":        ["html", " css ", "stylesheet", "dom ", "webpage", "browser", "frontend", "responsive", "tailwind"],
    "wissen_mathematik":  ["mathematik", "mathe", "algebra", "calculus", "matrix", "gleichung", "integral", "ableitung", "statistik"],
    "wissen_physik":      ["physik", "quantenphysik", "quantum", "relativität", "thermodynamik", "elektromagnetismus", "mechanik"],
    "wissen_linux":       ["linux", "bash", "shell", "terminal", "ubuntu", "debian", "arch", "systemctl", "sudo", "chmod", "unix"],
    "wissen_docker":      ["docker", "container", "kubernetes", "k8s", "dockerfile", "image", "pod", "helm", "compose"],
    "wissen_git":         ["git ", "github", "gitlab", "commit", "branch", "merge", "pull request", "repository", "rebase"],
    "wissen_chemie":      ["chemie", "molekül", "atom", "reaktion", "verbindung", "element", "periodensystem", "säure", "base"],
    "wissen_biologie":    ["biologie", "zelle", "dna", "rna", "evolution", "genetik", "protein", "organ", "ökosystem"],
    "wissen_security":    ["hack", "exploit", "pentest", "ctf", "vulnerability", "xss", "sql injection", "metasploit", "nmap", "burp"],
    "wissen_ki":          ["machine learning", "deep learning", "neural", "llm", "transformer", "embedding", "rag", "whisper", "ollama"],
    "wissen_ernaehrung":  ["ernährung", "nahrung", "protein", "kalorien", "vitamine", "makronährstoffe", "kochen", "rezept", "meal prep", "diät"],
    "wissen_sport":       ["sport", "training", "fitness", "muskel", "ausdauer", "krafttraining", "laufen", "yoga", "gym", "hypertrophie"],
    "wissen_finanzen":    ["finanzen", "budget", "aktie", "etf", "investieren", "steuern", "sparplan", "zinseszins", "börse", "vorsorge"],
    "wissen_psychologie": ["psychologie", "stress", "motivation", "habit", "verhalten", "emotion", "burnout", "bias", "kognition", "resilienz"],
    "wissen_philosophie": ["philosophie", "ethik", "logik", "stoizismus", "erkenntnistheorie", "moral", "ontologie", "existenzialismus"],
    "wissen_geschichte":  ["geschichte", "historisch", "revolution", "weltkrieg", "mittelalter", "antike", "kolonialismus", "eidgenossenschaft"],
    "wissen_recht":       ["recht", "gesetz", "datenschutz", "dsgvo", "kündigung", "mietrecht", "vertrag", "strafrecht", "urheberrecht"],
    "wissen_musik":       ["musik", "akkord", "melodie", "gitarre", "klavier", "daw", "produzieren", "mixing", "mastering", "musiktheorie"],
    "wissen_reisen":      ["reisen", "backpack", "visum", "hotel", "flug", "tourismus", "urlaub", "packen", "reiseplanung"],
}

# ── File handling constants ───────────────────────────────────────────────────
PROFIL_FILE = "nutzer_profil.json"
FILES_DIR   = "./tens_files"
FILES_INDEX = "./files_index.json"

_TEXT_EXTS = {
    ".txt", ".py", ".js", ".ts", ".html", ".css", ".md", ".sh",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".rs", ".go",
    ".java", ".c", ".cpp", ".h", ".xml", ".sql",
}


# ── Profile helpers ───────────────────────────────────────────────────────────

def lade_profil() -> dict:
    if os.path.exists(PROFIL_FILE):
        with open(PROFIL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def speichere_profil(profil: dict):
    with open(PROFIL_FILE, "w", encoding="utf-8") as f:
        json.dump(profil, f, indent=2, ensure_ascii=False)


def speichere_gespraech(user_msg: str, tens_msg: str):
    ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
    gespraeche.add(
        documents=[f"Nutzer: {user_msg}\nTENS: {tens_msg}"],
        ids=[ts],
    )


# ── Files index ───────────────────────────────────────────────────────────────

def lade_files_index() -> list:
    if os.path.exists(FILES_INDEX):
        try:
            with open(FILES_INDEX, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def speichere_files_index(index: list):
    with open(FILES_INDEX, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


# ── File reading ──────────────────────────────────────────────────────────────

def _pdf_pypdf(p: pathlib.Path) -> str:
    from pypdf import PdfReader
    return "\n\n".join(page.extract_text() or "" for page in PdfReader(str(p)).pages)


def _pdf_pypdf2(p: pathlib.Path) -> str:
    import PyPDF2
    with open(p, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def lese_datei(pfad: str) -> tuple:
    """Return (content, error_msg). Supports txt/py/js/md/json/csv/pdf/docx."""
    pfad = pfad.strip().strip('"').strip("'")
    p = pathlib.Path(pfad)
    if not p.exists():
        return "", f"Datei nicht gefunden: {pfad}"
    ext = p.suffix.lower()

    if ext in _TEXT_EXTS:
        return p.read_text(encoding="utf-8", errors="ignore"), ""

    if ext == ".json":
        try:
            data = json.loads(p.read_bytes())
            return json.dumps(data, indent=2, ensure_ascii=False), ""
        except Exception:
            return p.read_text(encoding="utf-8", errors="ignore"), ""

    if ext == ".csv":
        try:
            import pandas as pd
            df = pd.read_csv(p)
            return f"CSV — {len(df)} Zeilen, Spalten: {list(df.columns)}\n\n{df.head(50).to_string()}", ""
        except ImportError:
            return p.read_text(encoding="utf-8", errors="ignore"), ""

    if ext == ".pdf":
        for fn in [_pdf_pypdf, _pdf_pypdf2]:
            try:
                c = fn(p)
                if c.strip():
                    return c, ""
            except Exception:
                pass
        return "", "PDF: 'pip install pypdf' installieren."

    if ext == ".docx":
        try:
            from docx import Document
            doc = Document(str(p))
            return "\n".join(para.text for para in doc.paragraphs if para.text.strip()), ""
        except ImportError:
            return "", "DOCX: 'pip install python-docx' installieren."

    try:
        return p.read_text(encoding="utf-8", errors="ignore"), ""
    except Exception as e:
        return "", f"Kann nicht gelesen werden: {e}"


def _bestimme_dateiname(beschreibung: str, inhalt: str) -> str:
    m = re.search(r'\b([\w\-]+\.(?:py|js|ts|html|css|md|txt|json|sh|yaml|yml))\b', beschreibung, re.I)
    if m:
        return m.group(1).lower()
    if re.search(r'\bdef \w+\(|^import \w+', inhalt, re.M):
        ext = ".py"
    elif re.search(r'\bfunction\b|\bconst \w+ =|\blet \w+ =', inhalt):
        ext = ".js"
    elif re.search(r'<html|<!doctype', inhalt, re.I):
        ext = ".html"
    elif inhalt.strip().startswith(("{", "[")):
        ext = ".json"
    else:
        ext = ".txt"
    words = re.sub(r'[^a-z0-9 ]', '', beschreibung.lower()).split()[:3]
    name = "_".join(w for w in words if w) or "tens_output"
    return f"{name}{ext}"


# ── Topic classifier ──────────────────────────────────────────────────────────

def _ollama(messages: list, timeout: int = 60) -> str:
    """Call Ollama /api/chat with automatic CPU fallback on CUDA errors."""
    last_err = "LLM nicht erreichbar."
    for opts in [{}, {"num_gpu": 0}]:
        try:
            resp = requests.post(
                "http://localhost:11434/api/chat",
                json={"model": "dolphin-mistral", "messages": messages, "stream": False, "options": opts},
                timeout=timeout,
            )
            data = resp.json()
            if "message" in data:
                return data["message"]["content"]
            if "response" in data:
                return data["response"]
            err = data.get("error", str(data))
            if "cuda" in err.lower() or "terminated" in err.lower():
                last_err = err
                continue
            return f"Ollama-Fehler: {err}"
        except Exception as e:
            last_err = str(e)
            continue
    return f"LLM-Fehler: {last_err}"


def _klassifiziere_llm(url: str, text: str) -> str:
    """Fallback: ask LLM for a category name."""
    try:
        cat = _ollama([{
            "role": "user",
            "content": (
                "In welche Kategorie fällt dieser Text? Antworte NUR mit einem "
                "einzigen deutschen Kleinbuchstaben-Wort ohne Leerzeichen "
                "(z.B.: ernaehrung, sport, musik, reisen, finanzen, recht, "
                "psychologie, philosophie, geschichte, kochen, gesundheit).\n\n"
                f"URL: {url}\nText: {text[:400]}"
            ),
        }], timeout=15).strip().lower()
        cat = re.sub(r'[^a-z0-9]', '', cat)[:20]
        if len(cat) > 2:
            return f"wissen_{cat}"
    except Exception:
        pass
    return "wissen_allgemein"


def klassifiziere_thema(url: str, text: str) -> str:
    combined = (url + " " + text[:2000]).lower()
    best, best_score = None, 0
    for col_name, keywords in TOPIC_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score > best_score:
            best_score = score
            best = col_name
    if best_score > 0:
        return best
    return _klassifiziere_llm(url, text)


# ── Safe calculator ───────────────────────────────────────────────────────────

_SAFE_CHARS = re.compile(r'^[\d\s\+\-\*\/\%\(\)\.]+$')
_HAS_OP     = re.compile(r'\d\s*[\+\-\*\/\%]\s*[\-\d\(]')


def safe_eval(expr: str):
    expr = expr.strip()
    if not _SAFE_CHARS.match(expr):
        return None
    if not _HAS_OP.search(expr):
        return None
    try:
        result = eval(compile(expr, "<expr>", "eval"), {"__builtins__": {}}, {})
        if not isinstance(result, (int, float)):
            return None
        if isinstance(result, float) and result == int(result) and abs(result) < 1e15:
            return int(result)
        return round(result, 10)
    except Exception:
        return None


def extrahiere_mathe(text: str):
    candidates = re.findall(r'[\d\(\-][0-9\s\+\-\*\/\%\(\)\.]*', text)
    for cand in sorted(candidates, key=len, reverse=True):
        cand = re.sub(r'\s+', ' ', cand).strip()
        if _SAFE_CHARS.match(cand) and _HAS_OP.search(cand):
            return cand
    return None


# ── Memory search ─────────────────────────────────────────────────────────────

def suche_in_allen_collections(frage: str) -> str:
    resultate = []
    try:
        r = gespraeche.query(query_texts=[frage], n_results=2)
        if r["documents"][0]:
            resultate.extend(r["documents"][0])
    except Exception:
        pass
    try:
        for col in client.list_collections():
            if col.name.startswith("wissen_"):
                try:
                    r = client.get_collection(col.name).query(query_texts=[frage], n_results=2)
                    if r["documents"][0]:
                        resultate.extend(r["documents"][0])
                except Exception:
                    pass
    except Exception:
        pass
    return "\n\n".join(resultate[:5])


_BEGRUESSUNG  = {"hallo", "hi", "hey", "guten", "ich bin", "ich heisse"}
_AKTUELL_KEYS = {"2026", "2025", "neu", "aktuell", "heute", "neueste"}


def braucht_suche(frage: str) -> bool:
    if len(frage.split()) < 5:
        return False
    fl = frage.lower()
    if any(b in fl for b in _BEGRUESSUNG):
        return False
    if any(k in fl for k in _AKTUELL_KEYS):
        return True
    try:
        for col in client.list_collections():
            r = client.get_collection(col.name).query(query_texts=[frage], n_results=1)
            if r["documents"][0]:
                return False
    except Exception:
        pass
    return True


# ── Fact extraction ───────────────────────────────────────────────────────────

_ALLOWED_KEYS = {"name", "alter", "geburtstag", "wohnort", "beruf", "hobbys", "interessen", "sprache"}
_FAKE_NAMES   = {"user", "nutzer", "du", "ich", "assistant", "assistent"}


def extrahiere_fakten(user_msg: str, tens_msg: str):
    try:
        raw = _ollama([{
            "role": "user",
            "content": (
                f"Analysiere dieses Gespräch und extrahiere persönliche Fakten über den Nutzer.\n\n"
                f"Nutzer sagte: {user_msg}\n"
                f"Assistent antwortete: {tens_msg}\n\n"
                f"Erlaubte Keys NUR: name, alter, geburtstag, wohnort, beruf, hobbys, interessen, sprache\n"
                f"NIEMALS andere Keys erfinden. NIEMALS Fakten erfinden oder raten.\n"
                f"Datumsformat immer als: TT.MM.JJJJ\n"
                f"Wenn nichts Persönliches gesagt wurde: {{}}\n"
                f"Antworte NUR mit JSON, ohne Erklärung."
            ),
        }], timeout=30).strip()
        m = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
        if not m:
            return
        fakten = json.loads(m.group())
        fakten = {k: v for k, v in fakten.items() if k in _ALLOWED_KEYS and v and v != [] and v != {}}
        if "name" in fakten and str(fakten["name"]).lower() in _FAKE_NAMES:
            del fakten["name"]
        if fakten:
            profil = lade_profil()
            profil.update(fakten)
            speichere_profil(profil)
            print(f"  ▸ Profil aktualisiert: {fakten}")
    except Exception as e:
        print(f"  ▸ Fakten-Extraktion fehlgeschlagen: {e}")


# ── Knowledge processing ──────────────────────────────────────────────────────

def verarbeite_zu_wissen(url: str, text: str):
    wissen = _ollama([{
        "role": "user",
        "content": (
            f"Lies diesen Text und extrahiere strukturiertes Wissen auf Deutsch.\n\n"
            f"Text: {text[:3000]}\n\n"
            f"Format:\nFAKT: [was du gelernt hast]\nSKILL: [was du jetzt kannst]\n\n"
            f"Nur extrahieren was explizit im Text steht. Nichts erfinden."
        ),
    }])
    if wissen.startswith("LLM-Fehler"):
        print(f"  ▸ Wissen-Extraktion fehlgeschlagen: {wissen}")
        return

    ziel_col_name = klassifiziere_thema(url, text)
    ziel_col = client.get_or_create_collection(ziel_col_name)
    meta = [{"quelle": url, "typ": "wissen"}]

    try:
        ziel_col.add(documents=[wissen], ids=[url], metadatas=meta)
        print(f"  ▸ Gespeichert in '{ziel_col_name}': {url[:60]}")
    except Exception:
        ziel_col.update(documents=[wissen], ids=[url], metadatas=meta)
        print(f"  ▸ Aktualisiert in '{ziel_col_name}': {url[:60]}")


# ── Chat ──────────────────────────────────────────────────────────────────────

def chat(message: str, history: list = [], extrahiere: bool = True) -> list:
    profil    = lade_profil()
    profil_text = "\n".join(f"{k}: {v}" for k, v in profil.items()) or "Noch nichts."
    kontext   = suche_in_allen_collections(message)
    index     = lade_files_index()

    # ── Hallucination guard: frame context as verified FACTS ─────────────────
    if kontext:
        kontext_block = (
            "GESICHERTES WISSEN AUS DEINER DATENBANK (halte dich strikt daran):\n"
            + kontext
            + "\n\nAntworte NUR basierend auf diesen Fakten. "
              "Wenn du dir nicht sicher bist, sage 'Ich bin mir nicht sicher'."
        )
    else:
        kontext_block = (
            "Keine gespeicherten Informationen zu dieser Frage. "
            "Wenn du dir nicht sicher bist, sage 'Ich weiss es nicht' statt zu raten."
        )

    files_block = ""
    if index:
        lines = [
            f"- {e['name']} ({e.get('type','')}, {e.get('created','')[:10]}): {e.get('description','')[:60]}"
            for e in index[-10:]
        ]
        files_block = "\n\nVon dir erstellte/gelesene Dateien:\n" + "\n".join(lines)

    system = (
        f"Du bist TENS, mein persönlicher KI-Assistent.\n"
        f"WICHTIG: Antworte IMMER auf Deutsch. Niemals auf Englisch oder einer anderen Sprache.\n"
        f"Rede mich mit 'du' an. Sei direkt, klar und hilfreich – keine Floskeln.\n"
        f"Spezialisiert auf Programmierung, Cybersecurity (Ethical Hacking, Pentesting) und Technik.\n"
        f"Gib nur Informationen für legale, autorisierte Zwecke (eigene Labs, CTFs, autorisierte Pentests).\n"
        f"Verweigere klar illegale Anfragen.\n"
        f"Sage ehrlich 'Ich weiss es nicht' wenn du keine gesicherten Informationen hast.\n\n"
        f"Heute: {datetime.now().strftime('%d.%m.%Y')}\n\n"
        f"Was du über mich weißt:\n{profil_text}\n\n"
        f"Relevantes Wissen:\n{kontext_block}"
        f"{files_block}"
    )

    history.append({"role": "user", "content": message})

    reply = _ollama([{"role": "system", "content": system}] + history)

    history.append({"role": "assistant", "content": reply})
    print(f"\nTENS: {reply}\n")

    speichere_gespraech(message, reply)
    if extrahiere:
        extrahiere_fakten(message, reply)

    return history


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TENS bereit. Befehle: exit | lerne: <Thema> | lies: <Pfad> | erstelle: <Beschreibung>\n")
    history: list = []

    while True:
        try:
            user_input = input("Du: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nTschüss!")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "bye"}:
            print("Tschüss!")
            break

        # ── URL: scrape & learn ──────────────────────────────────────────────
        if user_input.startswith("http"):
            print("  ▸ Lese Webseite...")
            inhalt = lese_webseite(user_input)
            if len(inhalt) < 80:
                print("  ▸ Webseite konnte nicht gelesen werden.")
                continue
            verarbeite_zu_wissen(user_input, inhalt)
            history = chat(
                "Du hast gerade eine Webseite gelesen. Fasse in 3-4 Sätzen zusammen was du gelernt hast.",
                history, extrahiere=False,
            )

        # ── lerne: <Thema> ───────────────────────────────────────────────────
        elif user_input.lower().startswith("lerne:"):
            thema = user_input[6:].strip()
            if not thema:
                print("  ▸ Kein Thema angegeben.")
                continue
            print(f"  ▸ Lerne: {thema} ...")
            wissen = suche_und_lerne(f"{thema} erklärung tutorial")
            if len(wissen) < 80:
                print("  ▸ Nichts gefunden.")
                continue
            verarbeite_zu_wissen(thema, wissen)
            history = chat(
                f"Fasse auf Deutsch zusammen was du über '{thema}' gelernt hast.",
                history, extrahiere=False,
            )

        # ── lies: <Dateipfad> ────────────────────────────────────────────────
        elif user_input.lower().startswith("lies:"):
            pfad = user_input[5:].strip()
            print(f"  ▸ Lese Datei: {pfad}")
            inhalt, fehler = lese_datei(pfad)
            if fehler:
                print(f"  ▸ Fehler: {fehler}")
                continue
            if len(inhalt) < 10:
                print("  ▸ Datei ist leer.")
                continue
            verarbeite_zu_wissen(pfad, inhalt)
            # Track in index
            idx = lade_files_index()
            idx.append({
                "path":        pfad,
                "name":        pathlib.Path(pfad).name,
                "type":        "read",
                "created":     datetime.now().isoformat(),
                "description": inhalt[:100].replace("\n", " "),
            })
            speichere_files_index(idx)
            history = chat(
                f"Du hast die Datei '{pathlib.Path(pfad).name}' gelesen. "
                f"Fasse kurz zusammen was drin steht.",
                history, extrahiere=False,
            )

        # ── erstelle: <Beschreibung> ─────────────────────────────────────────
        elif user_input.lower().startswith("erstelle:"):
            beschreibung = user_input[9:].strip()
            if not beschreibung:
                print("  ▸ Keine Beschreibung angegeben.")
                continue
            print(f"  ▸ Erstelle: {beschreibung} ...")
            os.makedirs(FILES_DIR, exist_ok=True)
            # Ask TENS to generate content
            create_history = chat(
                f"Erstelle folgendes auf Deutsch: {beschreibung}\n\n"
                f"Schreibe NUR den Dateiinhalt, keine Erklärungen davor oder danach.",
                [], extrahiere=False,
            )
            content = create_history[-1]["content"] if create_history else ""
            if not content or len(content) < 10:
                print("  ▸ Inhalt konnte nicht generiert werden.")
                continue
            fname  = _bestimme_dateiname(beschreibung, content)
            fpath  = pathlib.Path(FILES_DIR) / fname
            fpath.write_text(content, encoding="utf-8")
            # Track
            idx = lade_files_index()
            idx.append({
                "path":        str(fpath),
                "name":        fname,
                "type":        "created",
                "created":     datetime.now().isoformat(),
                "description": beschreibung[:100],
            })
            speichere_files_index(idx)
            verarbeite_zu_wissen(str(fpath), content)
            print(f"  ▸ Datei gespeichert: {fpath}")
            history = chat(
                f"Du hast die Datei '{fname}' erfolgreich erstellt und unter '{fpath}' gespeichert.",
                history, extrahiere=False,
            )

        # ── normaler Chat ────────────────────────────────────────────────────
        else:
            math_expr   = extrahiere_mathe(user_input)
            math_result = safe_eval(math_expr) if math_expr else None

            if math_result is not None:
                print(f"  ▸ Rechner: {math_expr} = {math_result}")
                history = chat(
                    f"{user_input}\n\n[Python-Rechner: {math_expr} = {math_result}. "
                    f"Nenne genau dieses Ergebnis in deiner Antwort.]",
                    history, extrahiere=True,
                )

            elif braucht_suche(user_input):
                print("  ▸ Suche im Internet...")
                neues_wissen = suche_und_lerne(user_input)
                if len(neues_wissen.strip()) < 80:
                    # Nothing found anywhere — tell TENS to admit it
                    history = chat(
                        f"{user_input}\n\n[Keine zuverlässigen Informationen gefunden. "
                        f"Sage ehrlich 'Ich weiss es nicht'.]",
                        history, extrahiere=False,
                    )
                else:
                    verarbeite_zu_wissen(user_input, neues_wissen)
                    history = chat(
                        f"Beantworte die folgende Frage auf Deutsch anhand dieser aktuellen Informationen. "
                        f"Erfinde nichts dazu.\n\n"
                        f"Informationen:\n{neues_wissen[:2000]}\n\n"
                        f"Frage: {user_input}",
                        history, extrahiere=True,
                    )

            else:
                history = chat(user_input, history, extrahiere=True)
