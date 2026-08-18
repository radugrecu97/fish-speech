#!/usr/bin/env python3
"""
Extract Voice Sample & Transcript from Video Link (YouTube) for Fish Speech TTS.
Supports English, Hungarian, Danish, and other languages.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple


# Ensure deno and user bin paths are in PATH for yt-dlp JavaScript challenge solver
deno_bin_dir = str(Path.home() / ".deno/bin")
if deno_bin_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{deno_bin_dir}:{os.environ.get('PATH', '')}"


def find_binary(name: str) -> str:
    """Find binary path in conda/venv bin or system PATH."""
    # 1. Active python directory
    py_bin = Path(sys.executable).parent / name
    if py_bin.exists() and os.access(py_bin, os.X_OK):
        return str(py_bin)

    # 2. Check conda and user bin directories
    candidates = [
        Path.home() / ".deno/bin" / name,
        Path.home() / ".local/bin" / name,
        Path.home() / "miniconda3/envs/fish-speech/bin" / name,
        Path.home() / "anaconda3/envs/fish-speech/bin" / name,
        Path.home() / ".conda/envs/fish-speech/bin" / name,
        Path("/usr/local/bin") / name,
        Path("/usr/bin") / name,
    ]
    for c in candidates:
        if c.exists() and os.access(c, os.X_OK):
            return str(c)

    found = shutil.which(name)
    if found:
        return found
    return name


def parse_timestamp(ts: str) -> float:
    """Parse timestamps like '90', '1:30', '01:30', '00:01:30' into total seconds."""
    ts = ts.strip()
    parts = ts.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        else:
            raise ValueError
    except Exception:
        raise ValueError(f"Invalid timestamp format: '{ts}'. Use 'MM:SS' or seconds (e.g. '1:30' or '90').")


def format_timestamp(seconds: float) -> str:
    """Format seconds into HH:MM:SS."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hrs:02d}:{mins:02d}:{secs:02d}"


def normalize_lang_code(lang: str) -> str:
    """Map language name / aliases to ISO language code."""
    lang = lang.lower().strip()
    mapping = {
        "en": "en", "english": "en",
        "hu": "hu", "hungarian": "hu", "magyar": "hu",
        "da": "da", "danish": "da", "dansk": "da",
        "de": "de", "german": "de", "deutsch": "de",
        "fr": "fr", "french": "fr", "français": "fr",
        "es": "es", "spanish": "es", "español": "es",
        "it": "it", "italian": "it", "italiano": "it",
        "ja": "ja", "japanese": "ja",
        "zh": "zh", "chinese": "zh",
    }
    return mapping.get(lang, lang)


def parse_vtt_subtitles(vtt_content: str, start_sec: float, end_sec: float) -> str:
    """Extract clean text from WebVTT subtitles between start_sec and end_sec."""
    lines = vtt_content.splitlines()
    text_blocks = []
    seen_texts = set()

    time_pattern = re.compile(r"(\d{2}):(\d{2}):(\d{2}\.\d{3})\s+-->\s+(\d{2}):(\d{2}):(\d{2}\.\d{3})")
    current_in_range = False

    for line in lines:
        line_str = line.strip()
        if not line_str or line_str.startswith("WEBVTT") or line_str.startswith("Kind:") or line_str.startswith("Language:"):
            continue

        time_match = time_pattern.search(line_str)
        if time_match:
            h1, m1, s1 = time_match.group(1), time_match.group(2), time_match.group(3)
            h2, m2, s2 = time_match.group(4), time_match.group(5), time_match.group(6)
            block_start = int(h1) * 3600 + int(m1) * 60 + float(s1)
            block_end = int(h2) * 3600 + int(m2) * 60 + float(s2)

            # Check if within range (with 1.5s tolerance)
            current_in_range = (block_end >= start_sec - 0.5) and (block_start <= end_sec + 0.5)
            continue

        if current_in_range:
            # Clean VTT timing tags like <00:01:32.400>, <c>, </c>, &gt;&gt;
            clean = re.sub(r"<[^>]+>", "", line_str)
            clean = re.sub(r"&gt;&gt;", "", clean)
            clean = re.sub(r"&amp;", "&", clean)
            clean = re.sub(r"&quot;", '"', clean)
            clean = re.sub(r"&#39;|&apos;", "'", clean)
            clean = clean.strip()
            if clean and clean not in seen_texts:
                seen_texts.add(clean)
                text_blocks.append(clean)

    # Join and deduplicate repeated words from rolling captions
    combined = " ".join(text_blocks)
    combined = re.sub(r"\s+", " ", combined).strip()
    return combined


def extract_voice_sample(
    url: str,
    start_time: str,
    end_time: str,
    lang: str = "en",
    name: Optional[str] = None,
    output_dir: str = ".",
) -> Tuple[Path, str]:
    """Downloads audio slice, extracts subtitles, and outputs 44.1kHz mono WAV + transcript."""
    start_sec = parse_timestamp(start_time)
    end_sec = parse_timestamp(end_time)

    if end_sec <= start_sec:
        raise ValueError(f"End time ({end_time}) must be greater than start time ({start_time}).")

    duration = end_sec - start_sec
    lang_code = normalize_lang_code(lang)

    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not name:
        name = f"{lang_code}_voice_sample_{int(start_sec)}_{int(end_sec)}"
    if name.endswith(".wav"):
        name = name[:-4]

    final_wav_path = out_dir / f"{name}.wav"
    final_txt_path = out_dir / f"{name}.txt"

    temp_stem = out_dir / f"_temp_{name}"
    temp_vtt = out_dir / f"_temp_{name}.{lang_code}.vtt"

    start_hhmmss = format_timestamp(start_sec)
    end_hhmmss = format_timestamp(end_sec)
    section_arg = f"*{start_hhmmss}-{end_hhmmss}"

    print(f"\n========================================================")
    print(f"Extracting Voice Sample from YouTube")
    print(f"URL:        {url}")
    print(f"Time Range: {start_hhmmss} -> {end_hhmmss} ({duration:.1f} seconds)")
    print(f"Language:   {lang_code}")
    print(f"Output:     {final_wav_path}")
    print(f"========================================================\n")

    yt_bin = find_binary("yt-dlp")
    ffmpeg_bin = find_binary("ffmpeg")

    # 1. Download audio file and subtitles with yt-dlp
    cmd_dl = [
        yt_bin,
        "--extractor-args", "youtube:player_client=web_embedded,web",
        "-f", "140/ba[ext=m4a]/ba/b",
        "--write-auto-subs",
        "--write-subs",
        "--sub-lang", lang_code,
        "--no-playlist",
        "-o", f"{temp_stem}.%(ext)s",
        url,
    ]

    print("Downloading audio and subtitles from YouTube...")
    res = subprocess.run(cmd_dl, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if res.returncode != 0:
        # Fallback if specific audio format not found
        cmd_dl_fallback = [
            yt_bin,
            "--extractor-args", "youtube:player_client=web_embedded,web",
            "-f", "ba/b",
            "--write-auto-subs",
            "--write-subs",
            "--sub-lang", lang_code,
            "--no-playlist",
            "-o", f"{temp_stem}.%(ext)s",
            url,
        ]
        res_fb = subprocess.run(cmd_dl_fallback, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if res_fb.returncode != 0:
            print(res_fb.stdout)
            raise RuntimeError("yt-dlp failed to download audio. Check video URL.")

    # Find the downloaded temporary media file
    downloaded_media = None
    for ext in ("m4a", "webm", "opus", "mp4", "mp3", "wav", "mkv"):
        for p in out_dir.glob(f"_temp_{name}*.{ext}"):
            downloaded_media = p
            break
        if downloaded_media:
            break

    if not downloaded_media or not downloaded_media.exists():
        raise RuntimeError(f"Failed to find downloaded audio file with prefix '_temp_{name}'")

    # 2. Trim and resample audio to 44.1 kHz, 1-channel mono PCM WAV
    print(f"Trimming audio ({start_hhmmss} -> {end_hhmmss}) and resampling to 44.1 kHz Mono PCM WAV...")
    cmd_ffmpeg = [
        ffmpeg_bin, "-y",
        "-ss", str(start_sec),
        "-to", str(end_sec),
        "-i", str(downloaded_media),
        "-ar", "44100",
        "-ac", "1",
        str(final_wav_path),
        "-loglevel", "error"
    ]
    subprocess.run(cmd_ffmpeg, check=True)

    # 3. Extract Transcript from Subtitles
    transcript = ""
    vtt_candidates = list(out_dir.glob(f"_temp_{name}*.vtt"))
    if vtt_candidates:
        vtt_file = vtt_candidates[0]
        vtt_content = vtt_file.read_text(encoding="utf-8", errors="ignore")
        transcript = parse_vtt_subtitles(vtt_content, start_sec, end_sec)

    if not transcript:
        transcript = "[Transcript could not be auto-extracted. Please verify audio and enter transcript manually.]"

    # Save transcript file
    final_txt_path.write_text(transcript, encoding="utf-8")

    # 4. Clean up temporary files
    for temp_f in out_dir.glob(f"_temp_{name}*"):
        try:
            temp_f.unlink()
        except Exception:
            pass

    file_size_kb = final_wav_path.stat().st_size / 1024
    print("\nSUCCESS! Voice sample ready:")
    print(f"  • Audio File:  {final_wav_path} ({file_size_kb:.1f} KB)")
    print(f"  • Transcript:  {final_txt_path}")
    print(f"\nTranscript Content:\n\"{transcript}\"\n")
    print(f"Ready for Audiobook Generation:")
    print(f"  python tools/epub_to_audiobook_fishspeech.py \\")
    print(f"    -i book.epub -o book_audiobook.epub --lang {lang_code} \\")
    print(f"    --prompt-audio {final_wav_path} \\")
    print(f"    --prompt-text \"{transcript}\"\n")

    return final_wav_path, transcript


def main():
    parser = argparse.ArgumentParser(
        description="Extract a clean voice reference clip (.wav) & transcript from YouTube for Fish Speech TTS."
    )
    parser.add_argument("url", help="YouTube video URL (e.g. https://www.youtube.com/watch?v=...)")
    parser.add_argument("--start", "-s", required=True, help="Start timestamp (e.g. '01:30', '1:30', or '90')")
    parser.add_argument("--end", "-e", required=True, help="End timestamp (e.g. '01:50', '1:50', or '110')")
    parser.add_argument("--lang", "-l", default="en", help="Language code or name: 'en'/'english', 'hu'/'hungarian', 'da'/'danish' (default: en)")
    parser.add_argument("--name", "-n", help="Output file basename (e.g. 'danish_narrator', 'english_voice')")
    parser.add_argument("--output-dir", "-o", default=".", help="Directory to save extracted .wav and .txt (default: current directory)")

    args = parser.parse_args()

    try:
        extract_voice_sample(
            url=args.url,
            start_time=args.start,
            end_time=args.end,
            lang=args.lang,
            name=args.name,
            output_dir=args.output_dir,
        )
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
