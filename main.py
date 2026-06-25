from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import edge_tts
import tempfile
import os
import subprocess
import uuid
from typing import List, Optional

app = FastAPI()

SEGMENT_DIR = "/tmp/radio_segments"
ASSETS_DIR = "assets"
os.makedirs(SEGMENT_DIR, exist_ok=True)


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


class AmbienceSegmentRequest(BaseModel):
    index: int
    duration_sec: float = 10
    filename: str
    sound: str = "low_bed"


class BedRequest(BaseModel):
    file: str = "concrete_bunker_10m.mp3"
    start: float = 0
    duration: float = 5
    volume: float = 1.0
    name: Optional[str] = None


class MixEpisodeRequest(BaseModel):
    episode_file: str = "episode.mp3"
    bed_file: str = "concrete_bunker_10m.mp3"
    voice_volume: float = 1.0
    bed_volume: float = 1.0
    output_file: str = "episode_final.mp3"


class RadioWrapRequest(BaseModel):
    filename: str
    open_file: str = "radio_open.mp3"
    close_file: str = "radio_close.mp3"
    overwrite: bool = True


class ConcatRequest(BaseModel):
    files: List[str]


@app.get("/")
def health():
    return {"status": "ok", "service": "edge-tts-audio-api"}


@app.get("/routes")
def routes():
    return {
        "routes": [
            "/",
            "/routes",
            "/tts",
            "/silence",
            "/tts-segment",
            "/silence-segment",
            "/ambience-segment",
            "/bed",
            "/mix-episode",
            "/radio-wrap-segment",
            "/concat",
            "/segment/{filename}",
        ]
    }


@app.get("/segment/{filename}")
async def get_segment(filename: str):
    path = os.path.join(SEGMENT_DIR, filename)

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Segment not found: {filename}")

    return FileResponse(path, media_type="audio/mpeg", filename=filename)


@app.post("/tts")
async def tts(req: TTSRequest):
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="empty text")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp.close()

    communicate = edge_tts.Communicate(
        req.text,
        req.voice,
        rate=req.rate,
        pitch=req.pitch,
    )

    await communicate.save(tmp.name)

    return FileResponse(tmp.name, media_type="audio/mpeg", filename="speech.mp3")


@app.post("/silence")
async def silence(req: SilenceRequest):
    duration = max(0.1, min(req.duration_sec, 60))

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp.close()

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=mono",
        "-t", str(duration),
        "-ac", "1",
        "-ar", "44100",
        "-b:a", "128k",
        tmp.name,
    ]

    subprocess.run(cmd, check=True)

    return FileResponse(tmp.name, media_type="audio/mpeg", filename="silence.mp3")


@app.post("/tts-segment")
async def tts_segment(req: TTSSegmentRequest):
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="empty text")

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
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=mono",
        "-t", str(duration),
        "-ac", "1",
        "-ar", "44100",
        "-b:a", "128k",
        path,
    ]

    subprocess.run(cmd, check=True)

    return {
        "index": req.index,
        "type": "silence",
        "filename": req.filename,
        "path": path,
    }


@app.post("/bed")
async def make_bed(req: BedRequest):
    input_path = os.path.join(ASSETS_DIR, req.file)

    if not os.path.exists(input_path):
        raise HTTPException(status_code=404, detail=f"File not found: {input_path}")

    duration = max(0.1, min(req.duration, 3600))
    start = max(0, req.start)
    volume = max(0.0, min(req.volume, 2.0))

    output_name = req.name or f"bed_{uuid.uuid4().hex}.mp3"
    output_path = os.path.join(SEGMENT_DIR, output_name)

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", input_path,
        "-t", str(duration),
        "-filter:a", f"volume={volume}",
        "-ac", "1",
        "-ar", "44100",
        "-b:a", "128k",
        output_path,
    ]

    subprocess.run(cmd, check=True)

    return FileResponse(output_path, media_type="audio/mpeg", filename=output_name)


@app.post("/mix-episode")
async def mix_episode(req: MixEpisodeRequest):
    episode_path = os.path.join(SEGMENT_DIR, req.episode_file)
    bed_path = os.path.join(ASSETS_DIR, req.bed_file)
    output_path = os.path.join(SEGMENT_DIR, req.output_file)

    if not os.path.exists(episode_path):
        raise HTTPException(status_code=404, detail=f"Episode not found: {episode_path}")

    if not os.path.exists(bed_path):
        raise HTTPException(status_code=404, detail=f"Bed not found: {bed_path}")

    voice_volume = max(0.0, min(req.voice_volume, 3.0))
    bed_volume = max(0.0, min(req.bed_volume, 3.0))

    cmd = [
        "ffmpeg", "-y",
        "-i", episode_path,
        "-stream_loop", "-1",
        "-i", bed_path,
        "-filter_complex",
        (
            f"[0:a]volume={voice_volume}[voice];"
            f"[1:a]volume={bed_volume}[bed];"
            "[voice][bed]amix=inputs=2:duration=first:dropout_transition=0[out]"
        ),
        "-map", "[out]",
        "-ac", "1",
        "-ar", "44100",
        "-b:a", "128k",
        output_path,
    ]

    subprocess.run(cmd, check=True)

    return FileResponse(
        output_path,
        media_type="audio/mpeg",
        filename=req.output_file,
    )


@app.post("/radio-wrap-segment")
async def radio_wrap_segment(req: RadioWrapRequest):
    speech_path = os.path.join(SEGMENT_DIR, req.filename)

    if not os.path.exists(speech_path):
        raise HTTPException(
            status_code=404,
            detail=f"Speech file not found: {req.filename}"
        )

    open_path = os.path.join(ASSETS_DIR, req.open_file)
    close_path = os.path.join(ASSETS_DIR, req.close_file)

    if not os.path.exists(open_path):
        raise HTTPException(
            status_code=404,
            detail=f"Open sound not found: {req.open_file}"
        )

    if not os.path.exists(close_path):
        raise HTTPException(
            status_code=404,
            detail=f"Close sound not found: {req.close_file}"
        )

    output_path = speech_path

    if not req.overwrite:
        root, ext = os.path.splitext(speech_path)
        output_path = f"{root}_radio{ext}"

    temp_output = output_path + ".tmp.mp3"

    cmd = [
        "ffmpeg", "-y",
        "-i", open_path,
        "-i", speech_path,
        "-i", close_path,
        "-filter_complex",
        "[0:a][1:a][2:a]concat=n=3:v=0:a=1[out]",
        "-map", "[out]",
        "-ac", "1",
        "-ar", "44100",
        "-b:a", "128k",
        temp_output,
    ]

    subprocess.run(cmd, check=True)

    os.replace(temp_output, output_path)

    return {
        "filename": os.path.basename(output_path),
        "wrapped": True,
        "open_file": req.open_file,
        "close_file": req.close_file,
        "overwrite": req.overwrite,
    }


@app.post("/ambience-segment")
async def ambience_segment(req: AmbienceSegmentRequest):
    duration = max(0.1, min(req.duration_sec, 60))
    path = os.path.join(SEGMENT_DIR, req.filename)

    sound = (req.sound or "low_bed").lower()

    if sound in ["concrete_bunker", "bunker", "bed_bunker"]:
        input_path = os.path.join(ASSETS_DIR, "concrete_bunker_10m.mp3")
    elif sound in ["research_facility", "facility", "bed_facility"]:
        input_path = os.path.join(ASSETS_DIR, "research_facility_10m.mp3")
    else:
        input_path = None

    if input_path and os.path.exists(input_path):
        start = (req.index * 13) % 540

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", input_path,
            "-t", str(duration),
            "-filter:a", "volume=0.55",
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
            "source": input_path,
            "start": start,
        }

    sources = [
        ("sine=frequency=55:sample_rate=44100", "volume=0.22"),
        ("sine=frequency=82:sample_rate=44100", "volume=0.14"),
        ("anoisesrc=color=brown:amplitude=0.18:sample_rate=44100", "volume=0.45,highpass=f=45,lowpass=f=1600"),
    ]

    cmd = ["ffmpeg", "-y"]

    for source, _filter in sources:
        cmd += ["-f", "lavfi", "-i", source]

    filter_parts = []
    labels = []

    for i, (_source, audio_filter) in enumerate(sources):
        label = f"a{i}"
        filter_parts.append(f"[{i}:a]{audio_filter}[{label}]")
        labels.append(f"[{label}]")

    filter_complex = (
        ";".join(filter_parts)
        + ";"
        + "".join(labels)
        + f"amix=inputs={len(sources)}:duration=longest,"
        + "tremolo=f=0.10:d=0.35,"
        + "volume=1.6[out]"
    )

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-t", str(duration),
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
        "source": "generated",
    }


@app.post("/concat")
async def concat(req: ConcatRequest):
    if not req.files:
        raise HTTPException(status_code=400, detail="No files provided")

    list_path = os.path.join(SEGMENT_DIR, "concat_list.txt")
    output_path = os.path.join(SEGMENT_DIR, "episode.mp3")

    missing = []

    with open(list_path, "w", encoding="utf-8") as f:
        for filename in req.files:
            safe_path = os.path.join(SEGMENT_DIR, filename)

            if not os.path.exists(safe_path):
                missing.append(filename)

            f.write(f"file '{safe_path}'\n")

    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing segment files: {', '.join(missing[:10])}",
        )

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-ac", "1",
        "-ar", "44100",
        "-b:a", "128k",
        output_path,
    ]

    subprocess.run(cmd, check=True)

    return FileResponse(output_path, media_type="audio/mpeg", filename="episode.mp3")
