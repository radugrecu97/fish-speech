#!/usr/bin/env bash
set -e

SERVER_URL="http://127.0.0.1:8080/v1/tts"
VOICE_FILE="english_kristen_naiman.wav"
OUTPUT_FILE="${2:-english_kristen_output.wav}"
SEED="${3:-42}"

REF_TEXT="that clothing provided. Um, but my mom was very correct about it. She had a sort of she had a approach to it that was very sort of uh transactional in a way. It was like I'm going to use clothes in this way to appear like this. And she had a seriousness about it. And my dad had a more playful side about it and a kind of a joyful side."

RAW_INPUT="${1:-The old clock in the hallway struck twelve with a deep, echoing chime that resonated through the quiet house, while the autumn wind gently stirred the dry leaves outside.}"

if [ ! -f "$VOICE_FILE" ]; then
    echo "Error: $VOICE_FILE not found in $(pwd)"
    exit 1
fi

# Preprocess & Normalize English text (Abbreviations & Decimals)
NORMALIZED_TEXT=$(python3 -c "
import re, sys

text = '''$RAW_INPUT'''

en_abbrev_map = {
    r'\bMr\.': 'Mister',
    r'\bMrs\.': 'Missus',
    r'\bMs\.': 'Miss',
    r'\bDr\.': 'Doctor',
    r'\bProf\.': 'Professor',
    r'\bSt\.': 'Saint',
    r'\betc\.': 'etcetera',
    r'\be\.g\.': 'for example',
    r'\bi\.e\.': 'that is',
    r'\bvs\.': 'versus',
    r'\bapprox\.': 'approximately',
    r'%': ' percent'
}

for pattern, repl in en_abbrev_map.items():
    text = re.sub(pattern, repl, text)

# Normalize decimal numbers: 58.6 -> 58 point 6
text = re.sub(r'(\d+)\.(\d+)', r'\1 point \2', text)

# Prepend calm narrator tag if no custom tag provided
if not text.strip().startswith('['):
    text = '[calm and soothing voice] [speaking softly and clearly] ' + text

print(text.strip())
")

echo "=========================================================="
echo "Fish Speech English Voice (Kristen Naiman - Auto-Normalized)"
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
