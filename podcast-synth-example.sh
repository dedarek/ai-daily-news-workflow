#!/bin/bash
set -euo pipefail
export MOSI_TTS_API_KEY="sk-7268b88879d34f239b7a14f4b3e0ff0b"
DATE="2026-06-24"
SCRIPT="/tmp/ai-daily-news-podcast-${DATE}.script"
OUTDIR="/tmp/podcast-${DATE}"
MOSI="/root/.openclaw/workspace-research/skills/moss-ttsd/scripts/mosi_dialogue.sh"

mkdir -p "$OUTDIR"
cd "$OUTDIR"

# Split the script into 4 segments (~8 lines each)
# seg1: 豆包 + NotebookLM (lines 1-8)
head -8 "$SCRIPT" > seg01.txt
# seg2: OpenAI Cyber + NVIDIA Halos (lines 9-16)
sed -n '9,16p' "$SCRIPT" > seg02.txt
# seg3: Futurist + Rodin (lines 17-24)
sed -n '17,24p' "$SCRIPT" > seg03.txt
# seg4: Meta leak + wrap-up (lines 25-)
sed -n '25,$p' "$SCRIPT" > seg04.txt

for f in seg*.txt; do
    echo "$f: $(wc -l < $f) lines"
done

# Synthesize each segment
for f in seg01.txt seg02.txt seg03.txt seg04.txt; do
    base="${f%.txt}"
    text=$(cat "$f" | sed 's/$/\\n/' | tr -d '\n' | sed 's/\\n$//')
    echo "=== Synthesizing $base (${#text} chars) ==="
    bash "$MOSI" \
        --text "$text" \
        --voice1 2040784925577187328 \
        --voice2 2001910895478837248 \
        --output "${base}.wav" 2>&1 | tail -5
    echo "Done: ${base}.wav ($(stat -c%s ${base}.wav) bytes)"
    sleep 2
done

# Create concat list
rm -f filelist.txt
for f in seg01.wav seg02.wav seg03.wav seg04.wav; do
    echo "file '$OUTDIR/$f'" >> filelist.txt
done

echo "=== Concatenating ==="
ffmpeg -y -f concat -safe 0 -i filelist.txt -c copy "$OUTDIR/full.wav" 2>&1 | tail -3

echo "=== Converting to MP3 64k ==="
ffmpeg -y -i "$OUTDIR/full.wav" -codec:a libmp3lame -b:a 64k "/tmp/ai-daily-news-podcast-${DATE}.mp3" 2>&1 | tail -3

SIZE=$(stat -c%s "/tmp/ai-daily-news-podcast-${DATE}.mp3")
DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "/tmp/ai-daily-news-podcast-${DATE}.mp3" 2>/dev/null || echo "?")
echo "MP3: ${SIZE} bytes, ${DURATION}s"

# Check size
if [ "$SIZE" -gt 8388608 ]; then
    echo "WARNING: MP3 > 8MB, re-encoding at 48k"
    ffmpeg -y -i "$OUTDIR/full.wav" -codec:a libmp3lame -b:a 48k "/tmp/ai-daily-news-podcast-${DATE}.mp3" 2>&1 | tail -3
    SIZE=$(stat -c%s "/tmp/ai-daily-news-podcast-${DATE}.mp3")
    echo "Re-encoded MP3: ${SIZE} bytes"
fi

echo "SUCCESS" > "/tmp/ai-daily-news-podcast-${DATE}.status"
echo "Done!"
