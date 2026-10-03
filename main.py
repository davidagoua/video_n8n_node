import os
import uuid
import subprocess
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
import edge_tts

app = FastAPI(title="Video Engine Service")

TMP_DIR = "/tmp/video_engine"
os.makedirs(TMP_DIR, exist_ok=True)


class TTSRequest(BaseModel):
    script: str
    voice: str = "fr-FR-HenriNeural"


@app.post("/generate-tts")
async def generate_tts(payload: TTSRequest):
    """Génère uniquement l'audio MP3 (sans sous-titres)."""
    req_id = str(uuid.uuid4())
    audio_path = os.path.join(TMP_DIR, f"{req_id}.mp3")

    try:
        cmd = [
            "edge-tts",
            "--voice", payload.voice,
            "--text", payload.script,
            "--write-media", audio_path
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            raise Exception(f"edge-tts failed: {proc.stderr}")

        return {
            "task_id": req_id,
            "audio_path": audio_path
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS generation error: {str(e)}")


@app.post("/render-video")
async def render_video(
    task_id: str = Form(...),
    video_file: UploadFile = File(...)
):
    """
    Assemble la vidéo de fond reçue et l'audio MP3 au format 9:16 (sans sous-titres).
    """
    audio_path = os.path.join(TMP_DIR, f"{task_id}.mp3")
    bg_video_path = os.path.join(TMP_DIR, f"{task_id}_bg.mp4")
    output_video_path = os.path.join(TMP_DIR, f"{task_id}_final.mp4")

    if not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found for this task_id")

    # Écriture du fichier vidéo temporaire
    with open(bg_video_path, "wb") as f_bg:
        f_bg.write(await video_file.read())

    # Filtre vidéo : uniquement redimensionnement et recadrage 9:16 (1080x1920)
    video_filters = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"

    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",        # Boucle la vidéo si elle est plus courte que l'audio
        "-i", bg_video_path,
        "-i", audio_path,
        "-vf", video_filters,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",                 # Arrête la vidéo dès que l'audio se termine
        output_video_path
    ]

    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            raise Exception(f"FFmpeg error: {proc.stderr}")

        return FileResponse(
            path=output_video_path,
            filename="output.mp4",
            media_type="video/mp4"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FFmpeg error: {str(e)}")
    finally:
        # Nettoyage de la vidéo de fond brute
        if os.path.exists(bg_video_path):
            os.remove(bg_video_path)