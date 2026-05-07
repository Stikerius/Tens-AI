"""
TENS – Learn from AI
Lässt TENS von einem besseren Modell lernen.
Nutzt Ollama (lokales Modell), Claude API oder OpenAI API.

Usage:
  python learn_from_ai.py                     # 20 Runden, lokales Modell
  python learn_from_ai.py --rounds 40         # 40 Runden
  python learn_from_ai.py --model llama3      # anderes Ollama-Modell
  python learn_from_ai.py --api claude        # Claude API (braucht ANTHROPIC_API_KEY in .env)
  python learn_from_ai.py --api openai        # OpenAI API (braucht OPENAI_API_KEY in .env)
"""

import argparse
import os
import time
import random
import chromadb
import requests

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

MEMORY_PATH = "./tens_memory"

# Topics organized by category — these are questions TENS asks the teacher
LERNFRAGEN = {
    "wissen_python": [
        "Erkläre mir detailliert wie Python Decorators funktionieren mit Beispielen",
        "Wie funktionieren Python Context Manager und wann sollte ich sie verwenden?",
        "Erkläre Python's GIL (Global Interpreter Lock) und seine Auswirkungen",
        "Was sind Python Metaclasses und wie werden sie eingesetzt?",
        "Wie funktioniert Python's Garbage Collection und Speicherverwaltung?",
    ],
    "wissen_javascript": [
        "Erkläre das JavaScript Event Loop Modell mit Beispielen",
        "Was sind JavaScript Closures und wie werden sie praktisch eingesetzt?",
        "Wie funktioniert Prototypale Vererbung in JavaScript?",
        "Erkläre den Unterschied zwischen var, let und const in JavaScript",
    ],
    "wissen_ki": [
        "Wie funktioniert der Transformer-Mechanismus mit Attention in LLMs?",
        "Erkläre Retrieval Augmented Generation (RAG) Schritt für Schritt",
        "Was sind Embeddings und wie werden sie in der Vektordatenbank gespeichert?",
        "Erkläre Fine-tuning vs Prompting bei großen Sprachmodellen",
        "Wie funktioniert Backpropagation in Neural Networks?",
    ],
    "wissen_linux": [
        "Erkläre Linux File Permissions chmod, chown mit praktischen Beispielen",
        "Wie funktioniert systemd und wie schreibt man eigene Service Units?",
        "Erkläre Bash Scripting: Variablen, Schleifen, Funktionen und Fehlerbehandlung",
    ],
    "wissen_security": [
        "Erkläre SQL Injection detailliert mit Angriff und Prevention",
        "Wie funktioniert ein XSS-Angriff und wie schützt man sich davor?",
        "Erkläre JWT Tokens: Aufbau, Signierung, und Sicherheitslücken",
        "Was ist das OWASP Top 10 und welche Angriffe sind am häufigsten?",
        "Erkläre Buffer Overflow Exploits und Stack-based Angriffe",
    ],
    "wissen_mathematik": [
        "Erkläre Lineare Algebra: Vektoren, Matrizen und Transformationen visuell",
        "Wie funktioniert Bayes' Theorem mit praktischen Anwendungsbeispielen?",
        "Erkläre Gradient Descent und warum es in ML so wichtig ist",
    ],
    "wissen_ernaehrung": [
        "Erkläre Makronährstoffe: Protein, Kohlenhydrate und Fette und ihre Funktionen",
        "Wie funktioniert Intervallfasten biologisch und welche Varianten gibt es?",
        "Was sind die wichtigsten Vitamine und Mineralstoffe und wo sind sie enthalten?",
    ],
    "wissen_sport": [
        "Erkläre Progressive Overload im Krafttraining und wie man ihn anwendet",
        "Wie funktioniert Muskelwachstum (Hypertrophie) auf zellulärer Ebene?",
        "Was ist die optimale Erholungszeit zwischen Trainingseinheiten?",
    ],
    "wissen_finanzen": [
        "Erkläre ETF-Investing: was sind ETFs, wie funktionieren sie und warum sind sie gut?",
        "Wie funktioniert der Zinseszinseffekt und wie berechnet man ihn?",
        "Was sind die Grundlagen der Schweizer Altersvorsorge AHV, BVG, Säule 3a?",
    ],
    "wissen_psychologie": [
        "Erkläre die wichtigsten kognitiven Verzerrungen (Biases) mit Beispielen",
        "Wie funktioniert Habit-Formation laut neurowissenschaftlicher Forschung?",
        "Was ist Flowzustand und wie erreicht man ihn nach Csikszentmihalyi?",
    ],
}

client = chromadb.PersistentClient(path=MEMORY_PATH)

# ── Teacher API calls ─────────────────────────────────────────────────────────

def ask_ollama(question: str, model: str) -> str:
    try:
        resp = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": question}],
                "stream": False,
            },
            timeout=120,
        )
        data = resp.json()
        return (data.get("message") or {}).get("content", "") or data.get("response", "")
    except Exception as e:
        return f"Fehler: {e}"


def ask_claude(question: str) -> str:
    try:
        import anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return "Fehler: ANTHROPIC_API_KEY nicht gesetzt"
        ac = anthropic.Anthropic(api_key=api_key)
        msg = ac.messages.create(
            model="claude-opus-4-7",
            max_tokens=2000,
            messages=[{"role": "user", "content": question}],
        )
        return msg.content[0].text
    except ImportError:
        return "Fehler: anthropic Paket nicht installiert (pip install anthropic)"
    except Exception as e:
        return f"Fehler: {e}"


def ask_openai(question: str) -> str:
    try:
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return "Fehler: OPENAI_API_KEY nicht gesetzt"
        oa = OpenAI(api_key=api_key)
        resp = oa.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": question}],
            max_tokens=2000,
        )
        return resp.choices[0].message.content
    except ImportError:
        return "Fehler: openai Paket nicht installiert (pip install openai)"
    except Exception as e:
        return f"Fehler: {e}"


def ask_teacher(question: str, api: str, model: str) -> str:
    if api == "claude":
        return ask_claude(question)
    if api == "openai":
        return ask_openai(question)
    return ask_ollama(question, model)


# ── Store learning in ChromaDB ────────────────────────────────────────────────

def store_answer(collection_name: str, question: str, answer: str, api: str):
    if len(answer) < 50 or answer.startswith("Fehler:"):
        return False
    col = client.get_or_create_collection(collection_name)
    doc_id = f"learnai_{collection_name}_{question[:40].replace(' ','_')}_{int(time.time())}"
    # Format as FAKT/SKILL for consistent brain display
    formatted = f"FAKT: Gelernt von {api}-Modell\nFRAGE: {question}\n\nANTWORT:\n{answer[:3000]}"
    try:
        col.add(
            documents=[formatted],
            ids=[doc_id],
            metadatas=[{"quelle": f"teacher:{api}", "thema": question[:60], "typ": "learn_from_ai"}],
        )
        return True
    except Exception:
        try:
            col.update(documents=[formatted], ids=[doc_id],
                       metadatas=[{"quelle": f"teacher:{api}", "thema": question[:60], "typ": "learn_from_ai"}])
            return True
        except Exception:
            return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="TENS lernt von einem Teacher-Modell")
    parser.add_argument("--rounds",  type=int, default=20,       help="Anzahl Lernrunden (default: 20)")
    parser.add_argument("--model",   type=str, default="mistral", help="Ollama-Modell (default: mistral)")
    parser.add_argument("--api",     type=str, default="ollama",  help="API: ollama | claude | openai")
    parser.add_argument("--category",type=str, default="",        help="Nur diese Kategorie (z.B. python)")
    args = parser.parse_args()

    api   = args.api.lower()
    model = args.model
    rounds = args.rounds

    # Collect all questions
    all_questions = []
    for cat, questions in LERNFRAGEN.items():
        if args.category:
            cat_key = f"wissen_{args.category}" if not args.category.startswith("wissen_") else args.category
            if cat != cat_key:
                continue
        for q in questions:
            all_questions.append((cat, q))

    if not all_questions:
        print(f"Keine Fragen für Kategorie '{args.category}' gefunden.")
        return

    random.shuffle(all_questions)
    selected = all_questions[:rounds]

    print(f"\n{'═'*56}")
    print(f"  TENS – Lernen von AI")
    print(f"  Teacher: {api.upper()} {'(' + model + ')' if api == 'ollama' else ''}")
    print(f"  Runden:  {len(selected)}")
    print(f"{'═'*56}\n")

    success = 0
    errors  = 0

    for i, (cat, question) in enumerate(selected, 1):
        short = question[:50] + ("…" if len(question) > 50 else "")
        bar_w = 30
        filled = int(bar_w * i / len(selected))
        bar = "█" * filled + "░" * (bar_w - filled)
        print(f"\r  [{bar}] {i}/{len(selected)}  {short:<52}", end="", flush=True)

        answer = ask_teacher(question, api, model)
        if answer.startswith("Fehler:"):
            print(f"\n  ✗ {answer}")
            errors += 1
        else:
            ok = store_answer(cat, question, answer, api)
            if ok:
                success += 1
            else:
                errors += 1

        # Delay to avoid rate limits
        if api in ("claude", "openai"):
            time.sleep(1.0)
        else:
            time.sleep(0.5)

    print(f"\n\n{'═'*56}")
    print(f"  Fertig: {success} gelernt, {errors} Fehler")
    print(f"{'═'*56}\n")


if __name__ == "__main__":
    main()
