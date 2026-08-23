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

# ⚠️ သင့် Google AI Studio က API Key အမှန်ကို ဒီမှာ ထည့်ပေးပါ
GENAI_API_KEY = "AIzaSyCdNsTtFVmfTH7dgEbm56vhTxc3PwltswM"
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

    with open(input_video_path, "wb") as f:
        f.write(await file.read())

    try:
        # ၁။ Gemini AI ဖြင့် ဗီဒီယို စစ်ဆေးခြင်း
        video_file = genai.upload_file(path=input_video_path)
        model = genai.GenerativeModel(model_name="gemini-2.5-flash")
        
        prompt = f"Analyze this video and generate a full movie recap script in Burmese language. The audio length should match around {duration} seconds."
        response = model.generate_content([video_file, prompt])
        recap_script = response.text

        if not recap_script:
            raise Exception("Gemini AI မှ Script မထုတ်ပေးနိုင်ပါ။")

        # ၂။ Text to Speech အသံဖိုင် ဖန်တီးခြင်း
        await text_to_speech(recap_script, audio_path, voice=voice_type, speed=voice_speed)

        # ၃။ Video ဖြတ်တောက်ပြီး ပြန်လည်ပေါင်းစပ်ခြင်း
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

        if os.path.exists(input_video_path): os.remove(input_video_path)
        if os.path.exists(audio_path): os.remove(audio_path)

        return FileResponse(output_video_path, media_type="video/mp4", filename=output_video_path)

    except Exception as e:
        # ယာယီဖိုင်များ ဖျက်ခြင်း
        if os.path.exists(input_video_path): os.remove(input_video_path)
        if os.path.exists(audio_path): os.remove(audio_path)
        raise HTTPException(status_code=500, detail=str(e))
