import os
import asyncio
import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import google.generativeai as genai
import edge_tts
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GENAI_API_KEY = os.getenv("GEMINI_API_KEY")
if GENAI_API_KEY:
    genai.configure(api_key=GENAI_API_KEY)

VOICE_MAPPING = {
    "koko": "my-MM-ThihaNeural",
    "nyinyi": "my-MM-ThihaNeural",
    "maungmaung": "my-MM-ThihaNeural",
    "u_paing": "my-MM-ThihaNeural",
    "hlahla": "my-MM-NilarNeural",
    "myamya": "my-MM-NilarNeural",
    "yuya": "my-MM-NilarNeural",
    "daw_myalay": "my-MM-NilarNeural"
}

VOICE_PITCH_SPEED = {
    "koko": {"speed": "+0%", "pitch": "-5Hz"},
    "nyinyi": {"speed": "+15%", "pitch": "+0Hz"},
    "maungmaung": {"speed": "+10%", "pitch": "-2Hz"},
    "u_paing": {"speed": "-10%", "pitch": "-10Hz"},
    "hlahla": {"speed": "+0%", "pitch": "-2Hz"},
    "myamya": {"speed": "+15%", "pitch": "+0Hz"},
    "yuya": {"speed": "+10%", "pitch": "+3Hz"},
    "daw_myalay": {"speed": "-10%", "pitch": "-8Hz"}
}

async def text_to_speech(text: str, output_path: str, voice_key: str, speed_override: str):
    voice = VOICE_MAPPING.get(voice_key, "my-MM-ThihaNeural")
    preset = VOICE_PITCH_SPEED.get(voice_key, {"speed": "+15%", "pitch": "+0Hz"})
    communicate = edge_tts.Communicate(text, voice, rate=speed_override or preset["speed"], pitch=preset["pitch"])
    await communicate.save(output_path)

def apply_text_blur(clip, blur_position="bottom", blur_size="medium"):
    intensity = 51 if blur_size == "large" else (35 if blur_size == "medium" else 21)
    def filter_frame(frame):
        h, w, _ = frame.shape
        blurred_frame = frame.copy()
        if blur_position == "bottom":
            y1, y2 = int(h * 0.75), h
        elif blur_position == "top":
            y1, y2 = 0, int(h * 0.25)
        else:
            y1, y2 = int(h * 0.35), int(h * 0.65)
        roi = frame[y1:y2, 0:w]
        blurred_frame[y1:y2, 0:w] = cv2.GaussianBlur(roi, (intensity, intensity), 0)
        return blurred_frame
    return clip.fl_image(filter_frame)

@app.get("/")
def home():
    return {"status": "ok", "message": "Recap Studio Active"}

@app.post("/process-recap")
async def process_recap(
    file: UploadFile = File(...),
    duration: int = Form(180),
    voice_speed: str = Form("+15%"),
    voice_type: str = Form("nyinyi"),
    tone_mood: str = Form("Dramatic"),
    pacing: str = Form("Fast"),
    include_outro: bool = Form(True)
):
    if not GENAI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY မရှိပါ။")

    input_video_path = f"temp_{file.filename}"
    output_video_path = f"recap_{file.filename}"
    audio_path = "temp_voice.mp3"

    with open(input_video_path, "wb") as f:
        f.write(await file.read())

    video_file = None
    try:
        video_file = genai.upload_file(path=input_video_path)
        while video_file.state.name == "PROCESSING":
            await asyncio.sleep(3)
            video_file = genai.get_file(video_file.name)

        outro_text = " 'History With Tarbin' မှ တင်ဆက်ပေးလိုက်တာဖြစ်ပါတယ်။" if include_outro else ""
        prompt = f"Analyze video, write Burmese movie recap script (~{duration}s audio duration). Mood: {tone_mood}, Pacing: {pacing}. Plain text only. End with: '{outro_text}'"

        model = genai.GenerativeModel(model_name="gemini-2.5-flash")
        response = model.generate_content([video_file, prompt])
        
        await text_to_speech(response.text, audio_path, voice_type, voice_speed)

        video_clip = VideoFileClip(input_video_path)
        audio_clip = AudioFileClip(audio_path)

        if video_clip.duration > duration:
            video_clip = video_clip.subclip(0, duration)

        final_video = video_clip.set_audio(audio_clip)
        final_video.write_videofile(output_video_path, codec="libx264", audio_codec="aac")

        video_clip.close()
        audio_clip.close()
        if video_file: genai.delete_file(video_file.name)
        if os.path.exists(input_video_path): os.remove(input_video_path)
        if os.path.exists(audio_path): os.remove(audio_path)

        return FileResponse(output_video_path, media_type="video/mp4", filename=output_video_path)
    except Exception as e:
        if video_file: genai.delete_file(video_file.name)
        if os.path.exists(input_video_path): os.remove(input_video_path)
        if os.path.exists(audio_path): os.remove(audio_path)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/apply-editor")
async def apply_editor(
    file: UploadFile = File(...),
    logo_file: UploadFile = File(None),
    enable_blur: bool = Form(False),
    blur_position: str = Form("bottom"),
    blur_size: str = Form("medium"),
    logo_position: str = Form("top-right"),
    logo_size: int = Form(80)
):
    input_video_path = f"edit_in_{file.filename}"
    output_video_path = f"edited_{file.filename}"
    logo_path = f"edit_logo_{logo_file.filename}" if logo_file else None

    with open(input_video_path, "wb") as f:
        f.write(await file.read())

    if logo_file:
        with open(logo_path, "wb") as f:
            f.write(await logo_file.read())

    try:
        video_clip = VideoFileClip(input_video_path)

        if enable_blur:
            video_clip = apply_text_blur(video_clip, blur_position, blur_size)

        final_elements = [video_clip]
        if logo_path and os.path.exists(logo_path):
            pos_map = {"top-left": ("left", "top"), "top-right": ("right", "top"), "bottom-left": ("left", "bottom"), "bottom-right": ("right", "bottom")}
            logo_clip = (ImageClip(logo_path)
                         .resize(width=logo_size)
                         .set_duration(video_clip.duration)
                         .set_position(pos_map.get(logo_position, ("right", "top"))))
            final_elements.append(logo_clip)

        final_video = CompositeVideoClip(final_elements)
        final_video.write_videofile(output_video_path, codec="libx264", audio_codec="aac")

        video_clip.close()
        if os.path.exists(input_video_path): os.remove(input_video_path)
        if logo_path and os.path.exists(logo_path): os.remove(logo_path)

        return FileResponse(output_video_path, media_type="video/mp4", filename=output_video_path)
    except Exception as e:
        if os.path.exists(input_video_path): os.remove(input_video_path)
        if logo_path and os.path.exists(logo_path): os.remove(logo_path)
        raise HTTPException(status_code=500, detail=str(e))
