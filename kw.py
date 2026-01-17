#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import threading
import os
import re
import urllib.parse  # أضف هذا الاستيراد في أعلى الملف
from datetime import datetime
from math import radians, cos, sin, asin, sqrt
from enum import Enum

# مكتبات Flask والويب
from flask import Flask

# مكتبات قاعدة البيانات
import psycopg2
from psycopg2.extras import RealDictCursor

# مكتبات تليجرام
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from telegram.constants import ParseMode
from telegram.ext import ApplicationHandlerStop
from telegram.request import HTTPXRequest
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import MessageHandler, filters, ContextTypes
# إعداد السيرفر لـ Render
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive! 🚀"

 # تأكد من وجود هذا الاستيراد في أعلى الملف

def run_flask():
    # جلب المنفذ من ريندر، وإذا لم يوجد يستخدم 8080 كاحتياطي
    port = int(os.environ.get("PORT", 8080))
    # host='0.0.0.0' ضرورية جداً ليتمكن ريندر من رؤية السيرفر
    app.run(host='0.0.0.0', port=port)


# ==================== ⚙️ 1. الإعدادات ====================

# 🔴🔴 هام: بيانات الاتصال (يفضل وضعها في متغيرات بيئة لاحقاً)
DB_URL = "postgresql://postgres.nmteaqxrtcegxmgvsbzr:mohammedfahdypb@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"
BOT_TOKEN = "8531219319:AAFZREyQum0t85NtVlaxw3PPrkW_4D_8iaU"
# آيدي المشرفين
ADMIN_IDS = [8563113166, 7996171713, 7580027135]

# الكلمات المفتاحية للبحث في المجموعات
KEYWORDS = ["مشوار", "توصيل", "سائق", "كابتن", "سيارة", "وينك", "متاح", "مطلوب", "ابي", "بغيت"]
# --- 1. إعدادات الأحياء الذكية ---
# --- 1. إعدادات الأحياء الذكية (المدينة المنورة) ---
CITIES_DISTRICTS = {
    "المدينة المنورة": [
        "الإسكان", "البحر", "البدراني", "الجرف", 
        "الحزام", "الحمراء", "الخالدية", "الدويخي", 
        "الرانوناء", "الشروق", "الشرق", "العاقول", 
        "العريض", "العزيزية", "العنابس", "القبلتين", 
        "الملك فهد", "المطار", "المغيسله", "الهجرة", 
        "باقدو", "بني حارثة", "حديقة الملك فهد", "سيد الشهداء", 
        "شوران", "قباء", "مهزور"
    ]
}



# الذاكرة المؤقتة (Cache)
USER_CACHE = {}         # لتسريع استجابة البوت
CACHED_DRIVERS = []     # قائمة الكباتن للبحث السريع
LAST_CACHE_SYNC = datetime.min

# إعداد السجل (Logging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== 🗄️ 2. قاعدة البيانات ====================

def get_db_connection():
    try:
        conn = psycopg2.connect(DB_URL)
        return conn
    except Exception as e:
        print(f"❌ فشل الاتصال بقاعدة البيانات: {e}")
        return None

def init_db():
    """إنشاء الجداول وتحديث الأعمدة الناقصة"""
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            # إنشاء الجدول الأساسي

            # إنشاء جدول سجلات الدردشة
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_logs (
                    log_id SERIAL PRIMARY KEY,
                    sender_id BIGINT,
                    receiver_id BIGINT,
                    message_content TEXT,
                    msg_type TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    chat_id BIGINT,
                    role TEXT,
                    name TEXT,
                    phone TEXT,
                    car_info TEXT,
                    districts TEXT,
                    lat FLOAT DEFAULT 0.0,
                    lon FLOAT DEFAULT 0.0,
                    is_blocked BOOLEAN DEFAULT FALSE,
                    is_verified BOOLEAN DEFAULT FALSE,
                    subscription_expiry TIMESTAMPTZ,
                    balance FLOAT DEFAULT 0.0
                );
            """)
            # التأكد من وجود عمود الرصيد (للتحديثات القديمة)
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS balance FLOAT DEFAULT 0.0;")
            conn.commit()
            # ... (بعد إنشاء جدول users)

            # إنشاء جدول المحادثات النشطة
            cur.execute("""
                CREATE TABLE IF NOT EXISTS active_chats (
                    user_id BIGINT PRIMARY KEY,
                    partner_id BIGINT,
                    start_time TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            conn.commit()

            print("✅ قاعدة البيانات جاهزة.")
    except Exception as e:
        print(f"❌ خطأ في تهيئة قاعدة البيانات: {e}")
    finally:
        conn.close()

# ==================== 🛠️ 3. دوال مساعدة ====================

class UserRole(str, Enum):
    RIDER = "rider"
    DRIVER = "driver"

def get_distance(lat1, lon1, lat2, lon2):
    """حساب المسافة بين نقطتين (Haversine Formula)"""
    if any(v is None for v in [lat1, lon1, lat2, lon2]):
        return 999999
    try:
        lon1, lat1, lon2, lat2 = map(radians, [float(lon1), float(lat1), float(lon2), float(lat2)])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        return 6371 * 2 * asin(sqrt(a))
    except (ValueError, TypeError):
        return 999999

def update_db_location(user_id, lat, lon):
    """دالة مساعدة لتحديث موقع المستخدم في الخلفية"""
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            # تحديث الإحداثيات للمستخدم
            cur.execute("UPDATE users SET lat = %s, lon = %s WHERE user_id = %s", (lat, lon, user_id))
            conn.commit()
    except Exception as e:
        print(f"Error updating location for {user_id}: {e}")
    finally:
        conn.close()

def update_districts_in_db(user_id, districts_str):
    """تحديث عمود الأحياء في سوبابيز"""
    conn = get_db_connection()
    if not conn: return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET districts = %s WHERE user_id = %s",
                (districts_str, user_id)
            )
            conn.commit()
        return True
    except Exception as e:
        print(f"❌ خطأ تحديث الأحياء: {e}")
        return False
    finally:
        conn.close()




async def sync_all_users():
    """تحديث الذاكرة المؤقتة من قاعدة البيانات"""
    global USER_CACHE, CACHED_DRIVERS, LAST_CACHE_SYNC
    if (datetime.now() - LAST_CACHE_SYNC).total_seconds() < 120:
        return

    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users")
            all_users = cur.fetchall()

            USER_CACHE = {u['user_id']: u for u in all_users}
            CACHED_DRIVERS = [u for u in all_users if u['role'] == 'driver']

            LAST_CACHE_SYNC = datetime.now()
            # print(f"⚡ تم تحديث الذاكرة: {len(CACHED_DRIVERS)} كابتن.")
    finally:
        conn.close()
# --- دوال الدردشة الوسيطة ---

def start_chat_session(user1_id, user2_id):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            # ربط الطرف الأول بالثاني
            cur.execute("""
                INSERT INTO active_chats (user_id, partner_id) 
                VALUES (%s, %s), (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET partner_id = EXCLUDED.partner_id
            """, (user1_id, user2_id, user2_id, user1_id))
            conn.commit()
    finally:
        conn.close()

def end_chat_session(user_id):
    """إنهاء المحادثة وحذف الارتباط"""
    conn = get_db_connection()
    partner_id = None
    if not conn: return None
    try:
        with conn.cursor() as cur:
            # معرفة الطرف الآخر لإبلاغه
            cur.execute("SELECT partner_id FROM active_chats WHERE user_id = %s", (user_id,))
            res = cur.fetchone()
            if res:
                partner_id = res[0]

            # حذف السجلات للطرفين
            cur.execute("DELETE FROM active_chats WHERE user_id = %s OR partner_id = %s", (user_id, user_id))
            conn.commit()
    finally:
        conn.close()
    return partner_id

def get_chat_partner(user_id):
    """جلب آيدي الطرف الآخر في المحادثة"""
    conn = get_db_connection()
    if not conn: return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT partner_id FROM active_chats WHERE user_id = %s", (user_id,))
            res = cur.fetchone()
            return res[0] if res else None
    finally:
        conn.close()


def get_main_kb(role, is_verified=True):
    """لوحة المفاتيح الرئيسية حسب الرتبة"""
    if role == "driver":
        if not is_verified:
            return ReplyKeyboardMarkup([[KeyboardButton("⏳ الحساب قيد المراجعة")]], resize_keyboard=True)
        return ReplyKeyboardMarkup([
            [KeyboardButton("📍 تحديث موقعي"), KeyboardButton("📝 تحديث الأحياء")],
            [KeyboardButton("💰 محفظتي"), KeyboardButton("ℹ️ حالة اشتراكي")],
            [KeyboardButton("📞 تواصل مع الإدارة")] # تم إضافة الزر هنا
        ], resize_keyboard=True)

     # للراكب
    return ReplyKeyboardMarkup([
        [KeyboardButton("🚖 طلب رحلة"), KeyboardButton("📍 موقعي")],
        [KeyboardButton("💰 محفظتي"), KeyboardButton("📞 تواصل مع الإدارة")] # تم إضافة الزر هنا
    ], resize_keyboard=True)
# ==================== 🤖 4. المعالجات (Handlers) ====================

async def send_fancy_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    # رابط فيديو قصير (يمكنك استبداله برابط مباشر لملف MP4 أو معرف ملف على تليجرام)
    video_url = "https://example.com/your_promo_video.mp4" 
    
    welcome_text = (
        "🚀 **أهلاً بك في بوت مشواري للتوصيل الذكي!**\n\n"
        "يسعدنا انضمامك إلينا. المنصة الأسهل لربط الكباتن بالركاب في المدينة المنورة.\n\n"
        "📺 شاهد الفيديو القصير أعلاه لمعرفة كيفية الطلب.\n"
        "─────────────────\n"
        "👇 للبدء أو للاستفسار، استخدم الأزرار أدناه:"
    )

    # إنشاء الأزرار (البوت والإدارة)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🤖 ابدأ استخدام البوت", url="https://t.me/Fogtyjnbot"),
            InlineKeyboardButton("👨‍💻 تواصل مع الإدارة", url="https://t.me/YourAdminUserne")
        ]
    ])

    # إرسال الفيديو مع النص والأزرار
    try:
        await context.bot.send_video(
            chat_id=chat_id,
            video=video_url,
            caption=welcome_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        # في حال فشل إرسال الفيديو، أرسل النص فقط
        await context.bot.send_message(
            chat_id=chat_id,
            text=welcome_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )

# لا تنسى إضافة Handler لهذا الأمر في دالة main
# application.add_handler(CommandHandler("welcome", send_fancy_welcome))



async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    context.user_data.clear() # تصفير أي حالة قديمة لضمان عدم تعليق البوت

    # 1. فحص إذا كان الدخول عبر رابط طلب مشوار (Deep Link) قادم من القروب
    if context.args and len(context.args) > 0:
        arg_value = context.args[0]

        # التعامل مع روابط الطلب (سواء بدأت بـ order_ أو req_)
        if arg_value.startswith("order_") or arg_value.startswith("req_"):
            try:
                # 🔓 فك تشفير الرابط (لحل مشكلة الأسماء العربية مثل القبلتين)
                decoded_args = urllib.parse.unquote(arg_value)
                parts = decoded_args.split("_")

                if len(parts) >= 3:
                    driver_id = parts[1]
                    # دمج الأجزاء المتبقية في حال كان اسم الحي يحتوي على "_"
                    dist_name = "_".join(parts[2:]) 

                    context.user_data.update({
                        'driver_to_order': driver_id,
                        'order_dist': dist_name,
                        'state': 'WAIT_TRIP_DETAILS'
                    })

                    await update.message.reply_text(
                        f"👋 أهلاً بك يا {first_name}\n\n"
                        f"📍 أنت تطلب كابتن في حي: **{dist_name}**\n"
                        "─────────────────\n"
                        "📝 **يرجى كتابة تفاصيل مشوارك الآن:**\n"
                        "(مثلاً: من شارع المطار إلى الراشد مول الساعة 9 مساءً)",
                        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ إلغاء الطلب")]], resize_keyboard=True),
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return # إنهاء الدالة هنا لضمان عدم ظهور رسالة الترحيب العادية
            except Exception as e:
                logger.error(f"Error decoding deep link: {e}")

    # 2. الكود العادي للمستخدمين الذين دخلوا بدون رابط (القائمة الرئيسية)
    await sync_all_users()
    user = USER_CACHE.get(user_id)

    if user:
        # إذا كان المستخدم مسجلاً مسبقاً
        role_name = "الكابتن" if user['role'] == 'driver' else "الراكب"
        status_icon = "✅ موثق" if user['is_verified'] else "⏳ قيد المراجعة"
        
        welcome_text = (
            f"👋 أهلاً بك مجدداً، {role_name} **{user['name']}**\n"
            f"🛡️ الحالة: {status_icon}\n"
            "─────────────────\n"
            "🚀 استخدم القائمة بالأسفل للتحكم بالبوت."
        )
        await update.message.reply_text(
            welcome_text, 
            reply_markup=get_main_kb(user['role'], user['is_verified']), 
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        # إذا كان المستخدم جديداً (بدء عملية التسجيل)
        welcome_new = (
            f"👋 مرحباً بك يا **{first_name}** في بوت التوصيل!\n\n"
            "أنت غير مسجل حالياً، يرجى اختيار نوع الحساب للبدء:"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 تسجيل كراكب", callback_data="reg_rider"),
             InlineKeyboardButton("🚗 تسجيل ككابتن", callback_data="reg_driver")]
        ])
        await update.message.reply_text(welcome_new, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


# --- التسجيل ---
async def register_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    role = "rider" if query.data == "reg_rider" else "driver"
    context.user_data['reg_role'] = role
    context.user_data['state'] = 'WAIT_NAME'

    role_text = "كابتن (سائق)" if role == "driver" else "راكب (عميل)"
    msg = f"✅ اخترت: **{role_text}**\n\n📝 يرجى كتابة **اسمك الثلاثي** الآن:"

    await query.edit_message_text(text=msg, parse_mode=ParseMode.MARKDOWN)

async def complete_registration(update, context, name):
    user = update.effective_user
    user_id = user.id
    chat_id = update.effective_chat.id
    # الحصول على المعرف (Username) إذا وجد
    username = f"@{user.username}" if user.username else "لا يوجد معرف"
    
    role = context.user_data.get('reg_role')
    phone = context.user_data.get('reg_phone', '000000')

    conn = get_db_connection()
    if not conn: return

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            is_verified = True if role == 'rider' else False

            cur.execute("""
                INSERT INTO users (user_id, chat_id, role, name, phone, is_verified)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    phone = EXCLUDED.phone,
                    role = EXCLUDED.role,
                    is_verified = EXCLUDED.is_verified
                RETURNING *;
            """, (user_id, chat_id, role, name, phone, is_verified))
            conn.commit()
            await sync_all_users()

        context.user_data.clear()

        if role == 'driver':
            await update.message.reply_text(
                f"✅ **أبشرك تم استلام طلبك يا كابتن {name}**\n\nحسابك الحين تحت المراجعة، وأول ما يتفعل بيجيك إشعار. خلك قريب!",
                reply_markup=get_main_kb('driver', False)
            )
            
            # زر القبول والرفض للأدمن
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ قبول", callback_data=f"verify_ok_{user_id}"),
                 InlineKeyboardButton("❌ رفض", callback_data=f"verify_no_{user_id}")]
            ])
            
            # نص الرسالة للأدمن (تشمل المعرف ورابط مباشر)
            admin_text = (
                f"🔔 **تسجيل كابتن جديد للمراجعة**\n"
                f"─────────────────\n"
                f"👤 **الاسم:** {name}\n"
                f"📱 **الجوال:** `{phone}`\n"
                f"🆔 **المعرف:** {username}\n"
                f"🔗 **رابط الحساب:** [اضغط هنا](tg://user?id={user_id})\n"
                f"📄 **ID العمل:** `{user_id}`"
            )
            
            for aid in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=aid, 
                        text=admin_text, 
                        reply_markup=kb,
                        parse_mode=ParseMode.MARKDOWN
                    )
                except: pass
        else:
            await update.message.reply_text(
                f"🎉 **يا هلا بيك يا {name}**\nتم تفعيل حسابك كراكب، وتقدر تطلب مشاويرك من الآن!",
                reply_markup=get_main_kb('rider', True)
            )

    except Exception as e:
        print(f"Error registration: {e}")
        await update.message.reply_text("حدث خطأ، حاول مرة ثانية لاحقاً.")
    finally:
        conn.close()


# --- طلب الرحلات ---

async def order_ride_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ كابتن نخبة (بحث بالحي)", callback_data="order_by_district")],
        [InlineKeyboardButton("🌍 أقرب كابتن (بحث بالموقع)", callback_data="order_general")]
    ])
    await update.message.reply_text("🚖 **كيف تود البحث عن الكابتن؟**", reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

async def broadcast_general_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال الطلب للكباتن في نطاق 5 كم فقط"""
    
    # محاولة جلب الموقع من الرسالة الحالية أو من الذاكرة
    if update.message and update.message.location:
        r_lat = update.message.location.latitude
        r_lon = update.message.location.longitude
    else:
        r_lat = context.user_data.get('lat')
        r_lon = context.user_data.get('lon')

    # إذا لم نجد إحداثيات، نوقف العملية
    if r_lat is None or r_lon is None:
        return 0

    price = context.user_data.get('order_price', 0)
    details = context.user_data.get('search_district', "موقع GPS")
    rider_id = update.effective_user.id

    count = 0
    await sync_all_users() # تحديث القائمة

    for d in CACHED_DRIVERS:
        # لا ترسل الطلب لنفسك، وتأكد أن الكابتن لديه موقع مسجل
        if d['user_id'] == rider_id or d.get('lat') is None: 
            continue

        # حساب المسافة
        dist = get_distance(r_lat, r_lon, d['lat'], d['lon'])

        if dist <= 5.0: 
            # تجهيز زر القبول
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(f"✅ قبول ({price} ريال)", callback_data=f"accept_gen_{rider_id}_{price}")
            ]])

            try:
                await context.bot.send_message(
                    chat_id=d['user_id'],
                    text=(f"🚨 **طلب جديد قريب منك!**\n\n"
                          f"📍 المسافة: {dist:.1f} كم\n"
                          f"📝 الوجهة: {details}\n"
                          f"💰 السعر: {price} ريال"),
                    reply_markup=kb,
                    parse_mode=ParseMode.MARKDOWN
                )
                count += 1
            except: 
                continue

    return count

async def end_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner_id = end_chat_session(user_id)

    # إعادة الكيبورد الرئيسي حسب الرتبة
    await sync_all_users()
    user = USER_CACHE.get(user_id)
    role = user['role'] if user else 'rider'
    main_kb = get_main_kb(role, True)

    await update.message.reply_text("🛑 تم إنهاء المحادثة.", reply_markup=main_kb)

    if partner_id:
        try:
            p_user = USER_CACHE.get(partner_id)
            p_role = p_user['role'] if p_user else 'rider'
            await context.bot.send_message(
                chat_id=partner_id, 
                text="🛑 قام الطرف الآخر بإنهاء الرحلة/المحادثة.",
                reply_markup=get_main_kb(p_role, True)
            )
        except: pass


# --- المعالج الشامل (Global Handler) ---


# --- المعالج الشامل (Global Handler) ---
async def global_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # السماح بمرور الرسائل النصية أو الرسائل التي تحتوي على موقع
    if not update.message: return
    
    # إذا لم يكن هناك نص ولا موقع، اخرج (لتجنب الصور والملفات مثلاً)
    if not update.message.text and not update.message.location:
        return

    user_id = update.effective_user.id
    state = context.user_data.get('state')
    text = update.message.text if update.message.text else ""

    # الآن، إذا كان المستخدم أرسل موقعه وهو في حالة انتظار الموقع للطلب
    if update.message.location and state == 'WAIT_LOCATION_FOR_ORDER':
        # نقوم بتحويل المعالجة يدوياً لدالة الموقع لضمان عدم ضياع الطلب
        return await location_handler(update, context)

    # --- 1. التواصل مع الإدارة ---
    if text == "📞 تواصل مع الإدارة":
        await contact_admin_start(update, context)
        return

    if state == 'WAIT_ADMIN_MESSAGE':
        if text == "❌ إلغاء المراسلة":
            context.user_data['state'] = None
            await update.message.reply_text("تم الإلغاء.", reply_markup=get_main_kb(context.user_data.get('role', 'rider')))
            return
        
        for aid in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=aid,
                    text=f"📩 **رسالة دعم جديدة**\nمن: {update.effective_user.first_name}\nID: `{user_id}`\n\n💬 النص: {text}",
                    parse_mode=ParseMode.MARKDOWN
                )
            except: pass
        await update.message.reply_text("✅ تم إرسال رسالتك للإدارة.")
        context.user_data['state'] = None
        return

    # --- 2. إصلاح خطوات التسجيل ---
       # تأكد أن هذا الكود داخل دالة المعالج الأساسية ومحاذاته صحيحة
    
# داخل الـ global_handler الخاص بك:
    if state == 'WAIT_PHONE':
        # تنظيف النص من المسافات
        phone_input = text.strip()
        
        # التحقق: يبدأ بـ 05 ويتكون من 10 أرقام
        if state == 'WAIT_NAME':
        context.user_data['reg_name'] = text
        # تحديث الحالة إلى انتظار الرقم
        context.user_data['state'] = 'WAIT_PHONE'
        await update.message.reply_text("📱 **أبشر، الحين أرسل رقم جوالك:**\n(مثال: 05xxxxxxxx)")
        return  # ضروري جداً لإنهاء الدالة هنا

    # --- 2. مرحلة إدخال الرقم (التحقق ثم الحفظ) ---
    if state == 'WAIT_PHONE':
        import re
        phone_input = text.strip()
        
        # التحقق من صحة الرقم السعودي
        if not re.fullmatch(r'05\d{8}', phone_input):
            await update.message.reply_text("⚠️ **الرقم غير صحيح يا غالي..**\nلازم يبدأ بـ 05 ويتكون من 10 أرقام.")
            return

        context.user_data['reg_phone'] = phone_input
        # الانتقال فوراً لدالة الحفظ
        await complete_registration(update, context, context.user_data['reg_name'])
        context.user_data['state'] = None
        return



    # --- 3. طلب مشوار خاص (كابتن محدد) ---
    if state == 'WAIT_TRIP_DETAILS':
        context.user_data['trip_details'] = text 
        context.user_data['state'] = 'WAIT_TRIP_PRICE'
        await update.message.reply_text("💰 **كم السعر المعروض؟** (أرقام فقط):")
        return

    if state == 'WAIT_TRIP_PRICE':
        try:
            price = float(text)
            details = context.user_data.get('trip_details')
            driver_id = context.user_data.get('driver_to_order')
            
            # إرسال الطلب للكابتن
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ قبول الطلب", callback_data=f"accept_ride_{user_id}_{price}"),
                 InlineKeyboardButton("❌ رفض", callback_data=f"reject_ride_{user_id}")]
            ])
            try:
                await context.bot.send_message(
                    chat_id=driver_id,
                    text=f"🔔 **طلب خاص لك!**\nتفاصيل: {details}\nالسعر: {price} ريال",
                    reply_markup=kb
                )
                await update.message.reply_text("✅ تم إرسال العرض للكابتن، انتظر الموافقة.")
            except:
                await update.message.reply_text("❌ تعذر الوصول للكابتن.")
            
            context.user_data['state'] = None 
        except ValueError:
            await update.message.reply_text("⚠️ أرقام فقط لو سمحت.")
        return

    # --- 4. طلب مشوار عام (GPS) ---
    if state == 'WAIT_GENERAL_DETAILS':
        context.user_data['search_district'] = text
        context.user_data['state'] = 'WAIT_GENERAL_PRICE'
        await update.message.reply_text("💰 **كم السعر المقترح؟** (أرقام فقط):")
        return

    if state == 'WAIT_GENERAL_PRICE':
        try:
            context.user_data['order_price'] = float(text)
            
            kb = ReplyKeyboardMarkup([
                [KeyboardButton("📍 مشاركة موقعي لإرسال الطلب", request_location=True)],
                [KeyboardButton("❌ إلغاء الطلب")]
            ], resize_keyboard=True, one_time_keyboard=True)
            
            await update.message.reply_text(
                "📍 الآن اضغط الزر بالأسفل لمشاركة موقعك وتعميم الطلب:",
                reply_markup=kb
            )
            # هذه الحالة ستلتقطها دالة location_handler المصححة
            context.user_data['state'] = 'WAIT_LOCATION_FOR_ORDER' 
        except ValueError:
            await update.message.reply_text("⚠️ أرقام فقط.")
        return

    # --- 5. القائمة الرئيسية ---
    # 5. أوامر القائمة الرئيسية (Main Menu
    if text == "🚖 طلب رحلة":
        await order_ride_options(update, context)
        return

    if text == "📍 تحديث موقعي":
        await update.message.reply_text("📍 لتحديث موقعك، أرسل (Location) من المشبك 📎")
        return

    if text == "💰 محفظتي":
        user = USER_CACHE.get(user_id)
        bal = user.get('balance', 0) if user else 0
        await update.message.reply_text(f"💳 رصيدك الحالي: {bal} ريال")
        return

        # استبدال الكود القديم بهذا
    if text == "📍 مناطق عملي" or text == "📝 تحديث الأحياء":
        await districts_settings_view(update, context)
        return


    if text == "ℹ️ حالة اشتراكي":
        user = USER_CACHE.get(user_id)
        if user and user.get('subscription_expiry'):
             expiry = user['subscription_expiry'].strftime('%Y-%m-%d')
             await update.message.reply_text(f"📅 اشتراكك ينتهي في: {expiry}")
        else:
             await update.message.reply_text("❌ ليس لديك اشتراك فعال.")
        return

    # ---------------------------------------------------------
    # 6. معالجة إدخالات السائقين والبحث النصي
    # ---------------------------------------------------------
    if state == 'WAIT_DISTRICTS':
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET districts = %s WHERE user_id = %s", (text, user_id))
            conn.commit()
        await sync_all_users()
        await update.message.reply_text("✅ تم تحديث الأحياء بنجاح.")
        context.user_data['state'] = None
        return

    if state == 'WAIT_ELITE_DISTRICT':
        # بحث نصي في الأحياء
        found = []
        # التأكد من تحديث الكاش أولاً
        await sync_all_users()
        
        for d in CACHED_DRIVERS:
            if d.get('districts') and text in d['districts']:
                found.append(d)

        if not found:
            await update.message.reply_text("❌ لا يوجد كابتن مسجل في هذا الحي حالياً.")
        else:
            await update.message.reply_text(f"✅ وجدنا {len(found)} كابتن في {text}:")
            for d in found:
                # زر الطلب هنا ينقل لطلب خاص
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"📞 طلب {d['name']}", callback_data=f"book_{d['user_id']}_{text}") ]])
                await update.message.reply_text(f"👤 الكابتن: {d['name']}\n🚗 {d['car_info']}", reply_markup=kb)
        context.user_data['state'] = None
        return


# --- معالجة المواقع (Location) ---

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    location = update.message.location
    state = context.user_data.get('state')

    # 1. تحديث الإحداثيات في الذاكرة الحية
    context.user_data['lat'] = location.latitude
    context.user_data['lon'] = location.longitude

    # 2. تحديث قاعدة البيانات في الخلفية
    threading.Thread(target=update_db_location, args=(user_id, location.latitude, location.longitude)).start()

    # 3. جلب بيانات المستخدم لمعرفة رتبته (سائق أم راكب)
    await sync_all_users() # لضمان أن البيانات محدثة
    user_data = USER_CACHE.get(user_id, {})
    user_role = user_data.get('role', 'rider') # القيمة الافتراضية راكب إذا لم يوجد
    is_verified = user_data.get('is_verified', False)

    # 4. معالجة طلب الرحلة (للركاب فقط)
    if state == 'WAIT_LOCATION_FOR_ORDER' and user_role == 'rider':
        processing_msg = await update.message.reply_text("📡 جاري البحث عن كباتن...")
        count = await broadcast_general_order(update, context)
        
        if count > 0:
            await processing_msg.edit_text(
                f"✅ تم إرسال طلبك إلى **{count}** كابتن.",
                reply_markup=get_main_kb("rider", True)
            )
        else:
            await processing_msg.edit_text(
                "⚠️ لا يوجد كباتن متاحين حالياً.",
                reply_markup=get_main_kb("rider", True)
            )
        context.user_data['state'] = None

    # 5. إذا كان المرسل سائقاً يحدّث موقعه أو راكباً يحدّث موقعه خارج عملية الطلب
    else:
        # هنا السر: نرسل الكيبورد المناسب لرتبة المستخدم الفعلية
        await update.message.reply_text(
            "📍 تم تحديث موقعك بنجاح في النظام.",
            reply_markup=get_main_kb(user_role, is_verified)
        )


async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id

    # محاولة إغلاق مؤشر التحميل لتجنب التعليق
    try:
        await query.answer()
    except:
        pass
    # ===============================================================
    # 1. القائمة الرئيسية للبحث (أقرب كابتن vs بحث بالأحياء)
    # ===============================================================

    # --- خيار أ: أقرب كابتن (البحث بالموقع GPS) ---
    if data == "order_general":
        context.user_data['state'] = 'WAIT_GENERAL_DETAILS' 
        await query.edit_message_text(
            "🌍 **البحث عن أقرب كابتن (GPS):**\n\n"
            "📝 يرجى كتابة **تفاصيل مشوارك** الآن (من وين لوين؟):",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # --- خيار ب: كابتن نخبة (بحث باختيار المدينة والحي) ---
    elif data == "order_by_district":
        keyboard = []
        for city in CITIES_DISTRICTS.keys():
            keyboard.append([InlineKeyboardButton(city, callback_data=f"city_{city}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("📍 اختر المدينة:", reply_markup=reply_markup)
        return

    # ===============================================================
    # 2. التنقل داخل قائمة المدن والأحياء
    # ===============================================================

    # --- تم اختيار المدينة -> عرض الأحياء ---
    elif data.startswith("city_"):
        city_name = data.split("_")[1]
        districts = CITIES_DISTRICTS.get(city_name, [])
        
        # تنسيق الأزرار (2 في كل صف)
        keyboard = []
        for i in range(0, len(districts), 2):
            row = [InlineKeyboardButton(districts[i], callback_data=f"search_dist_{districts[i]}")]
            if i + 1 < len(districts):
                row.append(InlineKeyboardButton(districts[i+1], callback_data=f"search_dist_{districts[i+1]}"))
            keyboard.append(row)
        
        # زر رجوع
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="order_by_district")])
        
        await query.edit_message_text(
            f"📍 أحياء {city_name}:\nاختر الحي لرؤية الكباتن:", 
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # --- تم اختيار الحي -> عرض الكباتن ---
    elif data.startswith("search_dist_"):
        selected_dist = data.split("_")[2]
        await sync_all_users() # تحديث البيانات

        matched_drivers = []
        # البحث مع معالجة التاء المربوطة والهاء
        for d in CACHED_DRIVERS:
            if d.get('districts'):
                d_list = [x.strip().replace("ة", "ه") for x in d['districts'].replace("،", ",").split(",")]
                if selected_dist.replace("ة", "ه") in d_list:
                    matched_drivers.append(d)

        if not matched_drivers:
            await query.edit_message_text(
                f"📍 حي {selected_dist}:\n\n⚠️ للأسف، لا يوجد كباتن مسجلين في هذا الحي حالياً.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=f"city_الرياض")]]) # مثال
            )
        else:
            keyboard = []
            for d in matched_drivers[:8]: # عرض أول 8 فقط
                # الزر يرسل book_ID_DISTRICT
                keyboard.append([InlineKeyboardButton(
                    f"🚖 {d['name']} ({d.get('car_info', 'سيارة')})", 
                    callback_data=f"book_{d['user_id']}_{selected_dist}"
                )])
            
            await query.edit_message_text(
                f"✅ **كباتن متوفرين في {selected_dist}:**\nاضغط على الكابتن لطلب مشوار:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        return

    # ===============================================================
    # 3. بدء عملية حجز كابتن محدد (Book)
    # ===============================================================
    elif data.startswith("book_"):
        parts = data.split("_")
        driver_id = parts[1]
        dist_name = parts[2]
        
        # 1. حفظ البيانات
        context.user_data['driver_to_order'] = driver_id
        context.user_data['order_dist'] = dist_name

        # 2. التحقق: هل نحن في الخاص أم في مجموعة؟
        if query.message.chat.type == "private":
            # المستخدم في الخاص -> اطلب التفاصيل فوراً
            context.user_data['state'] = 'WAIT_TRIP_DETAILS'
            await query.edit_message_text(
                f"📝 **طلب مشوار من حي {dist_name}**\n\n"
                "يرجى كتابة **تفاصيل المشوار** (من وين لوين؟):",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            # المستخدم في مجموعة -> تحويل للبوت
            bot_username = context.bot.username
            url = f"https://t.me/{bot_username}?start=req_{driver_id}"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ اضغط هنا لإكمال الطلب", url=url)]])
            await query.edit_message_text(
                "📥 لإكمال الطلب وحماية خصوصيتك، انتقل للبوت:",
                reply_markup=kb
            )
        return

    # --- منطق تبديل الأحياء ---
    if data.startswith("toggle_dist_"):
        dist_name = data.replace("toggle_dist_", "")
        user_id = update.effective_user.id
        
        # البحث عن الكابتن في الكاش لتعديله
        for d in CACHED_DRIVERS:
            if d['user_id'] == user_id:
                # تحويل النص الحالي لقائمة
                current_list = [x.strip() for x in d.get('districts', "").replace("،", ",").split(",") if x.strip()]
                
                if dist_name in current_list:
                    current_list.remove(dist_name) # حذف
                else:
                    current_list.append(dist_name) # إضافة
                
                # تحديث النص (String)
                new_districts_str = "، ".join(current_list)
                d['districts'] = new_districts_str
                
                # تحديث سوبابيز فوراً
                update_districts_in_db(user_id, new_districts_str)
                break
        
        # إعادة عرض الأزرار لتظهر العلامات المحدثة
        await districts_settings_view(update, context)
        return

    elif data == "save_districts":
        await query.answer("✅ تم حفظ الأحياء في نظام سوبابيز")
        await query.edit_message_text("🚀 تم تحديث أحيائك! ستصلك تنبيهات القروب بناءً على اختياراتك الآن.")
        await sync_all_users() # مزامنة نهائية للكاش
        return



    # ===============================================================
    # 4. قبول الكابتن للطلب (عام أو خاص)
    # ===============================================================
    elif data.startswith("accept_ride_") or data.startswith("accept_gen_"):
        parts = data.split("_")
        rider_id = int(parts[2])
        price = float(parts[3])
        driver_id = user_id
        
        # أ) التحقق من رصيد الكابتن
        conn = get_db_connection()
        can_accept = False
        driver_name = "كابتن"
        driver_car = "سيارة"

        if conn:
            with conn.cursor() as cur:
                cur.execute("SELECT balance, name, car_info FROM users WHERE user_id = %s", (driver_id,))
                res = cur.fetchone()
                if res:
                    current_bal = res[0]
                    driver_name = res[1]
                    driver_car = res[2]
                    # السماح بالقبول إذا الرصيد أكبر من -5 (أو 0 حسب سياستك)
                    if current_bal >= -5: 
                        can_accept = True
            conn.close()

        if not can_accept:
            await query.answer("⚠️ رصيدك غير كافٍ! يرجى شحن المحفظة.", show_alert=True)
            return

        # ب) إبلاغ الكابتن بالانتظار
        await query.edit_message_text("⏳ تم إرسال موافقتك للعميل.. بانتظار تأكيده لفتح المحادثة.")

        # ج) إرسال طلب الموافقة النهائية للراكب
        kb_confirm = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💬 موافقة وفتح الدردشة", callback_data=f"final_start_{driver_id}_{price}"),
                InlineKeyboardButton("❌ رفض", callback_data=f"reject_ride_{driver_id}")
            ]
        ])

        try:
            await context.bot.send_message(
                chat_id=rider_id,
                text=(f"🎉 **تم قبول عرضك!**\n\n"
                      f"👤 الكابتن: {driver_name}\n"
                      f"🚗 السيارة: {driver_car}\n"
                      f"💰 السعر المتفق عليه: {price} ريال\n\n"
                      f"هل تود فتح المحادثة وبدء الرحلة؟"),
                reply_markup=kb_confirm,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            await query.edit_message_text(f"❌ تعذر الوصول للعميل. قد يكون حظر البوت.")
        return

    # ===============================================================
    # 5. الموافقة النهائية من الراكب (بدء الشات والخصم)
    # ===============================================================
    elif data.startswith("final_start_"):
        parts = data.split("_")
        driver_id = int(parts[2])
        price = float(parts[3])
        rider_id = user_id
        commission = price * 0.10 # عمولة 10%

        # 1. خصم العمولة من الكابتن
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET balance = balance - %s WHERE user_id = %s", (commission, driver_id))
                conn.commit()
            conn.close()

        # 2. تفعيل جلسة المحادثة
        start_chat_session(driver_id, rider_id)

        # 3. إشعار الأدمن (Log)
        admin_msg = (
            f"💰 **عملية ناجحة**\n"
            f"👤 راكب: `{rider_id}` | 🚖 كابتن: `{driver_id}`\n"
            f"💵 السعر: {price} | 📉 العمولة: {commission}"
        )
        for aid in ADMIN_IDS:
            try: await context.bot.send_message(chat_id=aid, text=admin_msg, parse_mode=ParseMode.MARKDOWN)
            except: pass

        # 4. إرسال واجهة الدردشة للطرفين
        # كيبورد يحتوي على زر مشاركة الموقع وزر إنهاء
        kb_chat = ReplyKeyboardMarkup([
            [KeyboardButton("📍 مشاركة موقعي الحالي", request_location=True)],
            [KeyboardButton("❌ إنهاء المحادثة")]
        ], resize_keyboard=True)

        # رسالة للراكب (الذي ضغط الزر)
        await query.edit_message_text("✅ تم بدء الرحلة وفتح الخط مع الكابتن.")
        await context.bot.send_message(
            chat_id=rider_id, 
            text="🟢 **أنت الآن في محادثة مباشرة مع الكابتن.**\nيمكنك إرسال موقعك أو الكتابة له هنا.", 
            reply_markup=kb_chat,
            parse_mode=ParseMode.MARKDOWN
        )

        # رسالة للكابتن
        try:
            await context.bot.send_message(
                chat_id=driver_id, 
                text=(f"✅ **وافق العميل وبدأت الرحلة!**\n"
                      f"تم خصم عمولة ({commission} ريال).\n"
                      f"تحدث معه الآن للتنسيق."), 
                reply_markup=kb_chat,
                parse_mode=ParseMode.MARKDOWN
            )
        except: pass
        return

    # ===============================================================
    # 6. الرفض (من الكابتن أو الراكب)
    # ===============================================================
    elif data.startswith("reject_ride_"):
        target_id = int(data.split("_")[2])
        
        await query.edit_message_text("❌ تم رفض الطلب.")
        try:
            await context.bot.send_message(chat_id=target_id, text="❌ عذراً، تم رفض/إلغاء الطلب من الطرف الآخر.")
        except: pass
        return

    # ===============================================================
    # 7. التوثيق (لوحة تحكم الأدمن)
    # ===============================================================
    elif data.startswith("verify_"):
        # التنسيق: verify_ok_ID أو verify_no_ID
        parts = data.split("_")
        action = parts[1]
        target_uid = int(parts[2])
        is_verified = (action == "ok")

        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET is_verified = %s WHERE user_id = %s", (is_verified, target_uid))
            conn.commit()
        conn.close()

        status_text = "✅ موثق" if is_verified else "❌ مرفوض"
        await query.edit_message_text(f"تم تحديث حالة المستخدم {target_uid} إلى: {status_text}")
        
        # إشعار المستخدم
        msg = "🎉 تهانينا! تم توثيق حسابك ككابتن." if is_verified else "❌ تم رفض طلب توثيق حسابك. تواصل مع الإدارة."
        try:
            await context.bot.send_message(chat_id=target_uid, text=msg)
        except: pass
        
        # تحديث الكاش
        await sync_all_users()
        return




async def districts_settings_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    
    # 1. جلب بيانات السائق من الكاش
    driver = next((d for d in CACHED_DRIVERS if d['user_id'] == user_id), None)
    
    # تحويل نص الأحياء من قاعدة البيانات إلى قائمة للمقارنة
    current_districts = []
    if driver and driver.get('districts'):
        current_districts = [d.strip() for d in driver['districts'].replace("،", ",").split(",") if d.strip()]

    # 2. بناء الأزرار
    all_districts = CITIES_DISTRICTS.get("المدينة المنورة", [])
    keyboard = []
    
    for i in range(0, len(all_districts), 2):
        row = []
        for j in range(2):
            if i + j < len(all_districts):
                dist_name = all_districts[i + j]
                # وضع علامة ✅ إذا كان الحي مختاراً
                status = "✅ " if dist_name in current_districts else "⬜ "
                row.append(InlineKeyboardButton(f"{status}{dist_name}", callback_data=f"toggle_dist_{dist_name}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🏁 حفظ وإغلاق", callback_data="save_districts")])

    text = "📍 **إعدادات نطاق العمل:**\n\nاختر الأحياء التي تعمل بها ليتم إشعارك بطلباتها في القروب والخاص."
    
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)


# --- أوامر الأدمن ---
async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال رسالة جماعية للكل: /broadcast الرسالة"""
    # 1. التحقق من أن المرسل هو الأدمن
    if update.effective_user.id not in ADMIN_IDS:
        return

    # 2. التحقق من وجود نص للرسالة
    message_text = " ".join(context.args)
    if not message_text:
        await update.message.reply_text("⚠️ خطأ في الاستخدام!\nاكتب الرسالة بعد الأمر، مثال:\n`/broadcast نعتذر عن توقف الخدمة للصيانة`", parse_mode=ParseMode.MARKDOWN)
        return

    await update.message.reply_text(f"⏳ جاري إرسال الرسالة إلى جميع المشتركين... يرجى عدم إيقاف البوت.")

    # 3. جلب كل المستخدمين من قاعدة البيانات
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ فشل الاتصال بقاعدة البيانات.")
        return

    users_list = []
    with conn.cursor() as cur:
        cur.execute("SELECT user_id FROM users")
        # تحويل النتائج لقائمة أرقام
        users_list = [row[0] for row in cur.fetchall()]
    conn.close()

    # 4. بدء عملية الإرسال
    success_count = 0
    block_count = 0

    for uid in users_list:
        try:
            # إضافة جملة "تنبيه إداري" لتظهر بشكل رسمي
            final_msg = f"📢 **تنبيه هام من الإدارة:**\n\n{message_text}"
            await context.bot.send_message(chat_id=uid, text=final_msg, parse_mode=ParseMode.MARKDOWN)
            success_count += 1
        except Exception:
            # إذا فشل الإرسال (غالباً لأن العضو سوى بلوك للبوت)
            block_count += 1

    # 5. التقرير النهائي
    report = (
        f"✅ **تم انتهاء الإذاعة!**\n"
        f"─────────────────\n"
        f"📩 تم الاستلام: {success_count} عضو\n"
        f"🚫 محظور/فاشل: {block_count} عضو\n"
        f"👥 المجموع الكلي: {len(users_list)}"
    )
    await update.message.reply_text(report, parse_mode=ParseMode.MARKDOWN)


async def admin_add_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تفعيل اشتراك: /sub ID DAYS"""
    if update.effective_user.id not in ADMIN_IDS: return
    try:
        uid = int(context.args[0])
        days = int(context.args[1])

        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(f"UPDATE users SET subscription_expiry = NOW() + INTERVAL '{days} days', is_verified=TRUE WHERE user_id = %s", (uid,))
            conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ تم تفعيل {days} يوم للعضو {uid}")
        await context.bot.send_message(uid, f"🎉 تم تفعيل اشتراكك لمدة {days} يوم.")
    except:
        await update.message.reply_text("❌ خطأ: /sub [ID] [Days]")

async def admin_cash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة رصيد: /cash ID AMOUNT"""
    if update.effective_user.id not in ADMIN_IDS: return
    try:
        uid = int(context.args[0])
        amount = float(context.args[1])

        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (amount, uid))
            conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ تم إضافة {amount} ريال.")
        await context.bot.send_message(uid, f"💰 تم شحن رصيدك بـ {amount} ريال.")
    except:
        await update.message.reply_text("❌ خطأ: /cash [ID] [Amount]")

async def group_order_scanner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # تجاهل الرسائل التي لا تحتوي على نص أو ليست في مجموعة
    if not update.message or not update.message.text: return
    if update.message.chat.type == "private": return

    user = update.effective_user
    text = update.message.text.lower()
    # تنظيف النص لتوحيد البحث (التاء المربوطة والهمزات)
    msg_clean = text.replace("ة", "ه").replace("أ", "ا").replace("إ", "ا")

    # 1. منع الطلبات الشهرية فوراً
    FORBIDDEN = ["شهري", "عقد", "راتب"]
    if any(k in msg_clean for k in FORBIDDEN):
        try: await update.message.delete()
        except: pass
        await context.bot.send_message(user.id, "⚠️ نعتذر، الطلبات الشهرية ممنوعة في القروب. يرجى طلب مشاوير يومية فقط.")
        return

    # 2. فحص الكلمات المفتاحية للطلب
    KEYWORDS = ["توصيل", "مشوار", "مطلوب", "ابي", "بغيت", "سواق", "كابتن", "وين"]
    if not any(k in msg_clean for k in KEYWORDS):
        return

    # 3. محاولة استخراج الحي من نص الرسالة
    districts_list = CITIES_DISTRICTS.get("المدينة المنورة", [])
    found_dist = None
    for dist in districts_list:
        clean_dist = dist.replace("ة", "ه").replace("أ", "ا").replace("إ", "ا")
        if clean_dist in msg_clean:
            found_dist = dist
            break

    # 4. إذا لم يجد اسم الحي -> يعرض أزرار الأحياء للاختيار (مثل آلية الخاص)
    if not found_dist:
        keyboard = []
        for i in range(0, len(districts_list), 2):
            row = [InlineKeyboardButton(districts_list[i], callback_data=f"search_dist_{districts_list[i]}")]
            if i + 1 < len(districts_list):
                row.append(InlineKeyboardButton(districts_list[i+1], callback_data=f"search_dist_{districts_list[i+1]}"))
            keyboard.append(row)
        
        await update.message.reply_text(
            f"يا هلا بك يا {user.first_name} ✨\nحدد الحي المطلوب للبحث عن كباتن متوفرين:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # 5. إذا وجد الحي -> يبحث عن الكباتن المسجلين في هذا الحي
    await sync_all_users()
    matched_drivers = []
    for d in CACHED_DRIVERS:
        if d.get('districts'):
            # تنظيف قائمة أحياء الكابتن للمطابقة
            d_dists = [x.strip().replace("ة", "ه") for x in d['districts'].replace("،", ",").split(",")]
            if found_dist.replace("ة", "ه") in d_dists:
                matched_drivers.append(d)

    # 6. عرض النتائج بنفس آلية "أزرار الأحياء" الاحترافية
    if matched_drivers:
        keyboard = []
        for d in matched_drivers[:6]: # عرض 6 كباتن كحد أقصى
            driver_id = d['user_id']
            # رابط Deep Link يفتح البوت ويبدأ الطلب
            deep_link = f"https://t.me/Fogtyjnbot?start=req_{driver_id}"
            
            # تصحيح السطر أدناه: إضافة اسم الكابتن وإغلاق علامات التنصيص والقوس
            keyboard.append([InlineKeyboardButton(f"🚖 اطلب الكابتن {d['name']}", url=deep_link)])

        await update.message.reply_text(
            f"✅ **أبشر! وجدنا كباتن متاحين في حي {found_dist}:**\n\n"
            "اضغط على اسم الكابتن ثم اضغط (ابدأ/Start) واكتب تفاصيل مشوارك داخل البوت:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

        
        # 7. تنبيه الكباتن في الخاص فوراً لزيادة سرعة الاستجابة
        for d in matched_drivers:
            try:
                await context.bot.send_message(
                    chat_id=d['user_id'],
                    text=f"🔔 **تنبيه:** يوجد  **{found_dist}**  هناك طلبات قريبه منك. كن مستعداً!"
                )
            except: pass
    else:
        # إذا لم يتوفر كباتن في الحي المحدد
        bot_username = context.bot.username
        # رابط ينقل العميل للبوت ويحفز خيار البحث بالموقع
        search_link = f"https://t.me/{bot_username}?start=order_general"
        
        keyboard = [[InlineKeyboardButton("🌍 ابحث عن أقرب كابتن (GPS)", url=search_link)]]
        
        await update.message.reply_text(
            f"📍 حي {found_dist}: لا يوجد كباتن مسجلين بهذا الحي حالياً.\n\n"
            "💡 **بدلاً من ذلك:** يمكنك البحث عن أقرب كابتن متاح حولك الآن بواسطة موقعك الجغرافي عبر البوت.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )


async def admin_send_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال رسالة من الأدمن لمستخدم: /send ID الرسالة"""
    if update.effective_user.id not in ADMIN_IDS: return
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ الاستخدام: `/send ID الرسالة`")
        return
    try:
        target_id = int(context.args[0])
        msg = " ".join(context.args[1:])
        await context.bot.send_message(chat_id=target_id, text=f"📢 **رسالة من الإدارة:**\n\n{msg}", parse_mode=ParseMode.MARKDOWN)
        await update.message.reply_text(f"✅ تم الإرسال للمستخدم {target_id}")
    except Exception as e:
        await update.message.reply_text(f"❌ فشل الإرسال: {e}")

async def contact_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دالة يبدأ بها المستخدم (راكب/سائق) مراسلة الإدارة"""
    context.user_data['state'] = 'WAIT_ADMIN_MESSAGE'
    await update.message.reply_text(
        "📝 **أرسل رسالتك أو شكواك الآن في رسالة واحدة:**",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ إلغاء المراسلة")]], resize_keyboard=True)
    )




async def admin_get_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. التحقق من صلاحية الأدمن
    if update.effective_user.id not in ADMIN_IDS:
        return

    # 2. التحقق من إدخال المعرفات (IDs)
    try:
        if len(context.args) < 2:
            await update.message.reply_text("⚠️ الاستخدام الصحيح: `/logs ID1 ID2`\nمثال: `/logs 12345 67890`", parse_mode=ParseMode.MARKDOWN)
            return

        id1 = int(context.args[0])
        id2 = int(context.args[1])

        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ خطأ في الاتصال بقاعدة البيانات.")
            return

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # جلب الرسائل المتبادلة بين الطرفين
            cur.execute("""
                SELECT sender_id, message_content, created_at 
                FROM chat_logs 
                WHERE (sender_id = %s AND receiver_id = %s) 
                   OR (sender_id = %s AND receiver_id = %s)
                ORDER BY created_at ASC 
                LIMIT 30
            """, (id1, id2, id2, id1))

            logs = cur.fetchall()

        if not logs:
            await update.message.reply_text("📭 لا توجد سجلات محادثة بين هذين الطرفين حالياً.")
            return

        # 3. تنسيق الرسائل للعرض
        report = f"📜 **سجل آخر الرسائل بين:**\n🆔 `{id1}`\n🆔 `{id2}`\n"
        report += "─────────────────\n"

        for msg in logs:
            sender_label = "👤 الطرف [1]" if msg['sender_id'] == id1 else "🚖 الطرف [2]"
            time_str = msg['created_at'].strftime('%H:%M')
            report += f"[{time_str}] {sender_label}: {msg['message_content']}\n"

        await update.message.reply_text(report, parse_mode=ParseMode.MARKDOWN)

    except ValueError:
        await update.message.reply_text("⚠️ يرجى التأكد من إدخال أرقام الـ ID بشكل صحيح.")
    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ: {e}")
    finally:
        if conn: conn.close()

async def chat_relay_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # 🛑 منع توجيه الأوامر أو زر الإنهاء للطرف الآخر
    if text and (text.startswith('/') or text == "❌ إنهاء المحادثة"):
        return 

    partner_id = get_chat_partner(user_id)
    if not partner_id: return 


    # 3. تحديد نوع الرسالة يدوياً لتخزينه في القاعدة
    if update.message.text:
        msg_type = "text"
        msg_content = update.message.text
    elif update.message.location:
        msg_type = "location"
        msg_content = f"📍 موقع: {update.message.location.latitude}, {update.message.location.longitude}"
    elif update.message.photo:
        msg_type = "photo"
        msg_content = "🖼️ [صورة]"
    elif update.message.voice:
        msg_type = "voice"
        msg_content = "🎤 [رسالة صوتية]"
    else:
        msg_type = "other"
        msg_content = "📎 [وسائط]"

    # 4. حفظ في قاعدة البيانات (السجلات)
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_logs (sender_id, receiver_id, message_content, msg_type)
                    VALUES (%s, %s, %s, %s)
                """, (int(user_id), int(partner_id), msg_content, msg_type))
                conn.commit()
        except Exception as e:
            print(f"❌ خطأ في حفظ SQL: {e}")
        finally:
            conn.close()

    # 5. نقل الرسالة للطرف الآخر
    kb_chat = ReplyKeyboardMarkup([
        [KeyboardButton("📍 مشاركة موقعي الحالي", request_location=True)],
        [KeyboardButton("❌ إنهاء المحادثة")]
    ], resize_keyboard=True)

    try:
        await context.bot.copy_message(
            chat_id=partner_id,
            from_chat_id=user_id,
            message_id=update.message.message_id,
            reply_markup=kb_chat
        )
    except Exception as e:
        print(f"❌ فشل النقل: {e}")

    # منع الرسالة من الوصول للـ global_handler
    raise ApplicationHandlerStop




# ==================== 🌐 5. خادم Flask (للبقاء نشطاً) ====================

app = Flask('')
@app.route('/')
def home(): return "Bot is Running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# ==================== 🏁 6. التشغيل الرئيسي ====================
def main():
    # 1. تهيئة السيرفر وقاعدة البيانات
    threading.Thread(target=run_flask, daemon=True).start()
    init_db()

    # 2. بناء التطبيق
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # --- الفئة الأولى: الأوامر ---
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("end", end_chat_command))
    application.add_handler(CommandHandler("send", admin_send_to_user))
    application.add_handler(CommandHandler("cash", admin_cash))
    application.add_handler(CommandHandler("sub", admin_add_days))
    application.add_handler(CommandHandler("broadcast", admin_broadcast))
    application.add_handler(CommandHandler("logs", admin_get_logs))

    # --- الفئة الثانية: الأزرار النصية الحساسة ---
    application.add_handler(MessageHandler(filters.Regex("^❌ إنهاء المحادثة$"), end_chat_command))
    application.add_handler(MessageHandler(filters.Regex("^❌ إلغاء الطلب$"), start_command))
    application.add_handler(MessageHandler(filters.Regex("^❌ إلغاء المراسلة$"), start_command))

    # --- الفئة الثالثة: المحادثة المباشرة (Relay) - Group 0 ---
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.ALL & ~filters.COMMAND & ~filters.Regex("^❌"),
        chat_relay_handler
    ), group=0)

    # --- الفئة الرابعة: المعالج الشامل (Global Handler) - Group 1 ---
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, 
        global_handler
    ), group=1)

    # --- الفئة الخامسة: أزرار الإنلاين (Callback) والمواقع ---
    # فصلنا التسجيل بنمط خاص لضمان عمله فوراً
    application.add_handler(CallbackQueryHandler(register_callback, pattern="^reg_"))
    application.add_handler(CallbackQueryHandler(handle_callbacks))
    
    application.add_handler(MessageHandler(filters.LOCATION, location_handler), group=-1)

    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT, group_order_scanner))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))

    # 3. بدء التشغيل
    print("🚀 البوت يعمل الآن بنجاح...")
    application.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    main()