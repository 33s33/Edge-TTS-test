from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.responses import FileResponse
import edge_tts
import tempfile
import os

app = FastAPI()

class TTSRequest(BaseModel):
    text: str
    voice: str = "ru-RU-DmitryNeural"
    rate: str = "-10%"
    pitch: str = "-2Hz"

@app.get("/")
def health():
    return {"status": "ok"}

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
