from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import chromadb
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PROFIL_FILE = "./nutzer_profil.json"
MEMORY_PATH = "./tens_memory"

STOP_WORDS = {
    "der", "die", "das", "und", "ist", "in", "zu", "den", "des", "mit", "ein", "eine",
    "einen", "einem", "einer", "sich", "von", "an", "auf", "für", "als", "auch", "es",
    "bei", "hat", "wurde", "wird", "sind", "war", "er", "sie", "wir", "ich", "du",
    "man", "so", "wie", "aber", "oder", "nicht", "noch", "mehr", "nach", "aus", "durch",
    "über", "unter", "wenn", "dann", "kann", "dass", "haben", "werden", "nutzer", "tens",
    "the", "and", "for", "are", "with", "has", "was", "from", "have", "been", "which",
    "will", "your", "all", "use", "can", "its", "you", "our", "new", "one", "about",
    "also", "into", "than", "fakt", "skill", "dieser", "diese", "dieses", "sehr",
    "damit", "dabei", "durch", "deine", "seine", "keine", "jetzt", "hier", "dass",
    "lerne", "gelernt", "erklärt", "erkläre", "immer", "noch", "bereits", "wurde",
    "werden", "haben", "hatte", "hatte", "beim", "beim", "einen", "einer", "diesem",
    "dieser", "diesen", "diesem", "welche", "welcher", "welches", "ihrer", "ihren",
}

CATEGORY_MAP = {
    "technologie": [
        "python", "javascript", "react", "docker", "git", "ollama", "chromadb",
        "api", "code", "llm", "model", "fastapi", "server", "gpu", "cpu",
        "software", "hardware", "database", "sql", "linux", "windows", "html",
        "css", "json", "http", "rest", "tensorflow", "pytorch", "numpy", "pandas",
        "embedding", "vektor", "pipeline", "framework", "library", "uvicorn",
        "beautifulsoup", "requests", "flask", "django", "scraping", "crawling",
        "programm", "programmi", "skript", "funktion", "klasse", "objekt",
    ],
    "wissenschaft": [
        "physik", "biologie", "chemie", "mathematik", "astronomie", "quantum",
        "quanten", "wissenschaft", "forschung", "theorie", "atom", "molekül",
        "evolution", "genetik", "neural", "neuronales", "backpropagation",
        "transformer", "algorithmus", "statistik", "wahrscheinlichkeit",
    ],
    "aktuell": [
        "2025", "2026", "2024", "news", "update", "release", "launch",
        "mistral", "openai", "gpt", "claude", "gemini", "llama", "deepseek",
        "anthropic", "google", "microsoft", "nvidia", "aktuell",
    ],
    "persoenlich": [
        "ivan", "ubs", "zürich", "schule", "bzz", "lehrling", "ausbildung",
        "geburtstag", "name", "beruf", "wohnort", "hobby",
    ],
}


def categorize(word: str) -> str:
    w = word.lower()
    for cat, keywords in CATEGORY_MAP.items():
        if any(k in w or w == k for k in keywords):
            return cat
    return "kern"


def url_to_topic(url: str) -> str:
    clean = re.sub(r'https?://(www\.)?', '', url)
    parts = clean.split("/")
    for part in parts[1:]:
        part = re.sub(r'[?#].*', '', part)
        part = re.sub(r'[-_]', ' ', part)
        part = re.sub(r'\.\w+$', '', part)
        if len(part) > 2 and not part.isdigit():
            return part.strip().title()[:24]
    return parts[0][:24].title()


@app.get("/brain")
def get_brain():
    client = chromadb.PersistentClient(path=MEMORY_PATH)
    collection = client.get_or_create_collection("gespraeche")
    data = collection.get(include=["documents", "metadatas"])

    documents = data["documents"] or []
    metadatas = data["metadatas"] or [{}] * len(documents)
    ids = data["ids"] or []
    total = len(documents)

    nodes = [{
        "id": "tens-core",
        "label": "TENS",
        "cat": "kern",
        "entries": max(total, 1),
        "facts": [
            "Persönlicher KI-Assistent",
            "Dolphin-Mistral via Ollama",
            f"{total} Gedächtnis-Einträge",
        ],
    }]
    links = []

    if documents:
        knowledge_topics: dict = {}
        word_freq: Counter = Counter()
        word_docs: dict = defaultdict(set)

        for i, (doc, meta) in enumerate(zip(documents, metadatas)):
            if meta and meta.get("typ") == "wissen":
                source = meta.get("quelle", ids[i] if i < len(ids) else "")
                topic = url_to_topic(source) if source.startswith("http") else str(source)[:24].title()
                if topic not in knowledge_topics:
                    knowledge_topics[topic] = {"count": 0, "facts": [], "cat": categorize(topic)}
                knowledge_topics[topic]["count"] += 1
                for line in doc.split("\n"):
                    line = line.strip()
                    if line.startswith(("FAKT:", "SKILL:")):
                        knowledge_topics[topic]["facts"].append(line[:70])
            else:
                words = re.findall(r'\b[A-Za-zÄäÖöÜüß]{4,20}\b', doc)
                for w in words:
                    wl = w.lower()
                    if wl not in STOP_WORDS:
                        word_freq[wl] += 1
                        word_docs[wl].add(i)

        # Knowledge topic nodes (max 12)
        for topic, info in sorted(knowledge_topics.items(), key=lambda x: -x[1]["count"])[:12]:
            nid = "kn-" + re.sub(r'\W+', '-', topic.lower())[:18]
            facts = info["facts"][:4] if info["facts"] else [f"Quelle: {topic}"]
            nodes.append({
                "id": nid,
                "label": topic,
                "cat": info["cat"],
                "entries": info["count"],
                "facts": facts,
            })
            links.append({"source": "tens-core", "target": nid})

        # Keyword nodes from conversations (max 12, min 2 occurrences)
        added = 0
        existing_labels = {n["label"].lower() for n in nodes}
        for word, count in word_freq.most_common(40):
            if added >= 12:
                break
            if count < 2:
                break
            label = word.capitalize()
            if any(label.lower() in ex or ex in label.lower() for ex in existing_labels):
                continue
            nid = "kw-" + word[:18]
            cat = categorize(word)
            nodes.append({
                "id": nid,
                "label": label,
                "cat": cat,
                "entries": count,
                "facts": [f"In {len(word_docs[word])} Gesprächen erwähnt"],
            })
            links.append({"source": "tens-core", "target": nid})
            existing_labels.add(label.lower())
            added += 1

        # Cross-links within same category (chain them)
        by_cat: dict = defaultdict(list)
        for n in nodes:
            if n["id"] != "tens-core":
                by_cat[n["cat"]].append(n["id"])
        for cat_nodes in by_cat.values():
            for i in range(len(cat_nodes) - 1):
                links.append({"source": cat_nodes[i], "target": cat_nodes[i + 1]})

    # Personal profile node
    if os.path.exists(PROFIL_FILE):
        try:
            with open(PROFIL_FILE, "r", encoding="utf-8") as f:
                profil = json.load(f)
            if profil:
                name = profil.get("name", "Nutzer")
                person_id = "personal-" + re.sub(r'\W+', '', name.lower())
                nodes.append({
                    "id": person_id,
                    "label": name,
                    "cat": "persoenlich",
                    "entries": len(profil),
                    "facts": [f"{k}: {v}" for k, v in profil.items() if v][:6],
                })
                links.append({"source": "tens-core", "target": person_id})
        except Exception:
            pass

    return {
        "nodes": nodes,
        "links": links,
        "meta": {
            "total_entries": total,
            "updated": datetime.now().isoformat(),
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
