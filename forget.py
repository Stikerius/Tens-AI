import chromadb

client = chromadb.PersistentClient(path="./tens_memory")
memory = client.get_or_create_collection("tens_memory")

# Alles löschen
client.delete_collection("tens_memory")
print("Gedächtnis gelöscht.")