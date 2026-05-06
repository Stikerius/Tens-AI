import chromadb

client = chromadb.PersistentClient(path="./tens_memory")

# Alle Collections löschen
for col in client.list_collections():
    client.delete_collection(col.name)
    print(f"Gelöscht: {col.name}")

print("Alles gelöscht.")