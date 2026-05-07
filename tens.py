import re
import requests
import chromadb
import json
import os
from datetime import datetime
from scraper import lese_webseite, suche_und_lerne

# ChromaDB Setup
client = chromadb.PersistentClient(path="./tens_memory")
gespraeche = client.get_or_create_collection("gespraeche")

# Topic → collection mapping for automatic knowledge routing
TOPIC_KEYWORDS = {
    "wissen_python":      ["python", "pip", "pandas", "numpy", "pytorch", "tensorflow", "flask", "django", "fastapi", "jupyter", "scipy", "matplotlib"],
    "wissen_javascript":  ["javascript", " js ", "node.js", "nodejs", "react", "vue", "angular", "typescript", "npm", "webpack", "deno", "bun"],
    "wissen_html":        ["html", " css ", "stylesheet", "dom ", "webpage", "webseite", "browser", "frontend", "responsive", "tailwind"],
    "wissen_mathematik":  ["mathematik", "mathe", "algebra", "calculus", "matrix", "gleichung", "integral", "ableitung", "statistik", "logarithmus"],
    "wissen_physik":      ["physik", "quantenphysik", "quantum", "relativität", "thermodynamik", "elektromagnetismus", "mechanik", "optik", "energie"],
    "wissen_linux":       ["linux", "bash", "shell", "terminal", "ubuntu", "debian", "arch", "systemctl", "sudo", "chmod", "grep", "awk", "sed", "unix"],
    "wissen_docker":      ["docker", "container", "kubernetes", "k8s", "dockerfile", "image", "pod", "helm", "compose"],
    "wissen_git":         ["git ", "github", "gitlab", "commit", "branch", "merge", "pull request", "repository", "rebase", "stash"],
    "wissen_chemie":      ["chemie", "molekül", "atom", "reaktion", "verbindung", "element", "periodensystem", "säure", "base"],
    "wissen_biologie":    ["biologie", "zelle", "dna", "rna", "evolution", "genetik", "protein", "organ", "ökosystem"],
}


def klassifiziere_thema(url: str, text: str) -> str:
    """Detect the best wissen_* collection for this content."""
    combined = (url + " " + text[:2000]).lower()
    best, best_score = None, 0
    for col_name, keywords in TOPIC_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score > best_score:
            best_score = score
            best = col_name
    return best if best_score > 0 else "wissen_allgemein"

# ── Safe calculator ──────────────────────────────────────────────────────────

_SAFE_CHARS = re.compile(r'^[\d\s\+\-\*\/\%\(\)\.]+$')
_HAS_OP     = re.compile(r'\d\s*[\+\-\*\/\%]\s*[\-\d\(]')


def safe_eval(expr: str):
    """Evaluate a basic math expression. Returns int/float or None on invalid input."""
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
    """Find the first math expression in natural-language text."""
    candidates = re.findall(r'[\d\(\-][0-9\s\+\-\*\/\%\(\)\.]*', text)
    for cand in sorted(candidates, key=len, reverse=True):
        cand = re.sub(r'\s+', ' ', cand).strip()
        if _SAFE_CHARS.match(cand) and _HAS_OP.search(cand):
            return cand
    return None

# JSON für wichtige Fakten
PROFIL_FILE = "nutzer_profil.json"

def lade_profil():
    if os.path.exists(PROFIL_FILE):
        with open(PROFIL_FILE, "r") as f:
            return json.load(f)
    return {}

def speichere_profil(profil):
    with open(PROFIL_FILE, "w") as f:
        json.dump(profil, f, indent=2)

def speichere_gespraech(user_msg, tens_msg):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    gespraeche.add(
        documents=[f"Nutzer: {user_msg}\nTENS: {tens_msg}"],
        ids=[timestamp]
    )

def suche_in_allen_collections(frage):
    resultate = []

    # In Gesprächen suchen
    try:
        r = gespraeche.query(query_texts=[frage], n_results=2)
        if r["documents"][0]:
            resultate.extend(r["documents"][0])
    except:
        pass

    # In allen Wissens-Collections suchen
    try:
        alle = client.list_collections()
        for col in alle:
            if col.name.startswith("wissen_"):
                wissen_col = client.get_collection(col.name)
                r = wissen_col.query(query_texts=[frage], n_results=2)
                if r["documents"][0]:
                    resultate.extend(r["documents"][0])
    except:
        pass

    return "\n\n".join(resultate[:5])

def braucht_suche(frage):
    if len(frage.split()) < 5:
        return False

    begruessung = ["hallo", "hi", "hey", "guten", "ich bin", "ich heisse"]
    if any(b in frage.lower() for b in begruessung):
        return False

    aktuelle_keywords = ["2026", "2025", "neu", "aktuell", "heute", "neueste"]
    if any(k in frage.lower() for k in aktuelle_keywords):
        return True

    # In ALLEN Collections prüfen
    try:
        alle = client.list_collections()
        for col in alle:
            col_obj = client.get_collection(col.name)
            r = col_obj.query(query_texts=[frage], n_results=1)
            if r["documents"][0]:
                return False
    except:
        pass

    return True

def extrahiere_fakten(user_msg, tens_msg):
    response = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": "dolphin-mistral",
            "messages": [{
                "role": "user",
                "content": f"""Analysiere dieses Gespräch und extrahiere persönliche Fakten über den Nutzer.

Nutzer sagte: {user_msg}
Assistent antwortete: {tens_msg}

Erlaubte Keys NUR: name, alter, geburtstag, wohnort, beruf, hobbys, interessen, sprache
NIEMALS andere Keys erfinden.
NIEMALS Fakten erfinden oder raten.
Datumsformate die du erkennen sollst: 14.08.2008, 14.8.08, 14. August 2008, August 14 2008
Immer speichern als: TT.MM.JJJJ
Wenn unsicher: weglassen.
Wenn nichts Persönliches gesagt wurde: {{}}
Antworte NUR mit JSON."""
            }],
            "stream": False
        }
    )
    try:
        text = response.json()["message"]["content"].strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        fakten = json.loads(text)
        fakten = {k: v for k, v in fakten.items() if v is not None and v != "" and v != []}
        # Falsche Namen entfernen
        if "name" in fakten and fakten["name"].lower() in ["user", "nutzer", "du", "ich"]:
            del fakten["name"]
        if fakten:
            profil = lade_profil()
            profil.update(fakten)
            speichere_profil(profil)
            print(f"[Gespeichert: {fakten}]")
    except:
        pass

def verarbeite_zu_wissen(url, text):
    response = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": "dolphin-mistral",
            "messages": [{
                "role": "user",
                "content": f"""Du liest diesen Text und extrahierst daraus strukturiertes Wissen.

Text: {text[:3000]}

Erstelle eine Liste von Dingen die du gelernt hast – als konkrete Fakten und Fähigkeiten.
Format:
FAKT: [was du gelernt hast]
SKILL: [was du jetzt kannst/weisst]

WICHTIG: Nur extrahieren was der Nutzer EXPLIZIT gesagt hat.
NIEMALS Fakten erfinden oder raten.
Wenn unsicher: weglassen.

Extrahiere alles Wichtige aus dem Text."""
            }],
            "stream": False
        }
    )

    wissen = response.json()["message"]["content"]

    # Route to the correct wissen_* collection based on topic
    ziel_col_name = klassifiziere_thema(url, text)
    ziel_col = client.get_or_create_collection(ziel_col_name)

    try:
        ziel_col.add(
            documents=[wissen],
            ids=[url],
            metadatas=[{"quelle": url, "typ": "wissen"}]
        )
        print(f"[TENS hat neues Wissen gespeichert in '{ziel_col_name}': {url}]")
        print(wissen)
    except:
        ziel_col.update(
            documents=[wissen],
            ids=[url],
            metadatas=[{"quelle": url, "typ": "wissen"}]
        )
        print(f"[Wissen aktualisiert in '{ziel_col_name}': {url}]")

def chat(message, history=[], extrahiere=True):
    profil = lade_profil()
    profil_text = "\n".join([f"{k}: {v}" for k, v in profil.items()])

    # In allen Collections suchen
    alte_gespraeche = suche_in_allen_collections(message)

    system = f"""Du bist TENS, mein persönlicher KI-Assistent.
WICHTIG: Antworte IMMER auf Deutsch, egal in welcher Sprache der Nutzer schreibt.
Kurz und locker, direkt auf den Punkt.
Rede mich mit "du" an.
Heute: {datetime.now().strftime("%d.%m.%Y")}

Was du über mich weisst:
{profil_text if profil_text else "Noch nichts."}

Relevantes Wissen:
{alte_gespraeche if alte_gespraeche else "Keine."}"""
    history.append({"role": "user", "content": message})

    response = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": "dolphin-mistral",
            "messages": [{"role": "system", "content": system}] + history,
            "stream": False
        }
    )

    reply = response.json()["message"]["content"]
    history.append({"role": "assistant", "content": reply})
    print(f"\nTENS: {reply}\n")

    speichere_gespraech(message, reply)
    if extrahiere:
        extrahiere_fakten(message, reply)

    return history

print("TENS ist bereit. Tippe 'exit' zum Beenden.\n")
history = []

while True:
    user_input = input("Du: ")
    if user_input.lower() == "exit":
        break
    if user_input.startswith("http"):
        print("[TENS liest und lernt...]")
        inhalt = lese_webseite(user_input)
        verarbeite_zu_wissen(user_input, inhalt)
        user_input = f"Du hast gerade diese Webseite gelesen. Fasse in 3-4 Sätzen zusammen was du gelernt hast."
        history = chat(user_input, history, extrahiere=False)
    elif user_input.lower().startswith("lerne:"):
        thema = user_input[6:].strip()
        print(f"[TENS lernt autonom: {thema}]")
        wissen = suche_und_lerne(thema)
        verarbeite_zu_wissen(thema, wissen)
        user_input = f"Fasse zusammen was du über '{thema}' gelernt hast."
        history = chat(user_input, history, extrahiere=False)
    else:
        math_expr   = extrahiere_mathe(user_input)
        math_result = safe_eval(math_expr) if math_expr else None

        if math_result is not None:
            print(f"[Rechner: {math_expr} = {math_result}]")
            user_input = (
                f"{user_input}\n\n"
                f"[Python-Rechner Ergebnis: {math_expr} = {math_result}. "
                f"Nenne genau dieses Ergebnis in deiner Antwort.]"
            )
        elif braucht_suche(user_input):
            print("[TENS sucht im Internet...]")
            neues_wissen = suche_und_lerne(user_input)
            verarbeite_zu_wissen(user_input, neues_wissen)
            user_input = f"""WICHTIG: Beantworte NUR basierend auf diesen aktuellen Informationen. Erfinde nichts dazu.

Aktuelle Informationen:
{neues_wissen[:2000]}

Frage: {user_input}"""
        history = chat(user_input, history, extrahiere=True)