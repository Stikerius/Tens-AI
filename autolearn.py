import argparse
import time
import chromadb
from ddgs import DDGS
from scraper import lese_webseite

client = chromadb.PersistentClient(path="./tens_memory")

# ── Topic list ────────────────────────────────────────────────────────────────
# Format: { "wissen_<collection>": ["Suchanfrage 1", ...], ... }

THEMEN = {
    "wissen_python": [
        "Python Grundlagen Variablen Datentypen",
        "Python Funktionen und Scope",
        "Python OOP Klassen Vererbung",
        "Python List Comprehensions Generators",
        "Python Decorators und Closures",
        "Python Async Await Asyncio",
        "Python Error Handling Exceptions",
        "Python File IO Pathlib",
        "Python Regular Expressions re Modul",
        "Python Dataclasses Pydantic",
        "Python Virtual Environments pip",
        "Python Testing pytest Unittest",
        "Python Type Hints Annotations",
        "Python Context Manager with Statement",
        "Python Multiprocessing Threading",
    ],
    "wissen_javascript": [
        "JavaScript ES6 Arrow Functions Destructuring",
        "JavaScript Promises async await",
        "JavaScript DOM Manipulation Events",
        "JavaScript Fetch API REST Requests",
        "TypeScript Grundlagen Typen Interfaces",
        "TypeScript Generics und Utility Types",
        "React Hooks useState useEffect",
        "React Context API State Management",
        "React Router Navigation",
        "Vue 3 Composition API",
        "Node.js Grundlagen Event Loop",
        "Node.js Express REST API",
        "Node.js Streams und Buffer",
        "npm Yarn Package Manager",
        "WebSockets real-time Kommunikation",
        "GraphQL Queries Mutations",
        "Jest Testing JavaScript",
    ],
    "wissen_html": [
        "HTML5 Semantische Elemente",
        "CSS Grid Layout System",
        "CSS Flexbox Grundlagen",
        "CSS Custom Properties Variables",
        "CSS Animations Transitions Keyframes",
        "Tailwind CSS Utility Classes",
        "Bootstrap 5 Komponenten",
        "Responsive Web Design Media Queries",
        "Web Accessibility ARIA Screen Reader",
        "SVG Grundlagen und Animation",
        "Canvas API JavaScript",
        "Progressive Web Apps PWA",
    ],
    "wissen_sql": [
        "SQL SELECT Grundlagen Joins",
        "SQL Subqueries und Window Functions",
        "PostgreSQL Fortgeschrittene Features",
        "PostgreSQL Indexing Performance",
        "MongoDB CRUD Aggregation Pipeline",
        "MongoDB Indexierung Schema Design",
        "Redis Datenstrukturen Caching",
        "Redis Pub Sub Messaging",
        "Database Normalisierung Design",
        "ORM SQLAlchemy Grundlagen",
    ],
    "wissen_algorithmen": [
        "Big O Notation Komplexität",
        "Arrays LinkedLists Datenstrukturen",
        "Stacks Queues Heaps",
        "Binary Trees BST Traversal",
        "Hash Tables Collision Handling",
        "Graph Algorithms BFS DFS",
        "Dijkstra Shortest Path",
        "Dynamic Programming Memoization",
        "Sorting Algorithms QuickSort MergeSort",
        "Design Patterns Singleton Factory",
        "Design Patterns Observer Strategy",
        "SOLID Prinzipien Software Design",
        "Clean Code Principles",
        "Funktionale Programmierung Grundlagen",
        "REST API Best Practices Design",
    ],
    "wissen_docker": [
        "Docker Container Images Grundlagen",
        "Dockerfile Build Optimierung",
        "Docker Compose Multi-Container Apps",
        "Docker Networking Volumes",
        "Kubernetes Pods Deployments",
        "Kubernetes Services Ingress",
        "Kubernetes ConfigMaps Secrets",
        "Helm Charts Kubernetes",
        "CI/CD Pipeline Konzepte",
        "GitHub Actions Workflows",
        "GitLab CI Pipeline",
        "Infrastructure as Code Terraform",
    ],
    "wissen_linux": [
        "Linux Terminal Befehle Grundlagen",
        "Bash Scripting Variables Loops",
        "Bash Funktionen und Pipes",
        "Linux Dateisystem Berechtigungen chmod",
        "Linux Prozesse ps kill systemctl",
        "Linux Netzwerk ifconfig netstat",
        "SSH Konfiguration Schlüssel",
        "Nginx Webserver Konfiguration",
        "DNS Grundlagen Namensauflösung",
        "TCP IP Protokoll Stack",
        "HTTP HTTPS Protokoll Grundlagen",
        "Firewall iptables nftables",
        "SSL TLS Zertifikate Let's Encrypt",
        "Cron Jobs Scheduling Linux",
    ],
    "wissen_ki": [
        "Machine Learning Supervised Learning",
        "Machine Learning Unsupervised Clustering",
        "Neural Networks Grundlagen Perceptron",
        "Deep Learning Convolutional Networks CNN",
        "Recurrent Networks LSTM GRU",
        "Transformer Architektur Attention",
        "BERT GPT Sprachmodelle",
        "Large Language Models LLM Grundlagen",
        "Prompt Engineering Techniques",
        "Fine-tuning LLMs LoRA",
        "RAG Retrieval Augmented Generation",
        "Vector Databases FAISS ChromaDB",
        "Word Embeddings Word2Vec",
        "PyTorch Grundlagen Tensoren",
        "TensorFlow Keras Sequential API",
        "Scikit-learn Classification Regression",
        "Hugging Face Transformers Pipeline",
        "Computer Vision Object Detection",
        "NLP Tokenization Named Entity Recognition",
        "Reinforcement Learning Grundlagen",
    ],
    "wissen_security": [
        "Cybersecurity CIA Triad Grundlagen",
        "SQL Injection Angriffe Prävention",
        "XSS Cross Site Scripting",
        "CSRF Cross Site Request Forgery",
        "SSRF Server Side Request Forgery",
        "Command Injection Path Traversal",
        "Authentication Passwort Hashing bcrypt",
        "JWT JSON Web Tokens",
        "OAuth 2.0 OpenID Connect",
        "Penetration Testing Methodik",
        "OWASP Top 10 Web Sicherheitslücken",
        "Nmap Port Scanning Reconnaissance",
        "Metasploit Framework Grundlagen",
        "Burp Suite Web Testing",
        "Kryptographie Symmetric Asymmetric",
        "PKI Zertifikate RSA",
        "Buffer Overflow Stack Smashing",
        "Privilege Escalation Linux Windows",
        "Incident Response Forensics",
        "SIEM Grundlagen Log Analysis",
    ],
    "wissen_mathematik": [
        "Algebra Gleichungen Ungleichungen",
        "Differentialrechnung Ableitung",
        "Integralrechnung Stammfunktionen",
        "Lineare Algebra Vektoren Matrizen",
        "Matrizenrechnung Determinante",
        "Statistik Deskriptive Kennzahlen",
        "Wahrscheinlichkeitsrechnung Bayes",
        "Diskrete Mathematik Kombinatorik",
        "Graphentheorie Grundlagen",
        "Logik Aussagenlogik Prädikatenlogik",
    ],
    "wissen_physik": [
        "Klassische Mechanik Newton Gesetze",
        "Thermodynamik Hauptsätze",
        "Elektromagnetismus Maxwell",
        "Quantenmechanik Wellenfunktion",
        "Relativitätstheorie Einstein",
        "Optik Wellen Interferenz",
        "Atomphysik Kernphysik Grundlagen",
    ],
    "wissen_chemie": [
        "Organische Chemie Grundlagen",
        "Anorganische Chemie Reaktionen",
        "Periodensystem Elemente Eigenschaften",
        "Molekülbindungen VSEPR Modell",
        "Elektrochemie Redoxreaktionen",
    ],
    "wissen_biologie": [
        "Zellbiologie Organellen Funktionen",
        "Genetik DNA Replikation Transkription",
        "Evolution Natürliche Selektion",
        "Neurobiologie Synapsen Aktionspotenzial",
        "Ökosysteme Biodiversität",
    ],
    "wissen_allgemein": [
        "Philosophie Erkenntnistheorie Grundlagen",
        "Psychologie Kognitive Verzerrungen",
        "Volkswirtschaft Angebot Nachfrage",
        "Geschichte der Informatik Turing",
        "Kommunikation Rhetorik Techniken",
    ],
    "wissen_ernaehrung": [
        "Grundlagen gesunde Ernährung Makronährstoffe",
        "Vitamine Mineralstoffe Mikronährstoffe",
        "Ernährung und Leistungsfähigkeit",
        "Intervallfasten Methoden Wirkung",
        "Vegane Ernährung Nährstoffversorgung",
        "Kohlenhydrate Zucker Glykämischer Index",
        "Proteinreiche Lebensmittel Muskelaufbau",
        "Darmgesundheit Probiotika Prebiotika",
        "Kochen Grundtechniken Küchentipps",
        "Meal Prep Rezepte Meal Planning",
    ],
    "wissen_sport": [
        "Krafttraining Grundlagen Progressive Overload",
        "Muskelaufbau Trainingsplanung Hypertrophie",
        "Cardio HIIT Training Herzrate",
        "Dehnen Mobilität Stretching",
        "Erholung Schlaf Regeneration Sport",
        "Laufen Technik Trainingsplan",
        "Schwimmen Technik Ausdauer",
        "Yoga Grundpositionen Atemübungen",
        "Functional Training Calisthenics",
        "Sport Verletzungen Prävention Physiotherapie",
    ],
    "wissen_musik": [
        "Musiktheorie Noten Intervalle Grundlagen",
        "Akkorde Harmonielehre Tonarten",
        "Rhythmus Takt Metrum",
        "Gitarre Grundlagen Griffbrett Akkorde",
        "Klavier Grundlagen Notenlesen Übungen",
        "Musikproduktion DAW Grundlagen",
        "Mixing Mastering Grundlagen Audio",
        "Musikgeschichte Klassik Romantik",
        "Genres Musikstile Elektronische Musik",
        "Gehörbildung Intervalle Melodien erkennen",
    ],
    "wissen_reisen": [
        "Europa Reiseziele Highlights",
        "Backpacking Tipps Budget Reisen",
        "Weltreise Planung Vorbereitung",
        "Reiseversicherung Tipps",
        "Packen Reiserucksack Checkliste",
        "Sprachbarrieren Reisen Kommunikation",
        "Visum Einreisebestimmungen Grundlagen",
        "Asien Reiseziele Kulturtipps",
        "Nordamerika USA Kanada Reisen",
        "Nachhaltiges Reisen Ökotourismus",
    ],
    "wissen_finanzen": [
        "Persönliche Finanzen Budgetplanung",
        "Sparen Tipps Geld sparen Alltag",
        "Investieren Grundlagen ETF Index Fonds",
        "Aktien Grundlagen Börse Aktienmarkt",
        "Kryptowährung Bitcoin Ethereum Grundlagen",
        "Compound Interest Zinseszins Langzeitsparen",
        "Schweizer Pensionskasse AHV Vorsorge",
        "Steuern Schweiz Grundlagen Steuererklärung",
        "Schulden abbauen Kredit Strategie",
        "Finanzielle Unabhängigkeit FIRE Bewegung",
    ],
    "wissen_recht": [
        "Schweizer Rechtssystem Überblick",
        "Arbeitsrecht Schweiz Grundlagen Kündigung",
        "Mietrecht Schweiz Mieter Vermieter Rechte",
        "Datenschutz DSGVO Schweiz DSG",
        "Urheberrecht Software Open Source Lizenzen",
        "Vertragsrecht Grundlagen Schweiz",
        "Konsumentenschutz Kaufrecht Gewährleistung",
        "Sozialversicherungen Schweiz ALV AHV IV",
        "Strafrecht Grundbegriffe Schweiz",
        "Internetrecht Cyberkriminalität Gesetze",
    ],
    "wissen_psychologie": [
        "Kognitive Verzerrungen Denkfehler",
        "Motivation Theorien Selbstbestimmung",
        "Stressmanagement Burnout Prävention",
        "Emotionale Intelligenz Empathie",
        "Kommunikation Gewaltfreie Kommunikation GFK",
        "Lernpsychologie Gedächtnis Vergessen",
        "Flow Zustand Csikszentmihalyi",
        "Persönlichkeitspsychologie Big Five Modell",
        "Verhaltensökonomie Nudging Entscheidungen",
        "Positiv Psychologie Resilienz Stärken",
    ],
    "wissen_philosophie": [
        "Stoizismus Mark Aurel Epiktet Philosophie",
        "Existenzialismus Sartre Camus Grundlagen",
        "Erkenntnistheorie Wahrheit Platon Kant",
        "Ethik Moral Grundbegriffe",
        "Philosophie des Geistes Bewusstsein",
        "Politische Philosophie Demokratie Gesellschaft",
        "Ostliche Philosophie Buddhismus Taoismus",
        "Wissenschaftsphilosophie Popper Kuhn",
        "Sprachphilosophie Wittgenstein Grundlagen",
        "Metaphysik Ontologie Sein",
    ],
    "wissen_geschichte": [
        "Weltgeschichte Überblick Epochen Zeitalter",
        "Schweizer Geschichte Eidgenossenschaft Gründung",
        "Industrielle Revolution England Europa",
        "Erster Weltkrieg Ursachen Verlauf Folgen",
        "Zweiter Weltkrieg Holocaust NS-Regime",
        "Kalter Krieg USA Sowjetunion Kubakrise",
        "Französische Revolution Aufklärung",
        "Antike Griechenland Rom Grundlagen",
        "Mittelalter Feudalismus Kreuzzüge",
        "Dekolonisierung 20 Jahrhundert Afrika Asien",
        "Geschichte des Internets Digitale Revolution",
        "Geschichte der Demokratie politische Systeme",
    ],
}

# ── Progress bar ──────────────────────────────────────────────────────────────

def progress(done: int, total: int, label: str = "") -> None:
    w = 32
    f = int(w * done / total)
    bar = "█" * f + "░" * (w - f)
    pct = 100 * done // total
    print(f"\r  [{bar}] {pct:3d}% {done}/{total}  {label:<30}", end="", flush=True)


# ── Duplicate check ───────────────────────────────────────────────────────────

def already_known(collection, thema: str) -> bool:
    try:
        existing = collection.get(include=["metadatas"])
        known = {m.get("thema") for m in (existing["metadatas"] or []) if m}
        return thema in known
    except Exception:
        return False


# ── CLI args ──────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description="TENS Autolernmodus")
parser.add_argument("--category", type=str, default="", help="Nur diese Kategorie lernen (z.B. python, sport)")
args = parser.parse_args()

if args.category:
    cat_key = f"wissen_{args.category}" if not args.category.startswith("wissen_") else args.category
    if cat_key not in THEMEN:
        print(f"Kategorie '{args.category}' nicht gefunden. Verfügbar:")
        for k in sorted(THEMEN.keys()):
            print(f"  {k.replace('wissen_', '')}")
        raise SystemExit(1)
    THEMEN = {cat_key: THEMEN[cat_key]}

# ── Main ──────────────────────────────────────────────────────────────────────

total_topics = sum(len(v) for v in THEMEN.values())
print(f"TENS Lernmodus  –  {total_topics} Themen in {len(THEMEN)} Kategorien\n")

done = 0
errors = 0

for kategorie, themen in THEMEN.items():
    col = client.get_or_create_collection(kategorie)
    print(f"\n📁  {kategorie.upper().replace('WISSEN_', '')}  ({len(themen)} Themen)")

    for thema in themen:
        done += 1
        progress(done, total_topics, thema[:30])

        if already_known(col, thema):
            continue

        try:
            with DDGS() as ddgs:
                resultate = list(ddgs.text(thema + " tutorial erklärung", max_results=2))

            for i, r in enumerate(resultate):
                url = r.get("href", "")
                inhalt = lese_webseite(url) if url.startswith("http") else r.get("body", "")

                if len(inhalt) < 80:
                    continue

                doc_id = f"{kategorie}_{thema[:40].replace(' ','_')}_{i}"
                try:
                    col.add(
                        documents=[inhalt[:3000]],
                        ids=[doc_id],
                        metadatas=[{"thema": thema, "kategorie": kategorie, "quelle": url}],
                    )
                except Exception:
                    pass  # already exists

            time.sleep(1.5)
        except Exception as e:
            errors += 1

print(f"\n\n✅  Lernmodus abgeschlossen  –  {done} Themen verarbeitet, {errors} Fehler.")
