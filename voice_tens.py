"""
TENS Sprachmodus – Spracheingabe via Whisper + Sprachausgabe via pyttsx3.

Verwendung:
  python voice_tens.py              # normaler Modus
  python voice_tens.py --wake       # Wake-Word "hey tens" aktivieren
"""

import os
import re
import sys
import wave
import tempfile
import threading

import pyttsx3

try:
    import pyaudio
    AUDIO_OK = True
except ImportError:
    AUDIO_OK = False
    print("  ▸ PyAudio nicht installiert: pip install pyaudio")

try:
    import whisper as _whisper
    WHISPER_OK = True
except ImportError:
    WHISPER_OK = False
    print("  ▸ Whisper nicht installiert: pip install openai-whisper")

# Import TENS logic (main loop is guarded by __name__ == "__main__")
from tens import chat, verarbeite_zu_wissen, braucht_suche, extrahiere_mathe, safe_eval
from scraper import suche_und_lerne

# ── TTS ───────────────────────────────────────────────────────────────────────

_engine = pyttsx3.init()
_voice_enabled = True


def _setup_voice():
    voices = _engine.getProperty("voices")
    for v in voices:
        if "german" in v.name.lower() or "_de" in v.id.lower() or "deutsch" in v.name.lower():
            _engine.setProperty("voice", v.id)
            break
    _engine.setProperty("rate", 160)
    _engine.setProperty("volume", 0.9)


_MD_STRIP = [
    (re.compile(r'\*\*(.+?)\*\*'), r'\1'),
    (re.compile(r'\*(.+?)\*'),     r'\1'),
    (re.compile(r'`[^`]+`'),       ' '),
    (re.compile(r'#{1,6}\s'),      ''),
    (re.compile(r'\[.+?\]\(.+?\)'), ''),
]


def speak(text: str):
    if not _voice_enabled:
        return
    for pattern, repl in _MD_STRIP:
        text = pattern.sub(repl, text)
    text = text.strip()[:900]
    _engine.say(text)
    _engine.runAndWait()


# ── Audio recording ───────────────────────────────────────────────────────────

_FORMAT   = pyaudio.paInt16 if AUDIO_OK else None
_CHANNELS = 1
_RATE     = 16000
_CHUNK    = 1024


def record_audio() -> str | None:
    """Block until user presses Enter, then return path to recorded WAV."""
    if not AUDIO_OK:
        return None

    pa     = pyaudio.PyAudio()
    stream = pa.open(
        format=_FORMAT, channels=_CHANNELS, rate=_RATE,
        input=True, frames_per_buffer=_CHUNK,
    )
    frames    = []
    recording = [True]

    def _read():
        while recording[0]:
            frames.append(stream.read(_CHUNK, exception_on_overflow=False))

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    input("  ▸ Aufnahme läuft... [Enter] zum Stoppen")
    recording[0] = False
    t.join(timeout=1)
    stream.stop_stream()
    stream.close()
    pa.terminate()

    if not frames:
        return None

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(tmp.name, "wb") as wf:
        wf.setnchannels(_CHANNELS)
        wf.setsampwidth(pyaudio.PyAudio().get_sample_size(_FORMAT))
        wf.setframerate(_RATE)
        wf.writeframes(b"".join(frames))
    return tmp.name


# ── Transcription ─────────────────────────────────────────────────────────────

_model = None


def transcribe(wav_path: str) -> str:
    if not WHISPER_OK:
        return ""
    global _model
    if _model is None:
        print("  ▸ Lade Whisper-Modell (base)...")
        _model = _whisper.load_model("base")
    result = _model.transcribe(wav_path, language="de")
    try:
        os.unlink(wav_path)
    except Exception:
        pass
    return (result.get("text") or "").strip()


# ── Main loop ─────────────────────────────────────────────────────────────────

WAKE_WORD = "hey tens"


def main():
    _setup_voice()
    history: list   = []
    use_wake        = "--wake" in sys.argv

    print("TENS Sprachmodus")
    print(f"  Wake-Word : {'AN  — sage \"Hey TENS\" vor dem Befehl' if use_wake else 'AUS'}")
    print(f"  Whisper   : {'OK' if WHISPER_OK else 'FEHLT'}")
    print(f"  PyAudio   : {'OK' if AUDIO_OK else 'FEHLT'}")
    print("  [Enter] = Aufnahme starten  |  'exit' = Beenden\n")

    speak("Hallo! TENS Sprachmodus ist aktiv.")

    while True:
        try:
            cmd = input("Du: [Enter] zum Sprechen, 'exit' zum Beenden > ").strip()
        except (EOFError, KeyboardInterrupt):
            speak("Tschüss!")
            break

        if cmd.lower() in {"exit", "quit", "bye"}:
            speak("Tschüss!")
            break

        # Text shortcut: type directly
        if cmd:
            text = cmd
        else:
            wav = record_audio()
            if not wav:
                print("  ▸ Keine Aufnahme.")
                continue
            print("  ▸ Transkribiere...")
            text = transcribe(wav)
            if not text:
                print("  ▸ Nichts erkannt.")
                continue
            print(f"  ▸ Erkannt: {text}")

        # Wake-word check
        if use_wake and WAKE_WORD not in text.lower():
            print("  ▸ Wake-Word nicht erkannt, ignoriert.")
            continue
        if use_wake:
            text = re.sub(re.escape(WAKE_WORD), "", text, flags=re.I).strip()
            if not text:
                speak("Ich höre zu.")
                continue

        # Route the input (same logic as tens.py main loop)
        if text.startswith("http"):
            speak("Ich lese die Webseite.")
            from scraper import lese_webseite
            inhalt = lese_webseite(text)
            if len(inhalt) > 80:
                verarbeite_zu_wissen(text, inhalt)
            history = chat(
                "Du hast eine Webseite gelesen. Fasse kurz zusammen was du gelernt hast.",
                history, extrahiere=False,
            )
        elif text.lower().startswith("lerne:"):
            thema = text[6:].strip()
            speak(f"Ich lerne jetzt über {thema}.")
            wissen = suche_und_lerne(f"{thema} erklärung tutorial")
            if len(wissen) > 80:
                verarbeite_zu_wissen(thema, wissen)
            history = chat(
                f"Fasse auf Deutsch zusammen was du über '{thema}' gelernt hast.",
                history, extrahiere=False,
            )
        else:
            math_expr   = extrahiere_mathe(text)
            math_result = safe_eval(math_expr) if math_expr else None

            if math_result is not None:
                history = chat(
                    f"{text}\n\n[Python-Rechner: {math_expr} = {math_result}. Nenne dieses Ergebnis.]",
                    history, extrahiere=True,
                )
            elif braucht_suche(text):
                speak("Ich suche kurz im Internet.")
                neues_wissen = suche_und_lerne(text)
                if len(neues_wissen.strip()) > 80:
                    verarbeite_zu_wissen(text, neues_wissen)
                    history = chat(
                        f"Beantworte diese Frage auf Deutsch:\n{text}\n\nInformationen:\n{neues_wissen[:2000]}",
                        history, extrahiere=True,
                    )
                else:
                    history = chat(
                        f"{text}\n\n[Keine Informationen gefunden. Sage 'Ich weiss es nicht'.]",
                        history, extrahiere=False,
                    )
            else:
                history = chat(text, history, extrahiere=True)

        # Speak the last TENS reply
        if history and history[-1]["role"] == "assistant":
            speak(history[-1]["content"])


if __name__ == "__main__":
    main()
