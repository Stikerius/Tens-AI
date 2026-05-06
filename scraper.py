import requests
from bs4 import BeautifulSoup

def lese_webseite(url):
    try:
        response = requests.get(url, timeout=10, headers={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
})
        soup = BeautifulSoup(response.text, "html.parser",)
        
        # Nur den Text extrahieren, kein HTML
        text = soup.get_text(separator="\n", strip=True)
        
        # Leere Zeilen entfernen
        zeilen = [z for z in text.split("\n") if len(z) > 30]
        return "\n".join(zeilen[:100])  # Erste 100 Zeilen
    except Exception as e:
        return f"Fehler: {e}"

# Test
if __name__ == "__main__":
    url = input("URL eingeben: ")
    text = lese_webseite(url)
    print(text)