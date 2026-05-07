from fastapi import FastAPI, Query, File, UploadFile, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, Response
from pydantic import BaseModel
from typing import Optional
import chromadb
import json
import os
import re
import threading
import tempfile
import pathlib
import requests as http
from collections import Counter
from datetime import datetime, timedelta
import hashlib

# ── Optional auth deps ────────────────────────────────────────────────────────
try:
    from jose import jwt as _jwt, JWTError
    HAS_JOSE = True
except ImportError:
    HAS_JOSE = False

try:
    import bcrypt as _bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="TENS Brain API", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PROFIL_FILE  = "./nutzer_profil.json"
MEMORY_PATH  = "./tens_memory"
USERS_FILE   = "./users.json"
USERS_DIR    = "./users"
SECRET_KEY   = os.environ.get("TENS_SECRET", "tens-neural-secret-2024")
TOKEN_EXPIRE = timedelta(days=30)
_HERE        = pathlib.Path(__file__).parent

# ── ChromaDB singleton ────────────────────────────────────────────────────────
_chroma_client: Optional[chromadb.PersistentClient] = None

def get_chroma() -> chromadb.PersistentClient:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=MEMORY_PATH)
    return _chroma_client

# ── Password / JWT helpers ────────────────────────────────────────────────────
def hash_password(pw: str) -> str:
    if HAS_BCRYPT:
        return _bcrypt.hashpw(pw.encode(), _bcrypt.gensalt()).decode()
    return hashlib.sha256(pw.encode()).hexdigest()

def verify_password(pw: str, hashed: str) -> bool:
    if HAS_BCRYPT and hashed.startswith("$2"):
        try:
            return _bcrypt.checkpw(pw.encode(), hashed.encode())
        except Exception:
            return False
    return hashlib.sha256(pw.encode()).hexdigest() == hashed

def create_token(user_id: str, role: str) -> str:
    payload = {"sub": user_id, "role": role}
    if HAS_JOSE:
        payload["exp"] = datetime.utcnow() + TOKEN_EXPIRE
        return _jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    import base64
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()

def decode_token(token: str) -> dict:
    try:
        if HAS_JOSE:
            return _jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        import base64
        return json.loads(base64.urlsafe_b64decode(token.encode() + b"==").decode())
    except Exception:
        return {}

# ── User management ───────────────────────────────────────────────────────────
def load_users() -> list:
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []

def save_users(users: list):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

def find_user(uid: str) -> Optional[dict]:
    return next((u for u in load_users() if u["id"] == uid), None)

def get_profil_file(user_id: str) -> str:
    if user_id == "ivan":
        return PROFIL_FILE
    p = f"{USERS_DIR}/{user_id}"
    os.makedirs(p, exist_ok=True)
    return f"{p}/profil.json"

def get_conv_col_name(user_id: str) -> str:
    return "gespraeche" if user_id == "ivan" else f"gespraeche_{user_id}"

def get_current_user(authorization: Optional[str]) -> Optional[dict]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    payload = decode_token(authorization[7:])
    uid = payload.get("sub")
    return find_user(uid) if uid else None

# ── Startup ───────────────────────────────────────────────────────────────────
def _initialize():
    os.makedirs(USERS_DIR, exist_ok=True)
    users = load_users()
    if not any(u["id"] == "ivan" for u in users):
        users.append({
            "id": "ivan",
            "name": "Ivan",
            "password_hash": hash_password("tens2024"),
            "role": "admin",
            "created": datetime.now().isoformat(),
        })
        save_users(users)
        print("  ✓ Admin-Account erstellt: username=ivan  password=tens2024")

    print()
    print("╔═══════════════════════════════════════════════════╗")
    print("║          TENS Brain API – bereit                 ║")
    print("╠═══════════════════════════════════════════════════╣")
    print("║  Chat:   http://localhost:8000/                  ║")
    print("║  Brain:  http://localhost:8000/brain-view        ║")
    print("║  Admin:  http://localhost:8000/admin             ║")
    print("║  Docs:   http://localhost:8000/docs              ║")
    print("╚═══════════════════════════════════════════════════╝")
    print()

_initialize()

# ── Ollama helper ─────────────────────────────────────────────────────────────
def _ollama(messages: list, timeout: int = 60) -> str:
    last = "LLM nicht erreichbar."
    for opts in [{}, {"num_gpu": 0}]:
        try:
            resp = http.post(
                "http://localhost:11434/api/chat",
                json={"model": "dolphin-mistral", "messages": messages, "stream": False, "options": opts},
                timeout=timeout,
            )
            data = resp.json()
            if "message" in data:
                return data["message"]["content"]
            if "response" in data:
                return data["response"]
            err = data.get("error", str(data))
            if "cuda" in err.lower() or "terminated" in err.lower():
                last = err
                continue
            return f"Ollama-Fehler: {err}"
        except Exception as e:
            last = str(e)
    return f"LLM-Fehler: {last}"

def _ollama_stream(messages: list):
    """Sync generator yielding tokens from Ollama streaming API."""
    try:
        resp = http.post(
            "http://localhost:11434/api/chat",
            json={"model": "dolphin-mistral", "messages": messages, "stream": True},
            stream=True,
            timeout=120,
        )
        for line in resp.iter_lines():
            if not line:
                continue
            try:
                data = json.loads(line)
                token = (data.get("message") or {}).get("content", "")
                if token:
                    yield token
                if data.get("done"):
                    return
            except Exception:
                continue
    except Exception as e:
        yield f"\n[Fehler: {e}]"

# ── Fact extraction (background) ──────────────────────────────────────────────
_ALLOWED_KEYS = {"name", "alter", "geburtstag", "wohnort", "beruf", "hobbys", "interessen", "sprache"}
_FAKE_NAMES   = {"user", "nutzer", "du", "ich", "assistant", "assistent"}

def _extrahiere_fakten(user_msg: str, tens_msg: str, profil_file: str):
    try:
        raw = _ollama([{"role": "user", "content": (
            f"Analysiere dieses Gespräch und extrahiere persönliche Fakten über den Nutzer.\n\n"
            f"Nutzer: {user_msg}\nAssistent: {tens_msg}\n\n"
            f"Erlaubte Keys NUR: name, alter, geburtstag, wohnort, beruf, hobbys, interessen, sprache\n"
            f"Wenn nichts Persönliches gesagt wurde: {{}}\n"
            f"Antworte NUR mit JSON."
        )}], timeout=20).strip()
        m = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
        if not m:
            return
        fakten = json.loads(m.group())
        fakten = {k: v for k, v in fakten.items() if k in _ALLOWED_KEYS and v}
        if "name" in fakten and str(fakten["name"]).lower() in _FAKE_NAMES:
            del fakten["name"]
        if fakten:
            profil = {}
            if os.path.exists(profil_file):
                with open(profil_file, "r", encoding="utf-8") as f:
                    profil = json.load(f)
            profil.update(fakten)
            d = os.path.dirname(profil_file)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(profil_file, "w", encoding="utf-8") as f:
                json.dump(profil, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def _save_conversation(user_msg: str, tens_msg: str, user: Optional[dict]):
    try:
        chroma = get_chroma()
        col_name = get_conv_col_name(user["id"]) if user else "gespraeche"
        gcol = chroma.get_or_create_collection(col_name)
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        gcol.add(
            documents=[f"Nutzer: {user_msg}\nTENS: {tens_msg}"],
            ids=[ts],
        )
    except Exception:
        pass

def _build_chat_messages(req, user: Optional[dict]) -> tuple:
    chroma = get_chroma()
    profil_file = get_profil_file(user["id"]) if user else PROFIL_FILE
    profil = {}
    if os.path.exists(profil_file):
        try:
            with open(profil_file, "r", encoding="utf-8") as f:
                profil = json.load(f)
        except Exception:
            pass
    profil_text = "\n".join(f"{k}: {v}" for k, v in profil.items()) if profil else "Noch nichts bekannt."

    resultate, cols_searched = [], []
    for col in chroma.list_collections():
        try:
            r = chroma.get_collection(col.name).query(query_texts=[req.message], n_results=2)
            if r["documents"][0]:
                resultate.extend(r["documents"][0])
                cols_searched.append(col.name)
        except Exception:
            pass
    kontext = "\n\n".join(resultate[:5])

    system = (
        f"Du bist TENS, ein persönlicher KI-Assistent.\n"
        f"WICHTIG: Antworte IMMER auf Deutsch. Niemals auf Englisch.\n"
        f"Rede den Nutzer mit 'du' an. Sei direkt, klar und hilfreich – keine Floskeln.\n"
        f"Spezialisiert auf Programmierung, Cybersecurity und Technik.\n"
        f"Heute: {datetime.now().strftime('%d.%m.%Y')}\n\n"
        f"Was du über den Nutzer weißt:\n{profil_text}\n\n"
        f"Relevantes Wissen:\n{kontext if kontext else 'Keins gespeichert.'}"
    )
    messages = (
        [{"role": "system", "content": system}]
        + req.history[-10:]
        + [{"role": "user", "content": req.message}]
    )
    return messages, cols_searched, profil_file

# ── Markdown strip helper ─────────────────────────────────────────────────────
def strip_markdown(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'`[^`]+`', '', text)
    text = re.sub(r'#{1,6}\s', '', text)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    return text.strip()

# ── File text extraction ──────────────────────────────────────────────────────
_TEXT_EXTS = {
    ".txt", ".py", ".js", ".ts", ".html", ".css", ".md", ".sh",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".rs", ".go",
    ".java", ".c", ".cpp", ".h", ".xml", ".sql",
}

def _extract_text(path: str, suffix: str) -> str:
    p = pathlib.Path(path)
    if suffix in _TEXT_EXTS or suffix == ".json":
        return p.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".csv":
        try:
            import pandas as pd
            df = pd.read_csv(p)
            return df.to_string()
        except Exception:
            return p.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        for importer in ["pypdf", "PyPDF2"]:
            try:
                if importer == "pypdf":
                    from pypdf import PdfReader
                    return "\n".join(pg.extract_text() or "" for pg in PdfReader(path).pages)
                else:
                    import PyPDF2
                    with open(path, "rb") as f:
                        reader = PyPDF2.PdfReader(f)
                        return "\n".join(pg.extract_text() or "" for pg in reader.pages)
            except Exception:
                continue
    if suffix == ".docx":
        try:
            from docx import Document
            doc = Document(path)
            return "\n".join(par.text for par in doc.paragraphs if par.text.strip())
        except Exception:
            pass
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

# ── Topic classifier ──────────────────────────────────────────────────────────
_TOPIC_KW = {
    "wissen_python":     ["python", "pip", "pandas", "numpy", "pytorch", "flask", "django", "fastapi"],
    "wissen_javascript": ["javascript", " js ", "node.js", "react", "vue", "typescript", "npm"],
    "wissen_html":       ["html", " css ", "dom ", "browser", "frontend", "tailwind"],
    "wissen_linux":      ["linux", "bash", "shell", "ubuntu", "systemctl", "chmod", "unix"],
    "wissen_docker":     ["docker", "container", "kubernetes", "dockerfile"],
    "wissen_security":   ["hack", "exploit", "pentest", "xss", "sql injection", "nmap", "burp"],
    "wissen_ki":         ["machine learning", "deep learning", "neural", "llm", "transformer"],
    "wissen_mathematik": ["mathematik", "mathe", "algebra", "integral", "statistik"],
    "wissen_ernaehrung": ["ernährung", "nahrung", "protein", "kalorien", "vitamine", "kochen", "rezept"],
    "wissen_sport":      ["sport", "training", "fitness", "muskel", "ausdauer", "laufen", "gym"],
    "wissen_finanzen":   ["finanzen", "budget", "aktie", "etf", "investieren", "steuern", "sparplan"],
    "wissen_psychologie":["psychologie", "stress", "motivation", "habit", "verhalten", "emotion"],
    "wissen_musik":      ["musik", "akkord", "melodie", "gitarre", "klavier", "daw", "produzieren"],
    "wissen_reisen":     ["reisen", "backpack", "visum", "hotel", "flug", "tourismus", "urlaub"],
    "wissen_recht":      ["recht", "gesetz", "datenschutz", "dsgvo", "kündigung", "mietrecht"],
    "wissen_philosophie":["philosophie", "ethik", "logik", "stoik", "erkenntnistheorie", "moral"],
    "wissen_geschichte": ["geschichte", "historisch", "revolution", "weltkrieg", "mittelalter"],
}

def _classify(name: str, text: str) -> str:
    combined = (name + " " + text[:2000]).lower()
    best, best_score = "wissen_allgemein", 0
    for col, kws in _TOPIC_KW.items():
        score = sum(1 for kw in kws if kw in combined)
        if score > best_score:
            best_score, best = score, col
    return best

# ── Collection category mapping ───────────────────────────────────────────────
COLLECTION_CATEGORY = {
    "wissen_python":      "technologie",
    "wissen_javascript":  "technologie",
    "wissen_html":        "technologie",
    "wissen_css":         "technologie",
    "wissen_linux":       "technologie",
    "wissen_docker":      "technologie",
    "wissen_git":         "technologie",
    "wissen_sql":         "technologie",
    "wissen_algorithmen": "technologie",
    "wissen_allgemein":   "technologie",
    "wissen_ki":          "wissenschaft",
    "wissen_mathematik":  "wissenschaft",
    "wissen_physik":      "wissenschaft",
    "wissen_chemie":      "wissenschaft",
    "wissen_biologie":    "wissenschaft",
    "wissen_astronomie":  "wissenschaft",
    "wissen_security":    "security",
    "wissen_ernaehrung":  "gesundheit",
    "wissen_sport":       "gesundheit",
    "wissen_psychologie": "gesellschaft",
    "wissen_finanzen":    "gesellschaft",
    "wissen_philosophie": "gesellschaft",
    "wissen_recht":       "gesellschaft",
    "wissen_geschichte":  "gesellschaft",
    "wissen_musik":       "kultur",
    "wissen_reisen":      "kultur",
}

def collection_to_category(col_name: str) -> str:
    if col_name in COLLECTION_CATEGORY:
        return COLLECTION_CATEGORY[col_name]
    if col_name.startswith("wissen_"):
        n = col_name[7:]
        if any(k in n for k in ["physik", "chemie", "biologie", "mathematik", "ki", "wissenschaft"]):
            return "wissenschaft"
        if any(k in n for k in ["ernaehrung", "sport", "gesundheit"]):
            return "gesundheit"
        if any(k in n for k in ["psychologie", "finanzen", "philosophie", "recht", "geschichte"]):
            return "gesellschaft"
        if any(k in n for k in ["musik", "reisen", "kultur"]):
            return "kultur"
        if any(k in n for k in ["security", "hack", "pentest", "ctf"]):
            return "security"
        return "technologie"
    return "kern"

def collection_display_name(col_name: str) -> str:
    if col_name.startswith("wissen_"):
        return col_name[7:].replace("_", " ").title()
    if col_name == "gespraeche" or col_name.startswith("gespraeche_"):
        return "Gespräche"
    return col_name.replace("_", " ").title()

STOP_WORDS = {
    "der", "die", "das", "und", "ist", "in", "zu", "den", "mit", "ein", "eine",
    "sich", "von", "an", "auf", "für", "als", "es", "bei", "hat", "wird", "sind",
    "war", "er", "sie", "wir", "ich", "du", "man", "so", "wie", "aber", "nicht",
    "nach", "aus", "über", "wenn", "kann", "dass", "haben", "werden", "nutzer",
    "tens", "the", "and", "for", "are", "with", "has", "was", "from", "have",
    "been", "will", "you", "our", "new", "one", "about", "also", "into", "fakt",
    "skill", "dieser", "diese", "sehr", "immer", "noch", "bereits", "lerne",
}

def extract_key_phrases(documents: list, max_phrases: int = 6) -> list:
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

# ── Pydantic models ───────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    history: list = []

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    name: str
    password: str

class SpeakRequest(BaseModel):
    text: str

# ── Static file routes ────────────────────────────────────────────────────────
@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)

@app.get("/")
def serve_chat():
    return FileResponse(_HERE / "web_ui.html")

@app.get("/brain-view")
def serve_brain():
    return FileResponse(_HERE / "tens_brain.html")

@app.get("/admin")
def serve_admin():
    f = _HERE / "admin.html"
    if f.exists():
        return FileResponse(f)
    return Response(content="<h1>admin.html not found</h1>", media_type="text/html")

@app.get("/d3.min.js")
def serve_d3():
    return FileResponse(_HERE / "d3.min.js", media_type="application/javascript")

# ── Auth endpoints ────────────────────────────────────────────────────────────
@app.post("/auth/login")
def auth_login(req: LoginRequest):
    user = find_user(req.username)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Ungültige Anmeldedaten")
    token = create_token(user["id"], user.get("role", "user"))
    return {"token": token, "user_id": user["id"], "name": user["name"], "role": user.get("role", "user")}

@app.post("/auth/register")
def auth_register(req: RegisterRequest, authorization: Optional[str] = Header(None)):
    admin = get_current_user(authorization)
    if not admin or admin.get("role") != "admin":
        raise HTTPException(403, "Nur für Admins")
    users = load_users()
    if any(u["id"] == req.username for u in users):
        raise HTTPException(400, "Benutzername bereits vergeben")
    users.append({
        "id": req.username,
        "name": req.name,
        "password_hash": hash_password(req.password),
        "role": "user",
        "created": datetime.now().isoformat(),
    })
    save_users(users)
    return {"ok": True, "user_id": req.username}

@app.get("/me")
def me(authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    if not user:
        raise HTTPException(401, "Nicht angemeldet")
    profil = {}
    pf = get_profil_file(user["id"])
    if os.path.exists(pf):
        try:
            with open(pf, "r", encoding="utf-8") as f:
                profil = json.load(f)
        except Exception:
            pass
    return {"id": user["id"], "name": user["name"], "role": user.get("role", "user"), "profil": profil}

# ── Admin endpoints ───────────────────────────────────────────────────────────
def _require_admin(authorization: Optional[str]):
    user = get_current_user(authorization)
    if not user or user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    return user

@app.get("/admin/users")
def admin_users(authorization: Optional[str] = Header(None)):
    _require_admin(authorization)
    chroma = get_chroma()
    result = []
    for u in load_users():
        msg_count = 0
        try:
            col = chroma.get_collection(get_conv_col_name(u["id"]))
            msg_count = col.count()
        except Exception:
            pass
        result.append({
            "id": u["id"],
            "name": u["name"],
            "role": u.get("role", "user"),
            "created": u.get("created"),
            "message_count": msg_count,
        })
    return result

@app.get("/admin/user/{user_id}")
def admin_user(user_id: str, authorization: Optional[str] = Header(None)):
    _require_admin(authorization)
    user = find_user(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    pf = get_profil_file(user_id)
    profil = {}
    if os.path.exists(pf):
        try:
            with open(pf, "r", encoding="utf-8") as f:
                profil = json.load(f)
        except Exception:
            pass
    return {"user": user, "profil": profil}

@app.delete("/admin/user/{user_id}")
def admin_delete_user(user_id: str, authorization: Optional[str] = Header(None)):
    _require_admin(authorization)
    if user_id == "ivan":
        raise HTTPException(400, "Admin kann nicht gelöscht werden")
    users = load_users()
    users = [u for u in users if u["id"] != user_id]
    save_users(users)
    return {"ok": True}

@app.get("/admin/stats")
def admin_stats(authorization: Optional[str] = Header(None)):
    _require_admin(authorization)
    chroma = get_chroma()
    cols = chroma.list_collections()
    total_entries = 0
    total_convs = 0
    knowledge_cols = 0
    for c in cols:
        try:
            count = chroma.get_collection(c.name).count()
            total_entries += count
            if c.name.startswith("wissen_"):
                knowledge_cols += 1
            if c.name.startswith("gespraeche"):
                total_convs += count
        except Exception:
            pass
    return {
        "total_entries": total_entries,
        "total_conversations": total_convs,
        "knowledge_collections": knowledge_cols,
        "total_collections": len(cols),
        "total_users": len(load_users()),
    }

# ── /reset endpoint ───────────────────────────────────────────────────────────
@app.post("/reset")
def reset_memory(authorization: Optional[str] = Header(None)):
    _require_admin(authorization)
    chroma = get_chroma()
    deleted = []
    for col in chroma.list_collections():
        chroma.delete_collection(col.name)
        deleted.append(col.name)
    if os.path.exists(PROFIL_FILE):
        with open(PROFIL_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
    return {"ok": True, "deleted_collections": deleted}

# ── /speak endpoint (edge-tts) ────────────────────────────────────────────────
@app.post("/speak")
async def speak(req: SpeakRequest):
    try:
        import edge_tts
    except ImportError:
        return Response(status_code=503, content=b"edge-tts nicht installiert: pip install edge-tts")

    clean = strip_markdown(req.text)[:800]
    if not clean.strip():
        return Response(status_code=204)

    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()
    try:
        communicate = edge_tts.Communicate(clean, "de-DE-KatjaNeural")
        await communicate.save(tmp.name)
        with open(tmp.name, "rb") as f:
            audio_data = f.read()
        return Response(content=audio_data, media_type="audio/mpeg")
    except Exception as e:
        return Response(status_code=500, content=str(e).encode())
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass

# ── /extract-text endpoint ────────────────────────────────────────────────────
@app.post("/extract-text")
async def extract_text_endpoint(file: UploadFile = File(...)):
    suffix = pathlib.Path(file.filename or "unknown.bin").suffix.lower()
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(await file.read())
        tmp.close()
        text = _extract_text(tmp.name, suffix)
        return {"text": text[:8000], "filename": file.filename}
    except Exception as e:
        return {"text": "", "filename": file.filename, "error": str(e)}
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass

# ── /transcribe endpoint ──────────────────────────────────────────────────────
_whisper_model = None

@app.post("/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    global _whisper_model
    try:
        import whisper as _whisper_lib
        import numpy as np
    except ImportError:
        return {"text": "", "error": "Whisper nicht installiert: pip install openai-whisper"}
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    try:
        tmp.write(await audio.read())
        tmp.close()
        import wave
        with wave.open(tmp.name, "rb") as wf:
            n_ch = wf.getnchannels(); sr = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
        audio_np = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        if n_ch > 1:
            audio_np = audio_np.reshape(-1, n_ch).mean(axis=1)
        if sr != 16000 and len(audio_np) > 0:
            target = int(len(audio_np) * 16000 / sr)
            audio_np = np.interp(np.linspace(0, len(audio_np), target), np.arange(len(audio_np)), audio_np).astype(np.float32)
        if _whisper_model is None:
            _whisper_model = _whisper_lib.load_model("base")
        result = _whisper_model.transcribe(audio_np, language="de", fp16=False)
        return {"text": (result.get("text") or "").strip()}
    except Exception as e:
        return {"text": "", "error": str(e)}
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass

# ── /upload endpoint ──────────────────────────────────────────────────────────
@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    suffix = pathlib.Path(file.filename or "unknown.txt").suffix.lower()
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(await file.read())
        tmp.close()
        text = _extract_text(tmp.name, suffix)
        if len(text.strip()) < 2:
            return {"ok": False, "error": "Datei ist leer."}
        wissen = _ollama([{"role": "user", "content": (
            f"Lies diesen Text und extrahiere strukturiertes Wissen auf Deutsch.\n\n"
            f"Text: {text[:3000]}\n\nFormat:\nFAKT: [...]\nSKILL: [...]\n\nNur explizit Genanntes."
        )}])
        col_name = _classify(file.filename or "", text)
        chroma = get_chroma()
        col = chroma.get_or_create_collection(col_name)
        doc_id = f"upload_{file.filename}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        col.add(documents=[wissen], ids=[doc_id], metadatas=[{"quelle": file.filename, "typ": "upload"}])
        preview = wissen[:300] + ("…" if len(wissen) > 300 else "")
        return {"ok": True, "collection": col_name, "doc_id": doc_id, "preview": preview}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass

# ── /chat endpoint ────────────────────────────────────────────────────────────
@app.post("/chat")
def chat_endpoint(req: ChatRequest, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    messages, cols_searched, profil_file = _build_chat_messages(req, user)
    reply = _ollama(messages)

    _save_conversation(req.message, reply, user)
    threading.Thread(
        target=_extrahiere_fakten,
        args=(req.message, reply, profil_file),
        daemon=True,
    ).start()

    profil = {}
    if os.path.exists(profil_file):
        try:
            with open(profil_file, "r", encoding="utf-8") as f:
                profil = json.load(f)
        except Exception:
            pass

    return {"reply": reply, "collections_searched": cols_searched, "facts_used": profil}

# ── /chat/stream endpoint ─────────────────────────────────────────────────────
@app.post("/chat/stream")
def chat_stream_endpoint(req: ChatRequest, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    messages, cols_searched, profil_file = _build_chat_messages(req, user)

    def generate():
        full_reply = []
        for token in _ollama_stream(messages):
            full_reply.append(token)
            yield f"data: {json.dumps({'token': token})}\n\n"
        reply_text = "".join(full_reply)
        if reply_text:
            _save_conversation(req.message, reply_text, user)
            threading.Thread(
                target=_extrahiere_fakten,
                args=(req.message, reply_text, profil_file),
                daemon=True,
            ).start()
        yield f"data: {json.dumps({'done': True, 'full': reply_text, 'collections_searched': cols_searched})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )

# ── /brain endpoint ───────────────────────────────────────────────────────────
@app.get("/brain")
def get_brain():
    chroma = get_chroma()
    all_cols = chroma.list_collections()
    col_names = {c.name for c in all_cols}

    nodes = [{
        "id": "tens-core", "label": "TENS", "cat": "kern", "entries": 1,
        "facts": ["Persönlicher KI-Assistent", "Dolphin-Mistral via Ollama", "Lokales Wissensnetz"],
        "_type": "core",
    }]
    links = []
    total_entries = 0

    for col in sorted(all_cols, key=lambda c: c.name):
        if not col.name.startswith("wissen_"):
            continue
        try:
            wissen_col = chroma.get_collection(col.name)
            data = wissen_col.get(include=["documents", "metadatas"])
            docs = data["documents"] or []
            ids = data["ids"] or []
            count = len(docs)
            total_entries += count
            cat = collection_to_category(col.name)
            display = collection_display_name(col.name)
            node_id = f"col-{col.name}"
            phrases = extract_key_phrases(docs, max_phrases=5)
            facts = phrases if phrases else [f"{count} Einträge gespeichert"]
            nodes.append({
                "id": node_id, "label": display, "cat": cat,
                "entries": max(count, 1), "facts": facts,
                "_type": "collection", "_collection": col.name,
            })
            links.append({"source": "tens-core", "target": node_id})
            sources_seen: dict = {}
            for i, (doc_id, doc) in enumerate(zip(ids, docs)):
                if len(sources_seen) >= 4:
                    break
                label = url_to_topic(doc_id) if doc_id.startswith("http") else doc_id[:20].replace("_", " ").title()
                if label in sources_seen:
                    continue
                sources_seen[label] = True
                sub_id = f"sub-{col.name}-{i}"
                sub_facts = [l.strip()[5:].strip() for l in doc.split("\n") if l.strip().startswith("FAKT:")][:3]
                if not sub_facts:
                    sub_facts = [f"Quelle: {label}"]
                nodes.append({
                    "id": sub_id, "label": label[:18], "cat": cat,
                    "entries": 1, "facts": sub_facts,
                    "_type": "document", "_collection": col.name, "_doc_id": doc_id,
                })
                links.append({"source": node_id, "target": sub_id})
        except Exception:
            pass

    # Conversations (all gespraeche* collections)
    for col in all_cols:
        if not (col.name == "gespraeche" or col.name.startswith("gespraeche_")):
            continue
        try:
            gcol = chroma.get_collection(col.name)
            data = gcol.get(include=["documents", "metadatas"])
            docs = data["documents"] or []
            metas = data["metadatas"] or []
            total_entries += len(docs)
            conv_docs = [d for d, m in zip(docs, metas) if not (m and m.get("typ") == "wissen")]
            phrases = extract_key_phrases(conv_docs or docs, max_phrases=6)
            facts = phrases if phrases else ["Gesprächsverlauf mit TENS"]
            node_id = f"col-{col.name}"
            display = collection_display_name(col.name)
            nodes.append({
                "id": node_id, "label": display, "cat": "kern",
                "entries": max(len(conv_docs), 1), "facts": facts,
                "_type": "collection", "_collection": col.name,
            })
            links.append({"source": "tens-core", "target": node_id})
        except Exception:
            pass

    # Profile
    if os.path.exists(PROFIL_FILE):
        try:
            with open(PROFIL_FILE, "r", encoding="utf-8") as f:
                profil = json.load(f)
            if profil:
                name = profil.get("name", "Nutzer")
                person_id = "personal-" + re.sub(r"\W+", "", name.lower())
                nodes.append({
                    "id": person_id, "label": name.upper(), "cat": "persoenlich",
                    "entries": max(len(profil) * 2, 2),
                    "facts": [f"{k}: {v}" for k, v in profil.items() if v][:6],
                    "_type": "profile_all",
                })
                links.append({"source": "tens-core", "target": person_id})
                for key, val in profil.items():
                    if not val:
                        continue
                    fact_id = f"fact-{key}"
                    label = key.capitalize()
                    nodes.append({
                        "id": fact_id, "label": label, "cat": "persoenlich",
                        "entries": 1, "facts": [str(val)], "_type": "profile_key", "_key": key,
                    })
                    links.append({"source": person_id, "target": fact_id})
        except Exception:
            pass

    return {"nodes": nodes, "links": links, "meta": {"total_entries": total_entries, "updated": datetime.now().isoformat()}}

# ── DELETE /brain/node ────────────────────────────────────────────────────────
@app.delete("/brain/node")
def delete_node(
    type: str = Query(...),
    collection: Optional[str] = Query(None),
    doc_id: Optional[str] = Query(None),
    key: Optional[str] = Query(None),
):
    chroma = get_chroma()
    if type == "collection" and collection:
        try:
            chroma.delete_collection(collection)
            return {"ok": True, "deleted": f"collection:{collection}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    if type == "document" and collection and doc_id:
        try:
            chroma.get_collection(collection).delete(ids=[doc_id])
            return {"ok": True, "deleted": f"doc:{doc_id}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    if type == "profile_key" and key:
        try:
            if not os.path.exists(PROFIL_FILE):
                return {"ok": False, "error": "Profil nicht gefunden"}
            with open(PROFIL_FILE, "r", encoding="utf-8") as f:
                profil = json.load(f)
            profil.pop(key, None)
            with open(PROFIL_FILE, "w", encoding="utf-8") as f:
                json.dump(profil, f, indent=2, ensure_ascii=False)
            return {"ok": True, "deleted": f"profile:{key}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    if type == "profile_all":
        try:
            with open(PROFIL_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=2)
            return {"ok": True, "deleted": "profile_all"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "Unbekannter Typ oder fehlende Parameter"}

# ── /history endpoint ─────────────────────────────────────────────────────────
@app.get("/history")
def get_history(limit: int = 100, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    col_name = get_conv_col_name(user["id"]) if user else "gespraeche"
    try:
        chroma = get_chroma()
        col    = chroma.get_collection(col_name)
        data   = col.get(include=["documents"])
        pairs  = list(zip(data["ids"] or [], data["documents"] or []))
        pairs.sort(key=lambda x: x[0], reverse=True)
        result = []
        for doc_id, doc in pairs[:limit]:
            # Format: "Nutzer: ...\nTENS: ..."
            parts     = doc.split("\nTENS: ", 1)
            user_msg  = parts[0].removeprefix("Nutzer: ")
            tens_msg  = parts[1] if len(parts) > 1 else ""
            ts_str    = doc_id[:14]
            try:
                dt        = datetime.strptime(ts_str, "%Y%m%d%H%M%S")
                timestamp = dt.isoformat()
            except Exception:
                timestamp = doc_id
            result.append({
                "id":        doc_id,
                "timestamp": timestamp,
                "user":      user_msg,
                "tens":      tens_msg,
            })
        return result
    except Exception:
        return []


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
