import chromadb
import os
import json
import glob

MEMORY_PATH = "./tens_memory"
PROFIL_FILE = "nutzer_profil.json"

print("TENS – Gedächtnis wird vollständig gelöscht...\n")

# 1. Delete every ChromaDB collection
try:
    client = chromadb.PersistentClient(path=MEMORY_PATH)
    cols = client.list_collections()
    if cols:
        for col in cols:
            client.delete_collection(col.name)
            print(f"  ✓ Collection gelöscht: {col.name}")
    else:
        print("  (keine Collections vorhanden)")
except Exception as e:
    print(f"  ✗ ChromaDB Fehler: {e}")
    # Force-delete the SQLite file if the client failed
    db_file = os.path.join(MEMORY_PATH, "chroma.sqlite3")
    if os.path.exists(db_file):
        os.remove(db_file)
        print(f"  ✓ SQLite direkt gelöscht: {db_file}")

# 2. Clear nutzer_profil.json
if os.path.exists(PROFIL_FILE):
    with open(PROFIL_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f, indent=2)
    print(f"  ✓ Profil geleert: {PROFIL_FILE}")

# 3. Delete any JSON cache files (not the profile itself)
for f in glob.glob("*_cache.json") + glob.glob("cache_*.json"):
    os.remove(f)
    print(f"  ✓ Cache gelöscht: {f}")

print(f"\n✅ Fertig. TENS hat alles vergessen und ist wieder neu.")
