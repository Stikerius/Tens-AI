import requests
import chromadb
import json
import os
from datetime import datetime
from scraper import lese_webseite, suche_und_lerne

# ChromaDB Setup
client = chromadb.PersistentClient(path="./tens_memory")
gespraeche = client.get_or_create_collection("gespraeche")

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
    # Gespräch in ChromaDB speichern
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    gespraeche.add(
        documents=[f"Nutzer: {user_msg}\nTENS: {tens_msg}"],
        ids=[timestamp]
    )

def suche_gespraeche(frage):
    # Relevante alte Gespräche suchen
    try:
        results = gespraeche.query(query_texts=[frage], n_results=3)
        if results["documents"][0]:
            return "\n".join(results["documents"][0])
    except:
        pass
    return ""

def braucht_suche(frage):
    # Aktuelle Themen immer suchen
    aktuelle_keywords = ["2026", "2025", "neu", "aktuell", "heute", "neueste", "gerade"]
    if any(k in frage.lower() for k in aktuelle_keywords):
        return True
    
    # Sonst prüfen ob Wissen vorhanden
    results = gespraeche.query(query_texts=[frage], n_results=1)
    if results["documents"][0]:
        return False
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
        fakten = {k: v for k, v in fakten.items() if v is not None and v != ""}
        fakten = {k: v for k, v in fakten.items() if v is not None and v != "" and v != []}
        if fakten:
            profil = lade_profil()
            profil.update(fakten)
            speichere_profil(profil)
            print(f"[Gespeichert: {fakten}]")
    except:
        pass

def verarbeite_zu_wissen(url, text):
    # TENS versteht den Inhalt und extrahiert strukturiertes Wissen
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

Beispiel:
FAKT: Python wurde 1991 von Guido van Rossum entwickelt
SKILL: Ich kann erklären wie Python Einrückungen statt Klammern nutzt

Extrahiere alles Wichtige aus dem Text."""
            }],
            "stream": False
        }
    )
    
    wissen = response.json()["message"]["content"]
    
    # Wissen in ChromaDB speichern
    try:
        gespraeche.add(
            documents=[wissen],
            ids=[url],
            metadatas=[{"quelle": url, "typ": "wissen"}]
        )
        print(f"[TENS hat neues Wissen gespeichert aus: {url}]")
        print(wissen)
    except:
        # URL bereits gespeichert - updaten
        gespraeche.update(
            documents=[wissen],
            ids=[url],
            metadatas=[{"quelle": url, "typ": "wissen"}]
        )
        print(f"[Wissen aktualisiert: {url}]")

def chat(message, history=[], extrahiere=True):
    profil = lade_profil()
    profil_text = "\n".join([f"{k}: {v}" for k, v in profil.items()])
    
    # Relevante Gespräche aus ChromaDB holen
    alte_gespraeche = suche_gespraeche(message)
    
    system = f"""Du bist TENS, persönlicher KI-Assistent von Ivan.
Antworte auf Deutsch, kurz und direkt.
Rede den Nutzer mit "du" an.
Sei locker und unkompliziert.
Heutiges Datum: {datetime.now().strftime("%d.%m.%Y")}

Was du über den Nutzer weisst:
{profil_text if profil_text else "Noch nichts bekannt."}

Relevante vergangene Gespräche:
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
    
    # Gespräch speichern + Fakten extrahieren
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
    # URL automatisch erkennen
    if user_input.startswith("http"):
        print("[TENS liest und lernt...]")
        inhalt = lese_webseite(user_input)
        verarbeite_zu_wissen(user_input, inhalt)
        user_input = f"Du hast gerade diese Webseite gelesen und Wissen daraus extrahiert. Fasse in 3-4 Sätzen zusammen was du über das Thema gelernt hast:\n\nDein extrahiertes Wissen wurde gespeichert."        
        history = chat(user_input, history, extrahiere=False)
    else:
        if braucht_suche(user_input):
            print("[TENS hat kein Wissen dazu – sucht im Internet...]")
            neues_wissen = suche_und_lerne(user_input)
            verarbeite_zu_wissen(user_input, neues_wissen)
            user_input = f"""WICHTIG: Beantworte NUR basierend auf diesen aktuellen Informationen. Erfinde nichts dazu.

Aktuelle Informationen:
{neues_wissen[:2000]}

Frage: {user_input}"""
        history = chat(user_input, history, extrahiere=False)  # ← False