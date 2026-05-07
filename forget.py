import chromadb
import os
import json

# ChromaDB komplett löschen
client = chromadb.PersistentClient(path="./tens_memory")

for col in client.list_collections():
    client.delete_collection(col.name)
    print(f"Gelöscht: {col.name}")

# JSON Profil leeren aber nicht löschen
PROFIL_FILE = "nutzer_profil.json"
if os.path.exists(PROFIL_FILE):
    with open(PROFIL_FILE, "w") as f:
        json.dump({}, f)
    print("Nutzerprofil geleert.")

print("\nAlles gelöscht. TENS ist wieder neu.")