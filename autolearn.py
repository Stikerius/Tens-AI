import time
import chromadb
from scraper import suche_und_lerne, lese_webseite
from ddgs import DDGS

# ChromaDB Setup
client = chromadb.PersistentClient(path="./tens_memory")

THEMEN = {
    "python":        ["Python Programmierung Grundlagen", "Python Funktionen", "Python OOP"],
    "javascript":    ["JavaScript Grundlagen", "JavaScript DOM", "JavaScript Async"],
    "mathematik":    ["Mathematik Algebra", "Mathematik Geometrie", "Mathematik Analysis"],
    "physik":        ["Physik Mechanik", "Physik Thermodynamik", "Quantenmechanik"],
    "machine_learning": ["Machine Learning Grundlagen", "Neural Networks", "Deep Learning"],
    "netzwerk":      ["Netzwerktechnik Grundlagen", "TCP/IP Protokoll", "HTTP HTTPS"],
    "linux":         ["Linux Grundlagen", "Linux Terminal Befehle", "Linux Dateisystem"],
    "docker":        ["Docker Container Grundlagen", "Docker Compose", "Docker Networking"],
    "cybersecurity": ["Cybersecurity Grundlagen", "SQL Injection", "XSS Angriffe"],
    "fastapi":       ["FastAPI Python Grundlagen", "REST API Design", "API Authentication"],

}

print(f"TENS Lernmodus gestartet – {sum(len(v) for v in THEMEN.values())} Themen in {len(THEMEN)} Kategorien\n")

for kategorie, themen in THEMEN.items():
    # Eigene Collection pro Kategorie
    collection = client.get_or_create_collection(f"wissen_{kategorie}")
    print(f"📁 Kategorie: {kategorie.upper()}")
    
    for thema in themen:
        print(f"  → Lerne: {thema}")
        
        try:
            # Suchen
            with DDGS() as ddgs:
                resultate = list(ddgs.text(thema, max_results=3))
            
            for i, r in enumerate(resultate):
                url = r['href']
                inhalt = lese_webseite(url)
                
                if len(inhalt) > 100:
                    collection.add(
                        documents=[inhalt[:3000]],
                        ids=[f"{thema}_{i}_{url[:50]}"],
                        metadatas=[{
                            "thema": thema,
                            "kategorie": kategorie,
                            "quelle": url,
                        }]
                    )
            
            print(f"  ✓ Gespeichert: {thema}")
        except Exception as e:
            print(f"  ✗ Fehler: {e}")
        
        time.sleep(2)
    
    print(f"  [{kategorie} abgeschlossen]\n")

print("✅ Lernmodus abgeschlossen!")
print(f"Kategorien: {list(THEMEN.keys())}")