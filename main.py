import logging
import sqlite3
import os
from datetime import datetime
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
import instaloader
import yt_dlp
import asyncio
from concurrent.futures import ThreadPoolExecutor

BOT_TOKEN = "8985773057:AAFaeT90Cg2WfoYHpdn75c-CYNwrDwv8ZnM"
ADMIN_ID = 8055210419
ALLOWED_USERS = [8055210419]
INSTAGRAM_USERNAME = "download_my_posts"
INSTAGRAM_PASSWORD = "parham1389"
DOWNLOAD_FOLDER = "downloads"

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.WARNING)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
executor = ThreadPoolExecutor(max_workers=2)

pending = {}

def init_database():
    conn = sqlite3.connect('instagram_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS usage_logs (
        id INTEGER PRIMARY KEY, user_id INTEGER, username TEXT, timestamp TEXT, 
        source TEXT, link TEXT)''')
    conn.commit()
    conn.close()

def download_instagram(url):
    try:
        L = instaloader.Instaloader()
        L.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
        if '/p/' in url:
            shortcode = url.split('/p/')[1].split('/')[0]
        elif '/reel/' in url:
            shortcode = url.split('/reel/')[1].split('/')[0]
        else:
            return None
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        download_folder = f"{DOWNLOAD_FOLDER}/{shortcode}"
        L.download_post(post, target=download_folder)
        return download_folder
    except Exception as e:
        logger.error(f"Instagram error: {e}")
        return None

def get_youtube_formats(url):
    try:
        ydl = yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True})
        info = ydl.extract_info(url, download=False)
        
        formats = []
        seen = set()
        
        for f in info.get('formats', []):
            if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                height = f.get('height', 0)
                fps = f.get('fps', 0)
                format_id = f.get('format_id')
                
                if height and format_id and height not in seen:
                    seen.add(height)
                    desc = f"{height}p"
                    if fps and fps > 30:
                        desc += f" ({int(fps)}fps)"
                    formats.append((height, format_id, desc))
        
        formats = sorted(formats, key=lambda x: x[0], reverse=True)
        return formats[:10]
    except:
        return []

def download_youtube(url, format_id):
    try:
        ydl_opts = {'format': format_id, 'outtmpl': f'{DOWNLOAD_FOLDER}/youtube/%(title)s.%(ext)s', 'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)
    except Exception as e:
        logger.error(f"YouTube error: {e}")
        return None

async def send_msg(chat_id, text):
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except:
        pass

async def polling_loop():
    init_database()
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    os.makedirs(f"{DOWNLOAD_FOLDER}/youtube", exist_ok=True)
    
    print("✅ ربات شروع شد\n")
    offset = 0
    
    try:
        while True:
            try:
                updates = await bot.get_updates(offset=offset, timeout=5)
                
                for update in updates:
                    offset = update.update_id + 1
                    
                    # Callback Query
                    if update.callback_query:
                        query = update.callback_query
                        chat_id = query.from_user.id
                        username = query.from_user.username or f"User_{chat_id}"
                        data = query.data
                        
                        if data.startswith('fmt_'):
                            parts = data.split('_')
                            format_id = '_'.join(parts[1:])
                            url = pending.get(f"yt_{chat_id}")
                            
                            if url:
                                await send_msg(chat_id, f"⏳ درحال دانلود...")
                                loop = asyncio.get_event_loop()
                                file = await loop.run_in_executor(executor, download_youtube, url, format_id)
                                
                                if file and os.path.exists(file):
                                    try:
                                        with open(file, 'rb') as f:
                                            await bot.send_video(chat_id=chat_id, video=f)
                                        await send_msg(chat_id, "✅ دانلود کامل!")
                                    except Exception as e:
                                        await send_msg(chat_id, f"❌ خطا: {str(e)[:50]}")
                                else:
                                    await send_msg(chat_id, "❌ خطا در دانلود")
                                
                                if f"yt_{chat_id}" in pending:
                                    del pending[f"yt_{chat_id}"]
                        
                        try:
                            await query.answer()
                        except:
                            pass
                    
                    # Text Message
                    elif update.message and update.message.text:
                        chat_id = update.effective_user.id
                        username = update.effective_user.username or f"User_{chat_id}"
                        text = update.message.text
                        
                        if chat_id not in ALLOWED_USERS:
                            await send_msg(chat_id, "❌ دسترسی ندارید")
                            continue
                        
                        if text == "/start":
                            await send_msg(chat_id, "🤖 لینک اینستا یا یوتیوب بفرست")
                        
                        elif "instagram.com" in text:
                            await send_msg(chat_id, "⏳ درحال دانلود...")
                            loop = asyncio.get_event_loop()
                            folder = await loop.run_in_executor(executor, download_instagram, text)
                            
                            if folder and os.path.exists(folder):
                                files = [f for f in os.listdir(folder) if f.endswith(('.mp4', '.jpg', '.png'))]
                                if files:
                                    for file in files[:3]:
                                        try:
                                            fpath = os.path.join(folder, file)
                                            if file.endswith('.mp4'):
                                                with open(fpath, 'rb') as f:
                                                    await bot.send_video(chat_id=chat_id, video=f)
                                            else:
                                                with open(fpath, 'rb') as f:
                                                    await bot.send_photo(chat_id=chat_id, photo=f)
                                        except:
                                            pass
                                    await send_msg(chat_id, "✅ دانلود کامل!")
                                else:
                                    await send_msg(chat_id, "❌ فایل یافت نشد")
                            else:
                                await send_msg(chat_id, "❌ خطا در دانلود")
                        
                        elif "youtube.com" in text or "youtu.be" in text:
                            await send_msg(chat_id, "⏳ درحال دریافت فرمت‌ها...")
                            loop = asyncio.get_event_loop()
                            formats = await loop.run_in_executor(executor, get_youtube_formats, text)
                            
                            if formats:
                                buttons = [[InlineKeyboardButton(f"📹 {desc}", callback_data=f"fmt_{fmt_id}")] 
                                          for h, fmt_id, desc in formats]
                                markup = InlineKeyboardMarkup(buttons)
                                await bot.send_message(chat_id=chat_id, text="فرمت انتخاب کنید:", reply_markup=markup)
                                pending[f"yt_{chat_id}"] = text
                            else:
                                await send_msg(chat_id, "❌ فرمتی پیدا نشد")
                        
                        elif text == "/stats" and chat_id == ADMIN_ID:
                            conn = sqlite3.connect('instagram_bot.db')
                            c = conn.cursor()
                            c.execute('SELECT COUNT(*) FROM usage_logs')
                            total = c.fetchone()[0]
                            conn.close()
                            await send_msg(chat_id, f"📊 کل دانلود‌ها: {total}")
                
                await asyncio.sleep(1)
            except Exception as e:
                print(f"❌ {e}")
                await asyncio.sleep(3)
    
    except KeyboardInterrupt:
        print("\n🛑 متوقف شد")

if __name__ == '__main__':
    asyncio.run(polling_loop())
