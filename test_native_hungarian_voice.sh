#!/usr/bin/env bash
set -e

SERVER_URL="http://127.0.0.1:8080/v1/tts"
VOICE_FILE="native_hungarian_ref.wav"
OUTPUT_FILE="${2:-calm_hungarian_output.wav}"
SEED="${3:-42}"

REF_TEXT="Mi az öt dolog, amit a legjobban és a legkevésbé szeretek Magyarországon a politikát elkerülve? Nehéz lesz öt negatív dolgot mondani politika nélkül, mert főleg az az oka annak, ha valaki nem szeret valamit Magyarországon, de megpróbálom."

RAW_INPUT="${1:-A mohácsi Duna-híd beruházásánál havi, teljesítésarányos elszámolásra térnek át, a kivitelező Duna Aszfalt Zrt. pedig 58,6 milliárd forintnyi, még teljesítéssel le nem fedett előleget fizet vissza az államnak. A Közlekedési és Beruházási Minisztériummal kötött megállapodás szerint a kivitelezés a nem felfüggesztett területeken tovább folytatódik.}"

if [ ! -f "$VOICE_FILE" ]; then
    echo "Error: $VOICE_FILE not found in $(pwd)"
    exit 1
fi

# Preprocess & Normalize Hungarian text (Abbreviations & Decimals)
NORMALIZED_TEXT=$(python3 -c "
import re, sys

text = '''$RAW_INPUT'''

# 1. Expand / strip trailing periods from common Hungarian abbreviations
abbrev_map = {
    r'\bZrt\.': 'Zrt',
    r'\bKft\.': 'Kft',
    r'\bNyrt\.': 'Nyrt',
    r'\bBt\.': 'Bt',
    r'\bdr\.': 'doktor',
    r'\bDr\.': 'Doktor',
    r'\bprof\.': 'professzor',
    r'\bProf\.': 'Professzor',
    r'\bpl\.': 'például',
    r'\bkb\.': 'körülbelül',
    r'\bstb\.': 'és így tovább',
    r'\bvö\.': 'vesd össze',
    r'\bún\.': 'úgynevezett',
    r'\bFt\b': 'forint',
    r'%': ' százalék'
}

for pattern, repl in abbrev_map.items():
    text = re.sub(pattern, repl, text)

# 2. Normalize decimal numbers: e.g. 58,6 -> 58 egész 6 tized
text = re.sub(r'(\d+),(\d+)', r'\1 egész \2 tized', text)

# 3. Prepend style tag if no custom tag is provided
if not text.strip().startswith('['):
    text = '[speaking naturally with clear articulation] ' + text

print(text.strip())
")

echo "=========================================================="
echo "Fish Speech Native Hungarian Voice (Auto-Normalized)"
echo "Voice Reference: $VOICE_FILE"
echo "Seed:            $SEED"
echo "Synthesizing:    $NORMALIZED_TEXT"
echo "Output File:     $OUTPUT_FILE"
echo "=========================================================="

python3 - <<PY | curl -s -X POST "$SERVER_URL" -H "Content-Type: application/json" -d @- -o "$OUTPUT_FILE"
import base64, json, sys

with open("$VOICE_FILE", "rb") as f:
    audio_b64 = base64.b64encode(f.read()).decode("utf-8")

payload = {
    "text": """$NORMALIZED_TEXT""",
    "references": [
        {
            "audio": audio_b64,
            "text": """$REF_TEXT"""
        }
    ],
    "temperature": 0.68,
    "top_p": 0.85,
    "repetition_penalty": 1.15,
    "seed": int("$SEED"),
    "format": "wav"
}
json.dump(payload, sys.stdout)
PY

if [ -s "$OUTPUT_FILE" ]; then
    FILE_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
    echo "Success! Audio saved to: $OUTPUT_FILE ($FILE_SIZE)"
    echo "To listen: aplay $OUTPUT_FILE (or mpv $OUTPUT_FILE)"
else
    echo "Error: Failed to generate audio. Is the API server running on $SERVER_URL?"
    exit 1
fi
