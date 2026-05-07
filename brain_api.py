from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import chromadb
import json
import os
import re
from collections import Counter
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
    "damit", "dabei", "deine", "seine", "keine", "jetzt", "hier",
    "lerne", "gelernt", "erklärt", "erkläre", "immer", "noch", "bereits",
    "werden", "haben", "hatte", "beim", "einen", "einer", "diesem",
    "dieser", "diesen", "welche", "welcher", "welches", "ihrer", "ihren",
    "sagte", "sagen", "gesagt", "antwortete", "antwortet", "frage", "fragte",
}

COLLECTION_CATEGORY = {
    "wissen_python":      "technologie",
    "wissen_javascript":  "technologie",
    "wissen_html":        "technologie",
    "wissen_css":         "technologie",
    "wissen_linux":       "technologie",
    "wissen_docker":      "technologie",
    "wissen_git":         "technologie",
    "wissen_allgemein":   "technologie",
    "wissen_mathematik":  "wissenschaft",
    "wissen_physik":      "wissenschaft",
    "wissen_chemie":      "wissenschaft",
    "wissen_biologie":    "wissenschaft",
    "wissen_astronomie":  "wissenschaft",
}


def collection_to_category(col_name: str) -> str:
    return COLLECTION_CATEGORY.get(
        col_name, "technologie" if col_name.startswith("wissen_") else "kern"
    )


def collection_display_name(col_name: str) -> str:
    if col_name.startswith("wissen_"):
        return col_name[7:].replace("_", " ").title()
    if col_name == "gespraeche":
        return "Gespräche"
    return col_name.replace("_", " ").title()


def url_to_topic(url: str) -> str:
    clean = re.sub(r"https?://(www\.)?", "", url)
    parts = clean.split("/")
    for part in parts[1:]:
        part = re.sub(r"[?#].*", "", part)
        part = re.sub(r"[-_]", " ", part)
        part = re.sub(r"\.\w+$", "", part)
        if len(part) > 2 and not part.isdigit():
            return part.strip().title()[:22]
    return parts[0][:22].title()


def extract_key_phrases(documents: list, max_phrases: int = 6) -> list:
    """Extract FAKT/SKILL lines; fall back to bigrams from conversation text."""
    fakt_lines = []
    for doc in documents:
        for line in doc.split("\n"):
            line = line.strip()
            if line.startswith("FAKT:"):
                text = line[5:].strip()
                if 8 < len(text) < 90:
                    fakt_lines.append(text)
            elif line.startswith("SKILL:"):
                text = line[6:].strip()
                if 8 < len(text) < 90:
                    fakt_lines.append(text)

    if fakt_lines:
        return fakt_lines[:max_phrases]

    # Bigram fallback for conversation documents
    all_text = " ".join(documents[:20])
    all_text = re.sub(r"(Nutzer|TENS):\s*", " ", all_text)
    words = re.findall(r"\b[A-Za-zÄäÖöÜüß]{5,20}\b", all_text)
    valid = [w.lower() for w in words if w.lower() not in STOP_WORDS]

    bigrams: Counter = Counter()
    for i in range(len(valid) - 1):
        bigrams[f"{valid[i].capitalize()} {valid[i+1].capitalize()}"] += 1

    phrases = [p for p, c in bigrams.most_common(max_phrases * 2) if c >= 2]
    if phrases:
        return phrases[:max_phrases]

    freq: Counter = Counter(valid)
    return [w.capitalize() for w, c in freq.most_common(max_phrases) if c >= 2]


@app.get("/brain")
def get_brain():
    client = chromadb.PersistentClient(path=MEMORY_PATH)
    all_cols = client.list_collections()
    col_names = {c.name for c in all_cols}

    nodes = [{
        "id":      "tens-core",
        "label":   "TENS",
        "cat":     "kern",
        "entries": 1,
        "facts":   ["Persönlicher KI-Assistent", "Dolphin-Mistral via Ollama", "Lokales Wissensnetz"],
    }]
    links = []
    total_entries = 0

    # ── wissen_* collections ──────────────────────────────────────────────
    for col in sorted(all_cols, key=lambda c: c.name):
        if not col.name.startswith("wissen_"):
            continue
        try:
            wissen_col = client.get_collection(col.name)
            data  = wissen_col.get(include=["documents", "metadatas"])
            docs  = data["documents"] or []
            ids   = data["ids"] or []
            count = len(docs)
            total_entries += count

            cat     = collection_to_category(col.name)
            display = collection_display_name(col.name)
            node_id = f"col-{col.name}"
            phrases = extract_key_phrases(docs, max_phrases=5)
            facts   = phrases if phrases else [f"{count} Einträge gespeichert"]

            nodes.append({
                "id":      node_id,
                "label":   display,
                "cat":     cat,
                "entries": max(count, 1),
                "facts":   facts,
            })
            links.append({"source": "tens-core", "target": node_id})

            # Sub-nodes: one per unique source (URL or named ID), up to 4
            sources_seen: dict = {}
            for i, (doc_id, doc) in enumerate(zip(ids, docs)):
                if len(sources_seen) >= 4:
                    break
                label = url_to_topic(doc_id) if doc_id.startswith("http") else doc_id[:20].replace("_", " ").title()
                if label in sources_seen:
                    continue
                sources_seen[label] = True

                sub_id    = f"sub-{col.name}-{i}"
                sub_facts = [l.strip()[5:].strip() for l in doc.split("\n") if l.strip().startswith("FAKT:")][:3]
                if not sub_facts:
                    sub_facts = [f"Quelle: {label}"]

                nodes.append({
                    "id":      sub_id,
                    "label":   label[:18],
                    "cat":     cat,
                    "entries": 1,
                    "facts":   sub_facts,
                })
                links.append({"source": node_id, "target": sub_id})
        except Exception:
            pass

    # ── gespraeche collection ─────────────────────────────────────────────
    if "gespraeche" in col_names:
        try:
            gcol  = client.get_collection("gespraeche")
            data  = gcol.get(include=["documents", "metadatas"])
            docs  = data["documents"] or []
            metas = data["metadatas"] or []
            total_entries += len(docs)

            # Only count real conversations (not old web-knowledge entries)
            conv_docs = [d for d, m in zip(docs, metas)
                         if not (m and m.get("typ") == "wissen")]

            phrases = extract_key_phrases(conv_docs or docs, max_phrases=6)
            facts   = phrases if phrases else ["Gesprächsverlauf mit TENS"]

            nodes.append({
                "id":      "col-gespraeche",
                "label":   "Gespräche",
                "cat":     "kern",
                "entries": max(len(conv_docs), 1),
                "facts":   facts,
            })
            links.append({"source": "tens-core", "target": "col-gespraeche"})
        except Exception:
            pass

    # ── nutzer_profil.json → Persönlichkeit cluster ───────────────────────
    if os.path.exists(PROFIL_FILE):
        try:
            with open(PROFIL_FILE, "r", encoding="utf-8") as f:
                profil = json.load(f)
            if profil:
                name      = profil.get("name", "Nutzer")
                person_id = "personal-" + re.sub(r"\W+", "", name.lower())

                nodes.append({
                    "id":      person_id,
                    "label":   name.upper(),
                    "cat":     "persoenlich",
                    "entries": max(len(profil) * 2, 2),
                    "facts":   [f"{k}: {v}" for k, v in profil.items() if v][:6],
                })
                links.append({"source": "tens-core", "target": person_id})

                KEY_LABELS = {
                    "name":       "Name",
                    "alter":      "Alter",
                    "geburtstag": "Geburtstag",
                    "wohnort":    "Wohnort",
                    "beruf":      "Beruf",
                    "hobbys":     "Hobbys",
                    "interessen": "Interessen",
                    "sprache":    "Sprache",
                }
                for key, val in profil.items():
                    if not val:
                        continue
                    fact_id = f"fact-{key}"
                    label   = KEY_LABELS.get(key, key.capitalize())
                    nodes.append({
                        "id":      fact_id,
                        "label":   label,
                        "cat":     "persoenlich",
                        "entries": 1,
                        "facts":   [str(val)],
                    })
                    links.append({"source": person_id, "target": fact_id})
        except Exception:
            pass

    return {
        "nodes": nodes,
        "links": links,
        "meta":  {
            "total_entries": total_entries,
            "updated":       datetime.now().isoformat(),
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
