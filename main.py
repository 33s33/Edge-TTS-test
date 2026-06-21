from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.responses import FileResponse
import edge_tts
import tempfile
import os
import subprocess
from fastapi.responses import FileResponse, JSONResponse
from typing import List

app = FastAPI()

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
    
class TTSRequest(BaseModel):
    text: str
    voice: str = "ru-RU-DmitryNeural"
    rate: str = "-10%"
    pitch: str = "-2Hz"

SEGMENT_DIR = "/tmp/radio_segments"
os.makedirs(SEGMENT_DIR, exist_ok=True)

@app.get("/")
def health():
    return {"status": "ok"}

@app.post("/tts-segment")
async def tts_segment(req: TTSSegmentRequest):
    path = os.path.join(SEGMENT_DIR, req.filename)

    communicate = edge_tts.Communicate(
        req.text,
        req.voice,
        rate=req.rate,
        pitch=req.pitch
    )

    await communicate.save(path)

    return {
        "index": req.index,
        "type": "speech",
        "filename": req.filename,
        "path": path
    }

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
        "-q:a", "9",
        "-acodec", "libmp3lame",
        tmp.name
    ]

    subprocess.run(cmd, check=True)

    return FileResponse(
        tmp.name,
        media_type="audio/mpeg",
        filename="silence.mp3"
    )

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
        pitch=req.pitch
    )

    await communicate.save(tmp.name)

    return FileResponse(
        tmp.name,
        media_type="audio/mpeg",
        filename="speech.mp3"
    )
