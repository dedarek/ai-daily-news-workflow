import subprocess, json, os, tempfile, base64, re, time

SF_KEY = "sk-xlhbpmkuclcffaekundkmsxofizblslqawbvqsxopxfxvzmm"
SF_URL = "https://api.siliconflow.cn/v1/audio/speech"
DATE = "2026-06-24"

VOICES = {
    "S1": "FunAudioLLM/CosyVoice2-0.5B:anna",  # 老陈 - female english voice? let me check
    "S2": "FunAudioLLM/CosyVoice2-0.5B:anna",  # 小满
}

# Read script
os.makedirs(f"/tmp/podcast-{DATE}", exist_ok=True)
with open(f"/tmp/ai-daily-news-podcast-{DATE}.script") as f:
    lines = f.readlines()

# Parse dialogue - group consecutive same-speaker lines
segments = []
current_speaker = None
current_text = []

for line in lines:
    line = line.strip()
    if not line:
        if current_text:
            segments.append((current_speaker, '\n'.join(current_text)))
            current_text = []
        current_speaker = None
        continue
    
    m = re.match(r'^\[(S[12])\]\s*(.*)', line)
    if not m:
        continue
    
    speaker = m.group(1)
    text = m.group(2).strip()
    
    if speaker != current_speaker:
        if current_text:
            segments.append((current_speaker, '\n'.join(current_text)))
            current_text = []
        current_speaker = speaker
    
    current_text.append(text)

if current_text:
    segments.append((current_speaker, '\n'.join(current_text)))

print(f"Total segments: {len(segments)}")

# Generate audio for each segment
audio_files = []
for i, (speaker, text) in enumerate(segments):
    # Voice mapping
    voice = "FunAudioLLM/CosyVoice2-0.5B:alex" if speaker == "S1" else "FunAudioLLM/CosyVoice2-0.5B:anna"
    
    payload = json.dumps({
        "model": "FunAudioLLM/CosyVoice2-0.5B",
        "input": text,
        "voice": voice,
        "response_format": "mp3"
    })
    
    outfile = f"/tmp/podcast-{DATE}/seg{i:03d}-{speaker}.mp3"
    print(f"[{i+1}/{len(segments)}] {speaker}: {text[:50]}... -> {outfile}")
    
    result = subprocess.run([
        "curl", "-s", "-X", "POST", SF_URL,
        "-H", f"Authorization: Bearer {SF_KEY}",
        "-H", "Content-Type: application/json",
        "-d", payload,
        "-o", outfile
    ], capture_output=True, text=True, timeout=30)
    
    sz = os.path.getsize(outfile)
    if sz < 100:
        # Check if it's an error JSON
        try:
            err = json.loads(open(outfile).read())
            print(f"  ERROR: {err}")
            continue
        except:
            print(f"  WARN: small file ({sz} bytes), might be error")
    
    audio_files.append(outfile)
    print(f"  OK: {sz} bytes")
    time.sleep(0.5)

# Concatenate MP3s
concat_list = f"/tmp/podcast-{DATE}/concat.txt"
with open(concat_list, 'w') as f:
    for af in audio_files:
        f.write(f"file '{af}'\n")

final = f"/tmp/ai-daily-news-podcast-{DATE}.mp3"
subprocess.run([
    "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
    "-c", "copy", final
], capture_output=True)

sz = os.path.getsize(final)
print(f"\nFinal MP3: {final} ({sz} bytes)")

# Get duration
result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1", final], capture_output=True, text=True)
dur = float(result.stdout.strip())
print(f"Duration: {dur:.1f}s ({dur/60:.1f} min)")

with open(f"/tmp/ai-daily-news-podcast-{DATE}.status", "w") as f:
    f.write(f"SUCCESS\npath={final}\nsize={sz}\nduration={dur:.1f}s\n")
