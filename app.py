import asyncio
import os
import re
from pyrogram import Client, filters
from telegram import Bot
from telegram.constants import ParseMode

# استيراد الدوال والمتغيرات من ملفك الأساسي (iib.py)
# استورد من الملف الجديد بدلاً من iib.py
from config import get_db_connection, normalize_text, CITIES_DISTRICTS, BOT_TOKEN

from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot is Running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- الإعدادات ---
API_ID = "36360458"
API_HASH = "daae4628b4b4aac1f0ebfce23c4fa272"

# كلمات تدل على وجود طلب (تم توسيعها وترتيبها)
KEYWORDS = [
    "مشوار", "توصيل", "تكسي", "تاكسي", "مطلوب", "محتاج", "سواقه", "سواق", 
    "سياره", "اوصل", "يوصلني", "اروح", "نقل", "طلبية", "اغراض", "توصيله", 
    "ناقصني", "مندوب", "ابغى", "ابي", "يوصل", "فاضي", "مين يوصل", 
    "الاياب", "الذهاب", "نقل عفش", "دباب"
]

# كلمات استبعادية لمنع الإعلانات المزعجة
EXCLUDED_WORDS = [
    "موجود الان", "تواصل معي", "انا كابتن", "سيارتي", "جاهز للتوصيل", 
    "عروض", "خصم", "للايجار", "وظائف", "تأجير"
]

# تعريف العميل والبوت
user_app = Client("user_session", api_id=API_ID, api_hash=API_HASH)
bot_sender = Bot(token=BOT_TOKEN)

# في ملف scraper.py - تعديل الهاندلر ليكون عاماً
@user_app.on_message(filters.group & ~filters.service)
async def scan_groups(client, message):
    if not message.text:
        return

    # طباعة في Termux للتأكد أن الرقم يرى الرسائل
    print(f"📥 رسالة جديدة من مجموعة: {message.chat.title}")

    text_clean = normalize_text(message.text)

    # 1. استبعاد رسائل الكباتن/الإعلانات
    if any(ex in text_clean for ex in EXCLUDED_WORDS):
        return

    # 2. البحث عن الكلمات المفتاحية (مشوار، توصيل...)
    if any(key in text_clean for key in KEYWORDS):
        found_district = None
        found_city = None
        
        # 3. البحث عن الحي في الرسالة
        for city, districts in CITIES_DISTRICTS.items():
            for district in districts:
                if normalize_text(district) in text_clean:
                    found_district = district
                    found_city = city
                    break
            if found_district: break
        
        # 4. إذا وجد حي، يتم التحويل فوراً للسائقين عبر البوت
        if found_district:
            print(f"✅ تم اكتشاف طلب في حي: {found_district}")
            await notify_drivers_by_district(found_city, found_district, message)

async def notify_drivers_by_district(city, district, original_msg):
    conn = get_db_connection()
    if not conn: return
    
    drivers = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id FROM users WHERE role = 'driver' AND districts ILIKE %s",
                (f"%{district}%",)
            )
            drivers = [row[0] for row in cur.fetchall()]
    except Exception as e:
        print(f"❌ خطأ في قاعدة البيانات: {e}")
    finally:
        conn.close()

    if not drivers: return

    # --- التعديل هنا لفتح خاص العميل مباشرة ---
    customer = original_msg.from_user
    
    # إذا كان لدى العميل "اسم مستخدم" (Username) نستخدمه، وإلا نستخدم الـ ID الخاص به
    if customer.username:
        customer_link = f"https://t.me/{customer.username}"
    else:
        customer_link = f"tg://user?id={customer.id}"
    
    alert_text = (
        f"🚨 **طلب مشوار جديد!**\n\n"
        f"📍 **الحي:** {district} ({city})\n"
        f"👤 **العميل:** {customer.first_name}\n"
        f"📝 **الطلب:**\n_{original_msg.text}_\n\n"
        f"📥 [اضغط هنا لمراسلة العميل خاص]({customer_link})"
    )

    for d_id in drivers:
        try:
            await bot_sender.send_message(
                chat_id=d_id, 
                text=alert_text, 
                parse_mode=ParseMode.MARKDOWN
            )
            await asyncio.sleep(0.05)
        except: continue
    # إرسال الرسالة للسائقين المشتركين
    for d_id in drivers:
        try:
            await bot_sender.send_message(
                chat_id=d_id,
                text=alert_text,
                parse_mode=ParseMode.MARKDOWN
            )
            await asyncio.sleep(0.05) # حماية من السبام
        except Exception:
            continue

async def run_scraper():
    print("🚀 جاري تشغيل الرادار وتحديث بيانات المجموعات...")
    await user_app.start()
    
    # هذه الخطوة ستحل مشكلة "Peer id invalid" للأبد
    # تقوم بجلب المجموعات المشترك فيها الحساب وتخزينها في ملف الجلسة
    print("🔄 جاري مزامنة المجموعات، يرجى الانتظار...")
    async for dialog in user_app.get_dialogs():
        pass  # مجرد المرور عليها يكفي لتخزين بياناتها
        
    print("✅ تم التنشيط! الرادار يراقب جميع المجموعات الآن...")
    
    # إبقاء السكرابر يعمل باستمرار
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(run_scraper())
    except KeyboardInterrupt:
        print("👋 تم إيقاف الرادار.")
