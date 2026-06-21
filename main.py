from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.responses import FileResponse
import edge_tts
import tempfile
import os
import subprocess
from typing import List

app = FastAPI()

SEGMENT_DIR = "/tmp/radio_segments"
os.makedirs(SEGMENT_DIR, exist_ok=True)

class AmbienceSegmentRequest(BaseModel):
    index: int
    duration_sec: float = 10
    filename: str
    sound: str = "radio_static"
    
class TTSRequest(BaseModel):
    text: str
    voice: str = "ru-RU-DmitryNeural"
    rate: str = "-10%"
    pitch: str = "-2Hz"


class SilenceRequest(BaseModel):
    duration_sec: float = 5


class TTSSegmentRequest(BaseModel):
    index: int
    text: str
    filename: str
    voice: str = "ru-RU-DmitryNeural"
    rate: str = "-12%"
    pitch: str = "-3Hz"


class SilenceSegmentRequest(BaseModel):
    index: int
    duration_sec: float = 5
    filename: str


class ConcatRequest(BaseModel):
    files: List[str]


@app.get("/")
def health():
    return {"status": "ok"}


@app.get("/segment/{filename}")
async def get_segment(filename: str):
    path = os.path.join(SEGMENT_DIR, filename)
    return FileResponse(path, media_type="audio/mpeg", filename=filename)


@app.post("/tts")
async def tts(req: TTSRequest):
    if not req.text or not req.text.strip():
        return {"error": "empty text"}

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp.close()

    communicate = edge_tts.Communicate(
        req.text,
        req.voice,
        rate=req.rate,
        pitch=req.pitch,
    )

    await communicate.save(tmp.name)

    return FileResponse(
        tmp.name,
        media_type="audio/mpeg",
        filename="speech.mp3",
    )


@app.post("/silence")
async def silence(req: SilenceRequest):
    duration = max(0.1, min(req.duration_sec, 60))

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp.close()

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=mono",
        "-t", str(duration),
        tmp.name,
    ]

    subprocess.run(cmd, check=True)

    return FileResponse(
        tmp.name,
        media_type="audio/mpeg",
        filename="silence.mp3",
    )

@app.post("/ambience-segment")
async def ambience_segment(req: AmbienceSegmentRequest):
    duration = max(0.1, min(req.duration_sec, 60))
    path = os.path.join(SEGMENT_DIR, req.filename)

    sound = (req.sound or "low_bed").lower()

    if "static" in sound or "radio" in sound:
        source = "anoisesrc=color=white:amplitude=0.06"
    elif "storm" in sound or "wind" in sound or "rain" in sound:
        source = "anoisesrc=color=brown:amplitude=0.12"
    else:
        source = "sine=frequency=55:sample_rate=44100"

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", source,
        "-t", str(duration),
        "-af", "volume=0.12,lowpass=f=900,highpass=f=35",
        "-ac", "1",
        "-ar", "44100",
        "-b:a", "128k",
        path,
    ]

    subprocess.run(cmd, check=True)

    return {
        "index": req.index,
        "type": "ambience",
        "filename": req.filename,
        "path": path,
        "sound": req.sound,
    }

    return {
        "index": req.index,
        "type": "ambience",
        "filename": req.filename,
        "path": path,
        "sound": req.sound,
    }
    
@app.post("/tts-segment")
async def tts_segment(req: TTSSegmentRequest):
    path = os.path.join(SEGMENT_DIR, req.filename)

    communicate = edge_tts.Communicate(
        req.text,
        req.voice,
        rate=req.rate,
        pitch=req.pitch,
    )

    await communicate.save(path)

    return {
        "index": req.index,
        "type": "speech",
        "filename": req.filename,
        "path": path,
    }


@app.post("/silence-segment")
async def silence_segment(req: SilenceSegmentRequest):
    duration = max(0.1, min(req.duration_sec, 60))
    path = os.path.join(SEGMENT_DIR, req.filename)

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=mono",
        "-t", str(duration),
        path,
    ]

    subprocess.run(cmd, check=True)

    return {
        "index": req.index,
        "type": "silence",
        "filename": req.filename,
        "path": path,
    }


@app.post("/concat")
async def concat(req: ConcatRequest):
    list_path = os.path.join(SEGMENT_DIR, "concat_list.txt")
    output_path = os.path.join(SEGMENT_DIR, "episode.mp3")

    with open(list_path, "w", encoding="utf-8") as f:
        for filename in req.files:
            safe_path = os.path.join(SEGMENT_DIR, filename)
            f.write(f"file '{safe_path}'\n")

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-ac", "1",
        "-ar", "44100",
        "-b:a", "128k",
        output_path,
    ]

    subprocess.run(cmd, check=True)

    return FileResponse(
        output_path,
        media_type="audio/mpeg",
        filename="episode.mp3",
    )
