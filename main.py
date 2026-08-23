import os
import asyncio
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import google.generativeai as genai
import edge_tts
from moviepy.editor import VideoFileClip, AudioFileClip

app = FastAPI()

# Cross-Origin Resource Sharing (CORS) ကို ခွင့်ပြုခြင်း
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Google AI Studio API Key ပြင်ရန်
GENAI_API_KEY = "AIzaSyBXOzwxUlTshVluPnlO-ERr3Y-zkTmYdac"
genai.configure(api_key=GENAI_API_KEY)

async def text_to_speech(text: str, output_path: str, voice: str = "my-MM-ThihaNeural", speed: str = "+15%"):
    communicate = edge_tts.Communicate(text, voice, rate=speed)
    await communicate.save(output_path)

@app.get("/")
def home():
    return {"status": "ok", "message": "Recap API Engine is active"}

@app.post("/process-video")
async def process_video(
    file: UploadFile = File(...),
    duration: int = Form(180),
    voice_speed: str = Form("+15%"),
    voice_type: str = Form("my-MM-ThihaNeural")
):
    input_video_path = f"temp_{file.filename}"
    output_video_path = f"recap_{file.filename}"
    audio_path = "temp_voice.mp3"

    # ဖိုင်သိမ်းဆည်းခြင်း
    with open(input_video_path, "wb") as f:
        f.write(await file.read())

    try:
        # ၁။ Gemini AI ဖြင့် ဗီဒီယို စစ်ဆေးပြီး Recap Script ထုတ်ခြင်း
        video_file = genai.upload_file(path=input_video_path)
        model = genai.GenerativeModel(model_name="gemini-2.5-flash")
        
        prompt = f"Analyze this video and generate a full movie recap script in Burmese language. The script content must match a narrative audio playback duration of approximately {duration} seconds."
        response = model.generate_content([video_file, prompt])
        recap_script = response.text

        # ၂။ Text to Speech အသံဖိုင် ဖန်တီးခြင်း
        await text_to_speech(recap_script, audio_path, voice=voice_type, speed=voice_speed)

        # ၃။ Video ဖြတ်တောက်ပြီး AI အသံဖြင့် ပြန်လည်ပေါင်းစပ်ခြင်း
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

        if os.path.exists(input_video_path):
            os.remove(input_video_path)
        if os.path.exists(audio_path):
            os.remove(audio_path)

        return FileResponse(output_video_path, media_type="video/mp4", filename=output_video_path)

    except Exception as e:
        return {"error": str(e)}
