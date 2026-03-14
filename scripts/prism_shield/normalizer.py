# scripts/prism_shield/normalizer.py

import re
import base64
import urllib.parse
from .base import MemoryEntry

try:
    # When running from project root
    from unicode_defense import normalize_unicode
except ModuleNotFoundError:  # pragma: no cover
    # Fallback if module is installed as a package
    from memshield_unicode_defense import normalize_unicode  # type: ignore[import]  # noqa: F401

class Normalizer:
    def __init__(self):
        self.invisible_chars = [
            '\u200b', '\u200c', '\u200d', '\uFEFF' # Zero width spaces, etc.
        ]
        # Regex to match ANSI escape codes
        self.ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        
    def normalize(self, entry: MemoryEntry) -> str:
        text = entry.text
        
        # 1. URL Decode (handles basic %20 and others often found in Intents/Network)
        text = urllib.parse.unquote(text)
        
        # 2. Base64 attempts. Often, intent extras or payloads might be b64 encoded
        # we try to find base64 looking strings and decode them. This is basic heurustic.
        # A more robust regex might be needed for production.
        b64_matches = re.findall(r'(?:[A-Za-z0-9+/]{4}){10,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?', text)
        for match in b64_matches:
            try:
                decoded = base64.b64decode(match).decode('utf-8')
                text = text.replace(match, decoded)
            except Exception:
                pass # Not valid b64 utf-8
                
        # 3. Remove invisible Unicode characters (obfuscation)
        for char in self.invisible_chars:
            text = text.replace(char, '')
            
        # 4. Remove ANSI escape codes (clipboard obfuscation)
        text = self.ansi_escape.sub('', text)
        
        # 5. Compress extreme whitespace flooding
        text = re.sub(r'[ \t]{10,}', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 6. HTML/XML basic tag stripping if it's accessibility tree or network payload
        # Leaving this somewhat intact for Layer 2 context, but we might want to strip script markers
        text = text.replace("<script>", " ").replace("</script>", " ")

        # 7. Final Unicode hardening (confusables, smart quotes, etc.)
        text = normalize_unicode(text)

        return text.strip()
