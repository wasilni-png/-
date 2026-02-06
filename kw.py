import asyncio
import threading
import sys
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pyrogram import Client
from telegram import Bot
from telegram.constants import ParseMode
import google.generativeai as genai

# --- محاولة استيراد الإعدادات من ملف config.py ---
try:
    from config import normalize_text, CITIES_DISTRICTS, BOT_TOKEN, get_db_connection
    print("✅ تم تحميل ملف config.py بنجاح")
except Exception as e:
    print(f"❌ خطأ في تحميل ملف config.py: {e}")
    sys.exit(1)

# --- إعدادات الحساب (API & Session) ---
API_ID = "36360458"
API_HASH = "daae4628b4b4aac1f0ebfce23c4fa272"
SESSION_STRING = "BAIq0QoApqDmvNIHZnbO2VxSWBdRlJ5SP7S19VeM7rV0Umjc1mO70IQx-Un7FdoYE27YpogRdiB-KXmzvk1zZl_u_CZSC7mQ7M7XdGrpIDvhhAhxVacbpIPary3Zh9J36X1hCZgBhpX9qneOiGxzQcGBdF7XMfsFdYI6_Be2hiPoKUFMtLflsrnWmLCNkKJFhylzubFLMX9KMzn7VnUG5rI9xCfDEae0emFjPA1FqysJV3P2ehe-HanA6GpaIxGOoDGOv_IyyySHFb0UAP4i19Xm5-i5SHUZNiT8e72DX1SLZn40Z5XRgEIdTrfoHDyyOfqvT676UlOLJHiHzQ0c06u6RvPMvAAAAAH-ZrzOAA"

# --- إعداد الذكاء الاصطناعي (Gemini) ---
# ملاحظة: يفضل استخدام gemini-2.0-flash لسرعة أكبر ودقة أعلى في عام 2026
genai.configure(api_key="AIzaSyDvEF8WDhGt6nDWjqxgix0Rb8qaAmtEPbk")
ai_model = genai.GenerativeModel('gemini-1.5-flash')

# --- الكلمات المستبعدة فوراً ---
DRIVER_KEYWORDS = ["متواجد", "متاح", "شغال", "جاهز", "أسعارنا", "يوجد لدينا", "سيارة نظيفة", "نقل عفش", "دربك سمح"]

user_app = Client("my_session", session_string=SESSION_STRING, api_id=API_ID, api_hash=API_HASH)
bot_sender = Bot(token=BOT_TOKEN)

# --- وظيفة الذكاء الاصطناعي المتطورة ---
async def ai_analyze_message(text):
    if not text or len(text.strip()) < 5: return False
    
    if any(word in text for word in DRIVER_KEYWORDS):
        return False

    prompt = f"""
    حلل نية المرسل في الرسالة التالية بدقة: "{text}"
    القواعد:
    - إذا كان المرسل (زبون) يطلب خدمة توصيل ركاب أو طلبات (مثال: محتاج سواق، مين يوصلني، ابي مشوار، عندي غرض): رد بـ YES.
    - إذا كان المرسل (سائق) يعرض خدمته أو يسولف (مثال: متواجد، أنا أوصل، تم التوصيل): رد بـ NO.
    رد بكلمة واحدة فقط: YES أو NO.
    """
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: ai_model.generate_content(prompt))
        answer = response.text.strip().upper()
        return "YES" in answer
    except Exception as e:
        print(f"⚠️ خطأ في تحليل AI: {e}")
        return "مشوار" in text or "توصيل" in text

# --- إرسال الإشعار للسائقين ---
async def notify_drivers(district, original_msg):
    content = original_msg.text or original_msg.caption
    if not content: return

    conn = get_db_connection()
    if not conn: return
    
    try:
        search_term = normalize_text(district)
        with conn.cursor() as cur:
            # 🟢 التعديل: جلب السائقين المشتركين، غير المحظورين، والنشطين فقط
            cur.execute(
                """
                SELECT user_id FROM users 
                WHERE role = 'driver' 
                AND is_blocked = FALSE 
                AND subscription_expiry > NOW()
                AND (REPLACE(REPLACE(districts, 'ة', 'ه'), 'ال', '') ILIKE %s)
                """,
                (f"%{search_term}%",)
            )
            drivers = [row[0] for row in cur.fetchall()]

        if not drivers: 
            return

        customer = original_msg.from_user
        customer_name = customer.first_name if customer.first_name else "عميل"
        # تأمين الرابط
        customer_link = f"tg://user?id={customer.id}" if not customer.username else f"https://t.me/{customer.username}"

        safe_text = content.replace("_", "-").replace("*", "").replace("`", "")

        alert_text = (
            f"🤖 **طلب مشوار ذكي (للمشتركين)**\n\n"
            f"📍 **الحي:** {district}\n"
            f"👤 **العميل:** {customer_name}\n"
            f"📝 **الطلب:**\n_{safe_text}_\n\n"
            f"📥 [اضغط هنا لمراسلة العميل خاص]({customer_link})"
        )

        # إرسال الرسائل
        for d_id in drivers:
            try:
                await bot_sender.send_message(chat_id=d_id, text=alert_text, parse_mode=ParseMode.MARKDOWN)
            except: 
                continue
                
        print(f"✅ تم تحويل طلب في {district} لـ {len(drivers)} سائق مشترك.")
    except Exception as e:
        print(f"❌ خطأ إرسال في notify_drivers: {e}")
    finally:
        # ⚠️ تغيير جوهري: إعادة الاتصال للمجمع بدلاً من إغلاقه نهائياً
        release_db_connection(conn)

# --- المحرك الرئيسي للرادار ---
async def start_radar():
    await user_app.start()
    me = await user_app.get_me()
    print(f"✅ تم تسجيل الدخول باسم: {me.first_name}")

    monitored_chats = []
    async for dialog in user_app.get_dialogs(limit=50):
        if "GROUP" in str(dialog.chat.type).upper():
            monitored_chats.append({"id": dialog.chat.id, "title": dialog.chat.title})

    print(f"📡 مراقبة نشطة لـ ({len(monitored_chats)}) مجموعة.")

    last_id = {}
    for chat in monitored_chats:
        try:
            async for msg in user_app.get_chat_history(chat["id"], limit=1):
                last_id[chat["id"]] = msg.id
        except:
            last_id[chat["id"]] = 0

    while True:
        for chat in monitored_chats:
            try:
                async for msg in user_app.get_chat_history(chat["id"], limit=1):
                    if msg.id > last_id.get(chat["id"], 0):
                        last_id[chat["id"]] = msg.id

                        # فحص النص والوسائط بشكل آمن
                        text_to_analyze = msg.text or msg.caption
                        if not text_to_analyze or (msg.from_user and msg.from_user.id == me.id):
                            continue

                        if await ai_analyze_message(text_to_analyze):
                            print(f"🧠 AI: تأكيد طلب حقيقي في [{chat['title']}]")
                            text_c = normalize_text(text_to_analyze)
                            for city, districts in CITIES_DISTRICTS.items():
                                for d in districts:
                                    if normalize_text(d) in text_c:
                                        await notify_drivers(d, msg)
                                        break

                await asyncio.sleep(0.5)
            except Exception as e:
                if "420" in str(e): await asyncio.sleep(15)
                continue
        await asyncio.sleep(2)

# --- خادم الويب ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(b"AI Radar is Live")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    threading.Thread(target=lambda: HTTPServer(('0.0.0.0', port), HealthCheckHandler).serve_forever(), daemon=True).start()
    asyncio.run(start_radar())
