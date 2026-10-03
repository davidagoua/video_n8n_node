import os
import uuid
import asyncio
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
    """Génère l'audio MP3 et le fichier de sous-titres SRT."""
    req_id = str(uuid.uuid4())
    audio_path = os.path.join(TMP_DIR, f"{req_id}.mp3")
    srt_path = os.path.join(TMP_DIR, f"{req_id}.srt")

    try:
        communicate = edge_tts.Communicate(payload.script, payload.voice)
        submaker = edge_tts.SubMaker()

        with open(audio_path, "wb") as f_audio:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f_audio.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    submaker.feed(chunk)

        with open(srt_path, "w", encoding="utf-8") as f_srt:
            f_srt.write(submaker.get_srt())

        return {
            "task_id": req_id,
            "audio_path": audio_path,
            "subtitles_path": srt_path
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS generation error: {str(e)}")


@app.post("/render-video")
async def render_video(
    task_id: str = Form(...),
    video_file: UploadFile = File(...)
):
    """
    Reçoit la vidéo de fond (multipart/form-data), l'associe à l'audio/sous-titres
    du task_id précédent, et renvoie le MP4 assemblé en binaire.
    """
    audio_path = os.path.join(TMP_DIR, f"{task_id}.mp3")
    srt_path = os.path.join(TMP_DIR, f"{task_id}.srt")
    bg_video_path = os.path.join(TMP_DIR, f"{task_id}_bg.mp4")
    output_video_path = os.path.join(TMP_DIR, f"{task_id}_final.mp4")

    if not os.path.exists(audio_path) or not os.path.exists(srt_path):
        raise HTTPException(status_code=404, detail="Audio or subtitle files not found for this task_id")

    # Sauvegarde de la vidéo de fond reçue
    with open(bg_video_path, "wb") as f_bg:
        f_bg.write(await video_file.read())

    # Format vertical 9:16 (1080x1920) avec sous-titres centrés incrustés
    video_filters = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        f"subtitles={srt_path}:force_style='FontSize=22,FontName=DejaVu Sans,Bold=1,"
        "PrimaryColour=&H00FFFFFF&,OutlineColour=&H00000000&,BorderStyle=1,Outline=2,Alignment=2,MarginV=180'"
    )

    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", bg_video_path,
        "-i", audio_path,
        "-vf", video_filters,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        output_video_path
    ]

    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            raise Exception(proc.stderr)

        return FileResponse(
            path=output_video_path,
            filename="output.mp4",
            media_type="video/mp4"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FFmpeg error: {str(e)}")
    finally:
        # Nettoyage des fichiers intermédiaires légers
        for path in [bg_video_path]:
            if os.path.exists(path):
                os.remove(path)