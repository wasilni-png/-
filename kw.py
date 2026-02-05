import os
import asyncio
import random
import glob
from flask import Flask
from threading import Thread
from telethon import TelegramClient

# ==========================================
# 1. إعدادات السيرفر (Flask) لـ Render
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "✅ System is Running! | Telegram Auto-Sender"

def run_flask():
    # ريندر يرسل المنفذ تلقائياً، أو نستخدم 10000 كبديل
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# ==========================================
# 2. إعدادات التليجرام (الثابتة)
# ==========================================
# يمكنك استخدام نفس الـ API لجميع الحسابات
API_ID = 33888256
API_HASH = 'bb1902689a7e203a7aedadb806c08854'

# نص الإعلان الموحد
AD_MESSAGE = """
<b>🌟 التميز والاحترافية لخدمتكم 🌟</b>

<b>✅ خدمات النقل:</b>
• توفير سائقين بالشهر (للمشاوير الجامعية والدوامات) 🚗

<b>✅ الخدمات الأكاديمية والتعليمية:</b>
• حل جميع الواجبات والبحوثات العلمية 📚
• إعداد الأطروحات وملفات الأداء الوظيفي للمعلمات 👩‍🏫

<b>✅ التوظيف والمهنة:</b>
• تصميم سيرة ذاتية احترافية بنظام <b>ATS</b> العالمي 📄
<i>(لضمان قبولك في أنظمة الفرز الآلي للشركات)</i>

──────────────────
📞 <b>للتواصل والاستفسار (اتصال أو واتساب):</b>
<code>0566187430</code>
"""

# ==========================================
# 3. وظيفة عمل البوت (لكل حساب)
# ==========================================
async def run_worker(session_file):
    """
    هذه الدالة تأخذ اسم ملف الجلسة وتقوم بتشغيل البوت الخاص به
    """
    # استخراج اسم الجلسة بدون الامتداد .session
    session_name = os.path.splitext(session_file)[0]
    
    try:
        # receive_updates=False ضروري جداً لتفادي أخطاء Render
        client = TelegramClient(session_name, API_ID, API_HASH, receive_updates=False)
        
        print(f"🔌 جاري اتصال الحساب: {session_name}...")
        await client.start()
        
        # جلب معلومات الحساب للتأكد
        me = await client.get_me()
        bot_name = me.first_name
        print(f"✅ تم دخول الحساب بنجاح: {bot_name}")

        # حلقة العمل اللانهائية
        while True:
            try:
                # 1. جلب المجموعات
                groups = []
                async for dialog in client.iter_dialogs():
                    if dialog.is_group:
                        groups.append(dialog)
                
                print(f"📊 [{bot_name}] وجد {len(groups)} مجموعة. جاري البدء...")
                
                # 2. تقسيم المجموعات (2 في كل مرة)
                for i in range(0, len(groups), 2):
                    batch = groups[i:i+2]
                    
                    for group in batch:
                        try:
                            await client.send_message(group, AD_MESSAGE, parse_mode='html')
                            print(f"✔️ [{bot_name}] أرسل لـ: {group.title}")
                        except Exception as e:
                            print(f"⚠️ [{bot_name}] فشل في {group.title}: {e}")
                            await asyncio.sleep(5) # انتظار بسيط عند الخطأ
                    
                    # 3. الانتظار العشوائي بين الدفعات (لمنع الحظر)
                    wait = random.randint(60, 120)
                    print(f"⏳ [{bot_name}] استراحة {wait} ثانية...")
                    await asyncio.sleep(wait)
                
                # 4. نهاية القائمة والانتظار الطويل
                print(f"🏁 [{bot_name}] أنهى القائمة. سيعود بعد 10 دقائق...")
                await asyncio.sleep(600)

            except Exception as e:
                print(f"❌ خطأ عام في دورة [{bot_name}]: {e}")
                await asyncio.sleep(60) # انتظار دقيقة قبل إعادة المحاولة

    except Exception as e:
        print(f"🚫 فشل تشغيل ملف الجلسة {session_name}: {e}")

# ==========================================
# 4. المشغل الرئيسي (Main)
# ==========================================
async def main():
    # البحث عن كل ملفات .session في المجلد
    session_files = glob.glob("*.session")
    
    if not session_files:
        print("❌ لم يتم العثور على أي ملفات .session! الرجاء رفع الملفات أولاً.")
        return

    print(f"📂 تم العثور على {len(session_files)} ملفات جلسة. جاري التشغيل...")
    
    # إنشاء مهمة مستقلة لكل ملف جلسة
    tasks = [run_worker(file) for file in session_files]
    
    # تشغيلهم جميعاً في وقت واحد
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    # تشغيل سيرفر الويب في الخلفية
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    
    # تشغيل البوتات
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
