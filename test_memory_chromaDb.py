import chromadb

client = chromadb.PersistentClient(path="./tens_memory")
memory = client.get_or_create_collection("gespraeche")
# Was ist in ChromaDB gespeichert?
alle = memory.get()
print(f"Anzahl Einträge: {len(alle['documents'])}")
for doc in alle['documents']:
    print(f"---\n{doc}")