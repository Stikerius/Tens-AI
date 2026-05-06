# TENS AI 🤖

Persönlicher lokaler KI-Assistent – komplett offline, keine Abhängigkeiten.

## Was ist TENS?

TENS ist ein selbst gebauter KI-Assistent der lokal auf deinem PC läuft.
Kein Abo, keine API, keine Datenweitergabe – alles gehört dir.

## Features

- Lokales Sprachmodell via Ollama (Dolphin-Mistral)
- Dauerhaftes Gedächtnis über ChromaDB + JSON
- Lernt automatisch Fakten über den Nutzer
- Komplett offline nach dem Setup

## Geplante Features

- Web Scraping
- Haussteuerung via Home Assistant
- Social Media Agent
- Bildgenerierung via Stable Diffusion

## Setup

1. Python installieren
2. Ollama installieren
3. Modell laden: `ollama pull dolphin-mistral`
4. Dependencies installieren: `pip install requests chromadb`
5. Starten: `python tens.py`

## Tech Stack

- Python
- Ollama
- Dolphin-Mistral 7B
- ChromaDB