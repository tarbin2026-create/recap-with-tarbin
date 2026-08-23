import os
import asyncio
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import google.generativeai as genai
import edge_tts
from moviepy.editor import VideoFileClip, AudioFileClip

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

# Voice Mapping Configuration (Microsoft Edge TTS Engine)
VOICE_MAPPING = {
    "koko": "my-MM-ThihaNeural",       # တည်ငြိမ်တဲ့ အမျိုးသားသံ
    "nyinyi": "my-MM-ThihaNeural",     # Recap ပြောတဲ့ အမျိုးသားသံ
    "maungmaung": "my-MM-ThihaNeural", # စိတ်ခံစားမှု အမျိုးသားသံ
    "u_paing": "my-MM-ThihaNeural",    # လူကြီးအသံ (အမျိုးသား)
    "hlahla": "my-MM-NilarNeural",     # တည်ငြိမ်တဲ့ အမျိုးသမီးသံ
    "myamya": "my-MM-NilarNeural",     # Recap ပြောတဲ့ အမျိုးသမီးသံ
    "yuya": "my-MM-NilarNeural",       # စိတ်ခံစားမှု အမျိုးသမီးသံ
    "daw_myalay": "my-MM-NilarNeural"  # လူကြီးအသံ (အမျိုးသမီး)
}

# Voice Speed Parameters setup for emotional nuances
VOICE_PITCH_SPEED = {
    "koko": {"speed": "+0%", "pitch": "-5Hz"},
    "nyinyi": {"speed": "+15%", "pitch": "+0Hz"},
    "maungmaung": {"speed": "+10%", "pitch": "-2Hz"},
    "u_paing": {"speed": "-10%", "pitch": "-10Hz"},
    "hlahla": {"speed": "+0%", "pitch": "-2Hz"},
    "myamya": {"speed": "+15%", "pitch": "+0Hz"},
    "yuya": {"speed": "+10%", "pitch": "+3Hz"},
    "daw_myalay": {"speed": "-10%", "pitch": "-8Hz"},
}

async def text_to_speech(text: str, output_path: str, voice_key: str, speed_override: str):
    voice = VOICE_MAPPING.get(voice_key, "my-MM-ThihaNeural")
    preset = VOICE_PITCH_SPEED.get(voice_key, {"speed": "+15%", "pitch": "+0Hz"})
    
    # Use user speed override if provided, else use preset speed
    chosen_speed = speed_override if speed_override else preset["speed"]
    pitch = preset["pitch"]

    communicate = edge_tts.Communicate(text, voice, rate=chosen_speed, pitch=pitch)
    await communicate.save(output_path)

@app.get("/")
def home():
    return {"status": "ok", "message": "Recap with Tarbin Studio Engine active"}

@app.post("/process-video")
async def process_video(
    file: UploadFile = File(...),
    duration: int = Form(180),
    voice_speed: str = Form("+15%"),
    voice_type: str = Form("nyinyi"),
    tone_mood: str = Form("dramatic"),
    pacing: str = Form("fast"),
    include_outro: bool = Form(True)
):
    if not GENAI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY ကို Render Environment Variables တွင် ထည့်သွင်းမထားပါ။")

    input_video_path = f"temp_{file.filename}"
    output_video_path = f"recap_{file.filename}"
    audio_path = "temp_voice.mp3"

    with open(input_video_path, "wb") as f:
        f.write(await file.read())

    video_file = None
    try:
        # 1. Video Upload to Gemini File API
        video_file = genai.upload_file(path=input_video_path)
        
        # Poll state until ACTIVE
        while video_file.state.name == "PROCESSING":
            await asyncio.sleep(4)
            video_file = genai.get_file(video_file.name)
            
        if video_file.state.name != "ACTIVE":
            raise Exception(f"ဗီဒီယိုဖိုင် စီစစ်မှု အဆင်မပြေပါ (State: {video_file.state.name})")

        # 2. Prompt Builder with Tone & Mood Studio Customization
        outro_text = " 'History With Tarbin' မှ တင်ဆက်ပေးလိုက်တာဖြစ်ပါတယ်။ ကြည့်ရှုပေးတဲ့အတွက် ကျေးဇူးတင်ပါတယ်။" if include_outro else ""
        
        prompt = f"""
        Analyze this video and generate a professional movie recap script in Burmese language.
        Requirements:
        - Script Duration Target: Match audio narrative pace for approximately {duration} seconds.
        - Tone & Mood Style: {tone_mood} (e.g., dramatic suspenseful, humorous comedy, documentary style, mysterious thriller).
        - Narrative Pacing: {pacing}.
        - Do NOT include scene descriptions, timestamps, or technical brackets like [Music Starts]. Provide ONLY the spoken Burmese monologue text.
        - Outro: End the script with this phrase: "{outro_text}"
        """

        model = genai.GenerativeModel(model_name="gemini-2.5-flash")
        response = model.generate_content([video_file, prompt])
        recap_script = response.text

        if not recap_script:
            raise Exception("Gemini AI မှ Script မထုတ်ပေးနိုင်ပါ။")

        # 3. Audio Synthesis
        await text_to_speech(recap_script, audio_path, voice_key=voice_type, speed_override=voice_speed)

        # 4. Video & Audio Sync Processing
        video_clip = VideoFileClip(input_video_path)
        audio_clip = AudioFileClip(audio_path)

        if video_clip.duration > duration:
            final_video = video_clip.subclip(0, duration)
        else:
            final_video = video_clip

        final_video = final_video.set_audio(audio_clip)
        final_video.write_videofile(output_video_path, codec="libx264", audio_codec="aac")

        video_clip.close()
        audio_clip.close()

        # Clean Up Google Drive/File Storage
        if video_file:
            try:
                genai.delete_file(video_file.name)
            except:
                pass

        if os.path.exists(input_video_path): os.remove(input_video_path)
        if os.path.exists(audio_path): os.remove(audio_path)

        return FileResponse(output_video_path, media_type="video/mp4", filename=output_video_path)

    except Exception as e:
        if video_file:
            try:
                genai.delete_file(video_file.name)
            except:
                pass
        if os.path.exists(input_video_path): os.remove(input_video_path)
        if os.path.exists(audio_path): os.remove(audio_path)
        raise HTTPException(status_code=500, detail=str(e))
