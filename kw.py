#!/umainbin/env python3
# -*- coding: utf-8 -*-

import logging
import threading
import asyncio
import time
import os
import re
import random
import urllib.parse  # أضف هذا الاستيراد في أعلى الملف
from datetime import datetime
from math import radians, cos, sin, asin, sqrt
from enum import Enum
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

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
from telegram.ext import MessageHandler, filters, ContextTypes, ChatMemberHandler

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
BOT_TOKEN = "8498451295:AAGt1R7THllSjYtEe5hvIEPnPhRkS_iBcnU"
ADMIN_IDS = [8563113166, 7580027135, 5027690233]

# الكلمات المفتاحية للبحث في المجموعات


# --- 1. إعدادات الأحياء الذكية (المدينة المنورة) ---
CITIES_DISTRICTS = {
    "المدينة المنورة": [
        "الإسكان", "البحر", "البدراني", "الفتح", "التلال", "الجرف", "الحزام", "الحمراء", 
        "الخالدية", "الدويخله", "الرانونا", "الربوة", "الشروق", "الشرق", 
        "العاقول", "العريض", "العزيزية", "العنابس", "القبلتين", "المبعوث", 
        "المطار", "المغيسله", "الملك فهد", "النبلاء", "الهجرة", "باقدو", 
        "بني حارثة", "حديقة الملك فهد", "سيد الشهداء", "شوران", "قباء", "مهزور",
        "شظاة", "مستشفى الملك فهد", "مستشفى الملك سلمان", "مستشفى الولادة", 
        "مستشفى المواساة", "النور مول", "العالية مول", "القارات", 
        "العيون", "طريق الملك عبدالعزيز", "الدائري"
    ]
}

LAST_REPLY_TIME = {}
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

class UserRole(str, Enum):
    RIDER = "rider"
    DRIVER = "driver"
LAST_DB_UPDATE = {}
# ==================== 🗄️ 2. قاعدة البيانات ====================
def normalize_text(text):
    if not text: return ""
    # إزالة التشكيل
    text = re.sub(r"[\u064B-\u0652]", "", text)
    # توحيد الحروف (أ إ آ -> ا، ة -> ه)
    text = text.replace("ة", "ه").replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    # إزالة تكرار الحروف (مثل: مشواااار -> مشوار)
    text = re.sub(r'(.)\1+', r'\1', text)
    return text.strip().lower()
    
def normalize_text(text):
    if not text: return ""
    # إزالة المسافات الزائدة وتحويل للحروف الصغيرة
    text = text.strip().lower()
    # توحيد الحروف المتشابهة
    replacements = {
        "أ": "ا", "إ": "ا", "آ": "ا",
        "ة": "ه",
        "ى": "ي",
        "ئ": "ي", "ؤ": "و"
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # إزالة (الـ) التعريف من البداية لجعل البحث مرناً (اختياري لكنه قوي)
    # مثال: "عزيزيه" ستطابق "العزيزية"
    words = text.split()
    clean_words = []
    for w in words:
        if w.startswith("ال") and len(w) > 3:
            clean_words.append(w[2:])
        else:
            clean_words.append(w)
    
    return " ".join(clean_words)

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


def save_chat_log(sender_id, receiver_id, content, msg_type="text"):
    """دالة مساعدة لحفظ الرسائل في قاعدة البيانات"""
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO chat_logs (sender_id, receiver_id, message_content, msg_type)
                VALUES (%s, %s, %s, %s)
            """, (sender_id, receiver_id, content, msg_type))
            conn.commit()
    except Exception as e:
        print(f"❌ خطأ في حفظ السجل: {e}")
    finally:
        conn.close()




# ==================== 🛠️ 3. دوال مساعدة ====================



async def update_db_silent(user_id, lat, lon):
    """
    تحديث الموقع باستخدام رابط DB_URL الحالي بدون تعطيل البوت
    """
    conn = None
    try:
        # استخدام الاتصال المباشر برابطك الحالي
        conn = psycopg2.connect(DB_URL)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET lat = %s, lon = %s, last_location_update = NOW() WHERE user_id = %s",
                (lat, lon, user_id)
            )
            conn.commit()
    except Exception as e:
        # استخدام السجل لطباعة الخطأ دون تعطيل البرنامج
        logger.error(f"❌ خطأ في تحديث الموقع الخلفي: {e}")
    finally:
        if conn:
            conn.close()

def get_chat_partner(user_id, context=None):
    """جلب معرف الطرف الآخر من قاعدة البيانات مباشرة"""
    conn = get_db_connection()
    if not conn: return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT partner_id FROM active_chats WHERE user_id = %s", (user_id,))
            res = cur.fetchone()
            if res: return res[0]
    except Exception as e:
        print(f"❌ Error fetching partner: {e}")
    finally:
        conn.close()
    return None

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
    if not conn: 
        return False
        
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET districts = %s WHERE user_id = %s",
                (districts_str, user_id)
            )
            conn.commit()
        return True
    except Exception as e:
        print(f"❌ خطأ تحديث الأحياء في قاعدة البيانات: {e}")
        return False
    finally:
        if conn:
            conn.close()





async def sync_all_users(force=False):
    global USER_CACHE, CACHED_DRIVERS, LAST_CACHE_SYNC
    
    if not force:
        if (datetime.now() - LAST_CACHE_SYNC).total_seconds() < 120:
            return

    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users")
            all_users = cur.fetchall()

            # تحويل المعرفات لنصوص لتوحيد الوصول إليها
            USER_CACHE = {str(u['user_id']): u for u in all_users}
            
            # فلترة السائقين: نتحقق أن الدور سائق
            # سيحتوي كل عنصر هنا على u['is_verified'] لأننا استخدمنا SELECT *
            CACHED_DRIVERS = [u for u in all_users if u['role'] == 'driver']

            LAST_CACHE_SYNC = datetime.now()
    finally:
        conn.close()



# --- دوال الدردشة الوسيطة ---

def start_chat_session(user1_id, user2_id):
    """ربط الطرفين ببعضهما في قاعدة البيانات"""
    conn = get_db_connection()
    if not conn: 
        return False
    try:
        with conn.cursor() as cur:
            # استخدام قيم واضحة لتجنب أخطاء السنتكس في SQL
            sql = """
                INSERT INTO active_chats (user_id, partner_id) 
                VALUES (%s, %s), (%s, %s)
                ON CONFLICT (user_id) 
                DO UPDATE SET partner_id = EXCLUDED.partner_id
            """
            cur.execute(sql, (str(user1_id), str(user2_id), str(user2_id), str(user1_id)))
            conn.commit()
            return True
    except Exception as e:
        print(f"SQL Error in start_chat_session: {e}")
        return False
    finally:
        conn.close()


def end_chat_session(user_id):
    """إنهاء المحادثة وحذف الارتباط من قاعدة البيانات"""
    conn = get_db_connection()
    partner_id = None
    if not conn: return None
    try:
        with conn.cursor() as cur:
            # 1. جلب معرف الطرف الآخر قبل الحذف
            cur.execute("SELECT partner_id FROM active_chats WHERE user_id = %s", (user_id,))
            res = cur.fetchone()
            partner_id = res[0] if res else None

            # 2. حذف الارتباط للطرفين نهائياً
            if partner_id:
                cur.execute("DELETE FROM active_chats WHERE user_id IN (%s, %s)", (user_id, partner_id))
            else:
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
            [KeyboardButton("📍 تحديث موقعي")],
            [KeyboardButton("ℹ️ حالة اشتراكي")],
            [KeyboardButton("📞 تواصل مع الإدارة")] # تم إضافة الزر هنا
        ], resize_keyboard=True)

     # للراكب
    return ReplyKeyboardMarkup([
        [KeyboardButton("🚖 طلب رحلة")], 
        [KeyboardButton("📞 تواصل مع الإدارة")]
    ], resize_keyboard=True)

# ==================== 🤖 4. المعالجات (Handlers) ====================





async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "عزيزي"
    
    # 1. تنظيف الذاكرة وتحديث الكاش
    context.user_data.clear()
    await sync_all_users()

    # 2. جلب بيانات المستخدم من الكاش
    user = USER_CACHE.get(user_id) or USER_CACHE.get(str(user_id))
    
    has_phone = False
    if user:
        phone = str(user.get('phone', ''))
        if phone and phone not in ['0000000000', 'None', '']:
            has_phone = True

    # 3. معالجة الدخول بدون روابط عميقة (Start عادي)
    if not context.args and has_phone:
        await update.message.reply_text(
            f"👋 مرحباً بك مجدداً يا {user['name']}", 
            reply_markup=get_main_kb(user['role'], user['is_verified'])
        )
        return

    # 4. معالجة الروابط العميقة (Deep Linking)
    if context.args:
        arg_value = context.args[0]

        # --- حالة طلب رحلة (order_) ---
        if arg_value.startswith("order_"):
            target_id = arg_value.replace("order_", "")

            # أ) المستخدم غير مسجل
            if not has_phone:
                context.user_data['state'] = 'WAIT_RIDER_PHONE'
                context.user_data['temp_name'] = first_name
                context.user_data['pending_order_driver'] = target_id 
                
                await update.message.reply_text(
                    f"👋 أهلاً بك يا {first_name}!\n\n"
                    "لإتمام طلبك، نحتاج لتوثيق حسابك.\n"
                    "✏️ **يرجى كتابة رقم جوالك الآن** (مثال: 05xxxxxxx):",
                    reply_markup=ReplyKeyboardRemove(),
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            # ب) المستخدم مسجل -> تحديد نص الرسالة بناءً على نوع الطلب
            # ✅ تم توحيد اسم المتغير هنا إلى msg_text (حروف صغيرة) لمنع الـ Crash
            if target_id == "general":
                context.user_data['state'] = 'WAIT_GENERAL_DETAILS'
                msg_text = "🌍 **إلى أين وجهتك؟**"
            else:
                context.user_data['driver_to_order'] = target_id
                context.user_data['state'] = 'WAIT_TRIP_DETAILS'
                msg_text = "📝 **اكتب تفاصيل مشوارك الآن** لإرسالها للكابتن:"

            await update.message.reply_text(
                f"✅ مرحباً بك مجدداً يا {first_name}\n\n{msg_text}",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ إلغاء الطلب")]], resize_keyboard=True),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # --- حالات التسجيل ---
        elif arg_value in ["driver_reg", "reg_driver"]:
            context.user_data['state'] = 'WAIT_NAME'
            context.user_data['reg_role'] = 'driver'
            await update.message.reply_text(
                "🚖 **أهلاً بك يا كابتن**\nيرجى كتابة اسمك الثلاثي للبدء في التسجيل:",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode=ParseMode.MARKDOWN
            )
            return
            
        elif arg_value == "reg_rider":
            context.user_data['state'] = 'WAIT_RIDER_PHONE'
            context.user_data['temp_name'] = first_name
            await update.message.reply_text(
                f"🎉 حياك الله يا {first_name}!\nللتسجيل، يرجى **كتابة رقم جوالك**:",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # 5. إذا وصل الكود هنا ولم ينفذ أي Return (مستخدم جديد بدون رابط)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 تسجيل كراكب", callback_data="reg_rider"),
         InlineKeyboardButton("🚗 تسجيل ككابتن", callback_data="reg_driver")]
    ])
    await update.message.reply_text(
        f"مرحباً بك {first_name}، أنت غير مسجل لدينا.\nاختر نوع الحساب للبدء:", 
        reply_markup=kb
    )

# دالة مساعدة للتسجيل التلقائي لضمان عدم تكرار الكود

# --- التسجيل ---
# --- التسجيل المحدث ---

async def register_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    data = query.data
    user_id = user.id
    await query.answer()

    # --- [1] قسم طلب الرحلات (للراكب) ---
    
    # أ- عرض قائمة الأحياء للراكب
    if data == "order_by_district":
        districts = CITIES_DISTRICTS.get("المدينة المنورة", [])
        keyboard = []
        for i in range(0, len(districts), 2):
            row = [InlineKeyboardButton(districts[i], callback_data=f"searchdist_{districts[i]}")]
            if i + 1 < len(districts):
                row.append(InlineKeyboardButton(districts[i+1], callback_data=f"searchdist_{districts[i+1]}"))
            keyboard.append(row)
        
        await query.edit_message_text(
            "📍 **أحياء المدينة المنورة**\nاختر الحي للبحث عن كباتن متوفرين فيه:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    # عند ضغط السائق على "حفظ وإنهاء"
        # عند ضغط السائق على "حفظ وإنهاء"
    elif data == "driver_home":
        # 1. جلب بيانات السائق الحالية لعرض الأحياء التي تم حفظها (اختياري للتوثيق)
        user_info = USER_CACHE.get(user_id, {})
        saved_dists = user_info.get('districts', "لا توجد أحياء مختارة")
        if not saved_dists: saved_dists = "لا توجد أحياء مختارة"
        
        # 2. تحويل الرسالة من "قائمة أزرار" إلى "نص تأكيدي" فقط (ستختفي الأزرار هنا)
        confirm_text = (
            "✅ **تم حفظ الأحياء بنجاح!**\n\n"
            f"📍 نطاق عملك الحالي:\n_{saved_dists}_\n\n"
            "يمكنك الآن استقبال الطلبات من الركاب في هذه المناطق."
        )
        
        await query.edit_message_text(
            text=confirm_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=None  # هذا السطر هو المسؤول عن إخفاء قائمة الأزرار تماماً
        )

        # 3. إرسال الكيبورد الرئيسي للسائق في رسالة جديدة لكي يتمكن من إكمال استخدامه للبوت
        await context.bot.send_message(
            chat_id=user_id,
            text="الآن، يمكنك العودة لمهامك من القائمة أدناه:",
            reply_markup=get_main_kb('driver', user_info.get('is_verified', True))
        )

    # --- [5] قسم قبول الرحلات (للسائق) ---
    

    # ب- معالجة اختيار حي معين والبحث عن كباتن
    elif data.startswith("searchdist_"):
        target_dist = data.split("_")[1]
        await sync_all_users() # تحديث البيانات من القاعدة
        
        def clean(t): return t.replace("ة", "ه").replace("أ", "ا").replace("إ", "ا").strip()
        target_clean = clean(target_dist)

        # البحث عن الكباتن الذين لديهم هذا الحي في ملفهم
        matched = [
            d for d in CACHED_DRIVERS 
            if d.get('districts') and target_clean in clean(d['districts'])
        ]

        if matched:
            kb = []
            for d in matched[:10]:
                kb.append([InlineKeyboardButton(f"🚖 اطلب الكابتن {d['name']}", url=f"https://t.me/{context.bot.username}?start=order_{d['user_id']}")])
            
            await query.edit_message_text(
                f"✅ وجدنا كباتن في حي **{target_dist}**:\nاضغط على الكابتن لطلب المشوار:",
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.edit_message_text(
                f"📍 لا يوجد كباتن مسجلين في حي **{target_dist}** حالياً.\nجرب الطلب عبر الموقع (GPS).",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🌍 طلب بالموقع", callback_data="order_general")]])
            )

    # --- [2] قسم إدارة الأحياء (للسائق) ---
    
    elif data == "manage_districts":
        districts = CITIES_DISTRICTS.get("المدينة المنورة", [])
        user_info = USER_CACHE.get(user_id, {})
        current_dists = user_info.get('districts', "") or ""
        
        keyboard = []
        for d in districts:
            # إضافة علامة ✅ للحي المختار مسبقاً
            status = "✅ " if d in current_dists else "❌ "
            keyboard.append([InlineKeyboardButton(f"{status}{d}", callback_data=f"toggle_{d}")])
        
        keyboard.append([InlineKeyboardButton("💾 حفظ وإنهاء", callback_data="driver_home")])
        await query.edit_message_text("📝 اختر الأحياء التي تعمل بها (اضغط للتبديل):", reply_markup=InlineKeyboardMarkup(keyboard))


    # --- [4] قسم إدارة المشرفين (قبول/رفض الكباتن) ---
    
    # حالة قبول الكابتن
    if data.startswith("verify_ok_"):
        target_driver_id = int(data.split("_")[2])
        
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET is_verified = True WHERE user_id = %s", (target_driver_id,))
                conn.commit()
            conn.close()
            
            # تحديث الكاش فوراً
            await sync_all_users(force=True)
            
            # إشعار الأدمن بنجاح العملية
            await query.edit_message_text(f"✅ تم تفعيل حساب الكابتن ({target_driver_id}) بنجاح.")
            
            # إشعار الكابتن بتفعيل حسابه
            try:
                await context.bot.send_message(
                    chat_id=target_driver_id,
                    text="🎉 **أبشرك يا كابتن!**\nتم مراجعة حسابك وتفعيله بنجاح. يمكنك الآن استقبال الطلبات وتحديث أحيائك.",
                    reply_markup=get_main_kb('driver', True)
                )
            except: pass

    # حالة رفض الكابتن
    elif data.startswith("verify_no_"):
        target_driver_id = int(data.split("_")[2])
        
        await query.edit_message_text(f"❌ تم رفض طلب انضمام الكابتن ({target_driver_id}).")
        
        try:
            await context.bot.send_message(
                chat_id=target_driver_id,
                text="⚠️ نعتذر منك يا كابتن، تم رفض طلب انضمامك حالياً. يمكنك التواصل مع الإدارة للاستفسار."
            )
        except: pass


    elif data.startswith("toggle_"):
        # مستوى الإزاحة هنا هو 8 مسافات (إذا كانت الدالة تبدأ بـ 0)
        dist_name = data.split("_")[1]
        
        # 1. جلب البيانات من الكاش المحلي مع التحقق من وجود المستخدم
        if user_id not in USER_CACHE:
            USER_CACHE[user_id] = {'districts': ""}
            
        user_info = USER_CACHE[user_id]
        current_str = user_info.get('districts', "") or ""
        
        # تحويل النص إلى قائمة
        current_list = [x.strip() for x in current_str.replace("،", ",").split(",") if x.strip()]
        
        # 2. التبديل الفوري في الذاكرة
        if dist_name in current_list:
            current_list.remove(dist_name)
            alert_msg = f"❌ تم إزالة {dist_name}"
        else:
            current_list.append(dist_name)
            alert_msg = f"✅ تم إضافة {dist_name}"
        
        # 3. تحديث الكاش المحلي
        new_districts_str = ",".join(current_list)
        USER_CACHE[user_id]['districts'] = new_districts_str

        # 4. بناء لوحة المفاتيح الجديدة
        districts = CITIES_DISTRICTS.get("المدينة المنورة", [])
        keyboard = []
        for i in range(0, len(districts), 2):
            row = []
            for d in districts[i:i+2]:
                status = "✅ " if d in current_list else "❌ "
                row.append(InlineKeyboardButton(f"{status}{d}", callback_data=f"toggle_{d}"))
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("💾 حفظ وإنهاء", callback_data="driver_home")])
        
        # 5. التحديث الآمن لواجهة المستخدم (التصحيح هنا)
        try:
            # استخدام query.message.edit_reply_markup بدلاً من query.edit_message_reply_markup
            await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
            await query.answer(alert_msg)
        except Exception as e:
            if "Message is not modified" not in str(e):
                print(f"UI Update Error: {e}")
                await query.answer("تم التحديث")

        # 6. التحديث في الخلفية
        asyncio.create_task(update_districts_in_db(user_id, new_districts_str))

    # --- [3] قسم التسجيل (الذي كان لديك) ---
    elif data in ["reg_rider", "reg_driver"]:
        role = "rider" if data == "reg_rider" else "driver"
        context.user_data['reg_role'] = role
        
        if role == "rider":
            # بدلاً من الإتمام الفوري، نطلب رقم الجوال
            context.user_data['state'] = 'WAIT_RIDER_PHONE'
            # نرسل رسالة جديدة تحتوي على زر مشاركة الرقم
            keyboard = [[KeyboardButton("📱 مشاركة رقم الجوال", request_contact=True)]]
            await query.message.reply_text(
                text=f"🎉 **أهلاً بك يا {user.first_name} في نظام الركاب**\n\nمن فضلك اضغط على الزر بالأسفل لمشاركة رقم جوالك لإتمام التسجيل:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True),
                parse_mode=ParseMode.MARKDOWN
            )
            # حذف رسالة الانلاين السابقة لتنظيف الشات
            try: await query.delete_message()
            except: pass
        else:
            context.user_data['state'] = 'WAIT_NAME'
            await query.edit_message_text(text="📝 يرجى كتابة **اسمك الثلاثي** الآن:", parse_mode=ParseMode.MARKDOWN)

async def complete_registration(update, context, name, phone=None, plate=None):
    user = update.effective_user
    user_id = user.id
    chat_id = update.effective_chat.id
    username = f"@{user.username}" if user.username else "لا يوجد معرف"
    
    # جلب الدور وحفظه في متغير محلي قبل مسح البيانات
    role = context.user_data.get('reg_role', 'rider') 
    phone = phone if phone else context.user_data.get('reg_phone', '0000000000')
    plate = plate if plate else context.user_data.get('reg_plate', 'غير محدد')

    conn = get_db_connection()
    if not conn: return

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            is_verified = (role == 'rider')
            cur.execute("""
                INSERT INTO users (user_id, chat_id, role, name, phone, plate_number, is_verified)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    phone = EXCLUDED.phone,
                    plate_number = EXCLUDED.plate_number,
                    role = EXCLUDED.role,
                    is_verified = EXCLUDED.is_verified
                RETURNING *;
            """, (user_id, chat_id, role, name, phone, plate, is_verified))
            conn.commit()
            
        await sync_all_users()
        # انقلنا المسح إلى ما بعد إتمام الفحوصات لضمان عدم فقدان البيانات
        
        if role == 'driver':
            support_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 مراسلة الإدارة", callback_data="contact_admin_start")],
                [InlineKeyboardButton("👤 الحساب المباشر", url="https://t.me/x3FreTx")]
            ])
            
            # استخدام HTML بدلاً من Markdown لضمان عدم تعطل الإرسال بسبب الرموز
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"✅ <b>أبشرك تم استلام طلبك يا كابتن {name}</b>\n\n"
                    f"🚗 <b>بيانات السيارة:</b> {plate}\n"
                    "حسابك الحين تحت المراجعة، وأول ما يتفعل بيجيك إشعار. خلك قريب!"
                ),
                reply_markup=support_kb,
                parse_mode="HTML"
            )

            await context.bot.send_message(
                chat_id=chat_id,
                text="📋 قائمة التحكم الخاصة بك:",
                reply_markup=get_main_kb('driver', False)
            )

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ قبول", callback_data=f"verify_ok_{user_id}"),
                 InlineKeyboardButton("❌ رفض", callback_data=f"verify_no_{user_id}")]
            ])
            
            admin_text = (
                f"🔔 <b>تسجيل كابتن جديد للمراجعة</b>\n"
                f"─────────────────\n"
                f"👤 <b>الاسم:</b> {name}\n"
                f"📱 <b>الجوال:</b> <code>{phone}</code>\n"
                f"🔢 <b>اللوحة:</b> <code>{plate}</code>\n"
                f"🆔 <b>المعرف:</b> {username}\n"
                f"🔗 <b>رابط الحساب:</b> <a href='tg://user?id={user_id}'>اضغط هنا</a>\n"
                f"📄 <b>ID العمل:</b> <code>{user_id}</code>"
            )
            
            for aid in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=aid, 
                        text=admin_text, 
                        reply_markup=kb,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    print(f"Error sending to admin {aid}: {e}")
        
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎉 <b>يا هلا بيك يا {name}</b>\nتم تفعيل حسابك كراكب بنجاح، تقدر تطلب مشاويرك من الحين!",
                reply_markup=get_main_kb('rider', True),
                parse_mode="HTML"
            )

        # مسح البيانات المؤقتة في نهاية العملية تماماً
        context.user_data.clear()

    except Exception as e:
        print(f"Error registration: {e}")
        await context.bot.send_message(chat_id=chat_id, text="⚠️ حدث خطأ أثناء التسجيل، جرب مرة ثانية.")
    finally:
        if conn: conn.close()


# --- طلب الرحلات ---
async def order_ride_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌍 أقرب كابتن (بحث بالموقع)", callback_data="order_general")]
    ])
    await update.message.reply_text("🚖 **ابحث عن اقرب كابتن متواجد حولك؟**", reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

async def broadcast_general_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    r_lat = update.message.location.latitude if update.message and update.message.location else context.user_data.get('lat')
    r_lon = update.message.location.longitude if update.message and update.message.location else context.user_data.get('lon')

    if r_lat is None or r_lon is None: return []

    map_link = f"https://www.google.com/maps?q={r_lat},{r_lon}"
    price = context.user_data.get('order_price', 0)
    details = context.user_data.get('search_district', "موقع GPS")
    rider_id = update.effective_user.id

    sent_messages_info = [] 
    await sync_all_users()

    for d in CACHED_DRIVERS:
        # 1. تخطي الراكب نفسه أو من ليس لديه إحداثيات
        if d['user_id'] == rider_id or d.get('lat') is None: 
            continue
            
        # 2. التعديل الجديد: منع السائقين غير الموثقين من استلام الطلبات
        # نفترض أن قيمة التوثيق مخزنة في 'is_verified' داخل الكاش
        if not d.get('is_verified', False):
            continue

        dist = get_distance(r_lat, r_lon, d['lat'], d['lon'])

        # 3. إرسال الطلب فقط لمن هم في نطاق 15 كم
        if dist <= 15.0: 
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"✅ قبول ({price} ريال)", callback_data=f"accept_gen_{rider_id}_{price}")],
                [InlineKeyboardButton("💵 اقتراح سعر آخر", callback_data=f"bid_req_{rider_id}")] 
            ])

            try:
                msg = await context.bot.send_message(
                    chat_id=d['user_id'],
                    text=(f"🚨 **طلب جديد قريب منك!**\n\n"
                          f"📍 المسافة: {dist:.1f} كم\n"
                          f"📝 الوجهة: {details}\n"
                          f"💰 العرض: {price} ريال\n\n"
                          f"🗺 [موقع الراكب على الخريطة]({map_link})"),
                    reply_markup=kb,
                    parse_mode=ParseMode.MARKDOWN
                )
                sent_messages_info.append({'chat_id': d['user_id'], 'message_id': msg.message_id})
            except: 
                continue
            
    return sent_messages_info


async def end_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # 1. جلب الشريك قبل حذف الجلسة لضمان الحصول على الـ ID
    partner_id = get_chat_partner(user_id)
    
    # 2. حذف الجلسة من قاعدة البيانات
    end_chat_session(user_id)
    
    # 3. تنظيف ذاكرة البوت المحلية للمستخدم الحالي
    context.user_data.pop('chat_with', None)
    context.user_data.pop('order_status', None)
    
    # 4. تحديث الكاش لضمان قراءة الدور (Role) الصحيح
    await sync_all_users()

    # --- تعريف الدالة الداخلية ---
        # --- تعريف الدالة الداخلية المصححة ---
    async def reset_user_menu(uid, is_initiator=False):
        # 1. محاولة جلب البيانات (بالرقم وبالنص لضمان المطابقة)
        user_info = USER_CACHE.get(uid) or USER_CACHE.get(str(uid)) or {}
        
        # 2. استخراج الرتبة مع تحويلها لحروف صغيرة لضمان المطابقة مع get_main_kb
        role = str(user_info.get('role', 'rider')).lower()
        
        # 3. التأكد من حالة التوثيق (اجعلها True كافتراضي إذا لم توجد لفتح القائمة)
        is_v = user_info.get('is_verified', True)
        
        # (اختياري) طباعة للتصحيح في التيرمنال لمعرفة ماذا يرى البوت
        print(f"DEBUG: User {uid} is resetting to role: {role}")

        msg = "🛑 تم إنهاء المحادثة والعودة للقائمة الرئيسية." if is_initiator else "🛑 قام الطرف الآخر بإنهاء المحادثة."
        
        try:
            # استدعاء دالتك get_main_kb
            kb = get_main_kb(role, is_v)
            
            await context.bot.send_message(
                chat_id=uid,
                text=msg,
                reply_markup=kb
            )
        except Exception as e:
            print(f"Failed to reset menu for {uid}: {e}")

    # 5. استدعاء الدالة (تأكد من مطابقة الاسم: reset_user_menu)
    await reset_user_menu(user_id, is_initiator=True)
    
    # 6. تنفيذ إعادة الضبط للطرف الآخر (الشريك)
    if partner_id:
        # مسح ذاكرة الشريك المؤقتة لضمان خروجه من وضع الـ Relay
        try:
            context.application.drop_user_data(partner_id) 
        except: pass
        
        await reset_user_menu(partner_id, is_initiator=False)

    # إيقاف المعالجة لضمان عدم مرور الرسالة لمعالجات أخرى
    raise ApplicationHandlerStop


# --- المعالج الشامل (Global Handler) ---


# --- المعالج الشامل (Global Handler) ---
async def global_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. التحقق من وجود رسالة (أهم خطوة لمنع الانهيار)
    if not update.message:
        return

    # 2. استخراج البيانات بأمان (تعديل جوهري هنا)
    user = update.effective_user
    if not user: return # حماية إضافية إذا لم يستطع البوت التعرف على المستخدم
    
    user_id = user.id
    state = context.user_data.get('state')
    
    # استخراج النص مع ضمان عدم كونه None حتى لو كانت الرسالة صورة أو موقع
    text = update.message.text.strip() if update.message.text else ""


    if text == "🔙 العودة للقائمة الرئيسية":
        # 1. تصفير الحالة (State) لضمان الخروج من أي عمليات معلقة
        context.user_data['state'] = None
    
        # 2. جلب حالة التوثيق فقط (لأنها مهمة لشكل أزرار السائق)
        user_data = USER_CACHE.get(user_id) or {}
        is_verified = user_data.get('is_verified', True)

        # 3. إرسال القائمة الرئيسية مع تحديد الرتبة "driver" يدوياً
        await update.message.reply_text(
            "🏠 تم الرجوع لقائمة الكابتن.",
            reply_markup=get_main_kb('driver', is_verified) # قمنا بتغيير role إلى 'driver' هنا
        )
        return
        
    if state == 'WAIT_ADMIN_MESSAGE':
        if text == "❌ إلغاء المراسلة":
            context.user_data['state'] = None
            
            # جلب البيانات من الكاش (المرتبط بقاعدة البيانات)
            user_info = USER_CACHE.get(user_id, {})
            
            # جلب القيم الحقيقية
            # هنا البوت سيأخذ الـ role والـ is_verified كما هي في السوبابيس (Supabase)
            role = user_info.get('role') 
            verified_status = user_info.get('is_verified')

            await update.message.reply_text(
                "تم الإلغاء.", 
                reply_markup=get_main_kb(role, verified_status)
            )
            return


    # ---------------------------------------------------------
    # [الفلتر الأول] المحادثات النشطة (Chat Relay)
    # ---------------------------------------------------------
    # إذا كان المستخدم يتحدث حالياً مع طرف آخر (كابتن/راكب)، اخرج فوراً
    if get_chat_partner(user_id):
        return 

    # ---------------------------------------------------------
    # [الفلتر الثاني] معالجة الموقع (Location)
    # ---------------------------------------------------------
    if update.message.location:
        # سواء كان لطلب أو تحديث عادي، نحوله لدالة الموقع ونخرج
        return await location_handler(update, context)

        # --- [تعديل] خطوات تسجيل السائق المحدثة ---
    # استلام سعر المزايدة من السائق
    if context.user_data.get('state') == 'DRIVER_SENDING_BID' and update.message.text:
        bid_price = update.message.text
        rider_id = context.user_data.get('bidding_for_rider')
        driver = update.effective_user

        # التحقق من أن المدخل رقمي
        if not bid_price.isdigit():
            await update.message.reply_text("⚠️ يرجى إرسال السعر كأرقام فقط (مثال: 50).")
            return

        # إنشاء أزرار القبول والرفض للراكب
                # إنشاء أزرار القبول والرفض للراكب (تعديل المعرفات لتطابق المعالج المالي الملغي)
        kb_to_rider = InlineKeyboardMarkup([
            [
                # استخدمنا final_start_ لتفعيل الدردشة المباشرة فوراً
                InlineKeyboardButton(f"✅ قبول ({bid_price} ريال)", callback_data=f"final_start_{driver.id}_{bid_price}"),
                InlineKeyboardButton("❌ رفض العرض", callback_data=f"reject_ride_{driver.id}")
            ]
        ])

        # إرسال العرض للراكب في الخاص
        try:
            await context.bot.send_message(
                chat_id=rider_id,
                text=(f"💰 **وصلك عرض سعر جديد لمشوارك!**\n\n"
                      f"🚕 الكابتن: {driver.full_name}\n"
                      f"💵 السعر المقترح: {bid_price} ريال\n\n"
                      f"هل تود قبول هذا العرض؟"),
                reply_markup=kb_to_rider
            )
            await update.message.reply_text(f"✅ تم إرسال عرضك ({bid_price} ريال) للراكب. انتظر موافقته.")
        except:
            await update.message.reply_text("❌ فشل إرسال العرض للراكب (ربما قام بحظر البوت).")

        # تصفير حالة السائق ليعود للوضع الطبيعي
        context.user_data['state'] = None
        context.user_data.pop('bidding_for_rider', None)
        return

    
    # 1. استلام الاسم
    if state == 'WAIT_NAME':
        context.user_data['reg_name'] = text
        # --- الإضافة الهامة هنا ---
        context.user_data['reg_role'] = 'driver' 
        # -------------------------
        context.user_data['state'] = 'WAIT_PHONE'
        await update.message.reply_text("📱 **أبشر، الحين أرسل رقم جوالك:**\n(مثال: 05xxxxxxxx)")
        return

    if state == 'WAIT_PHONE':
        phone_input = text.strip()
        if not re.fullmatch(r'05\d{8}', phone_input):
            await update.message.reply_text("⚠️ **الرقم غير صحيح..**\nلازم يبدأ بـ 05 ويتكون من 10 أرقام.")
            return
        
        # حفظ الرقم والانتقال لطلب اللوحة
        context.user_data['reg_phone'] = phone_input
        context.user_data['state'] = 'WAIT_PLATE'
        await update.message.reply_text("🔢 **ممتاز، الحين أرسل رقم لوحة السيارة:**\n(مثال: أ ب ج 1234)")
        return

    if state == 'WAIT_PLATE':
        plate_input = text.strip()
        
        # جلب البيانات المحفوظة في الخطوات السابقة
        name = context.user_data.get('reg_name')
        phone = context.user_data.get('reg_phone')
        
        # نؤكد أن الدور هو سائق قبل استدعاء دالة الإتمام
        context.user_data['reg_role'] = 'driver'
        
        # استدعاء دالة الإتمام مع تمرير القيم مباشرة
        await complete_registration(update, context, name, phone, plate_input)
        
        context.user_data['state'] = None
        return


    # المرحلة 1: استلام التفاصيل والانتقال للسعر
    if state == 'WAIT_RIDE_DETAILS':
        context.user_data['ride_details'] = text
        context.user_data['state'] = 'WAIT_RIDE_PRICE'
        await update.message.reply_text("💰 **الخطوة 2 من 3**\n\nكم السعر الذي تعرضه لهذا المشوار؟")
        return

    # المرحلة 2: استلام السعر والانتقال للموقع
    elif state == 'WAIT_RIDE_PRICE':
        context.user_data['ride_price'] = text
        context.user_data['state'] = 'WAIT_RIDE_LOCATION'
        
        # إنشاء زر طلب الموقع الحقيقي
        kb = ReplyKeyboardMarkup([
            [KeyboardButton("📍 مشاركة موقعي الآن للبحث", request_location=True)],
            [KeyboardButton("❌ إلغاء الطلب")]
        ], resize_keyboard=True, one_time_keyboard=True)
        
        await update.message.reply_text(
            "🌍 **الخطوة الأخيرة: تحديد موقعك**\n\nاضغط على الزر بالأسفل لإرسال موقعك لنحدد أقرب كابتن لك:",
            reply_markup=kb
        )
        return

    
    
    # استخراج البيانات
    
    
    

    # ---------------------------------------------------------
    # [الفلتر الثالث] معالجة حالات البوت (States)
    # ---------------------------------------------------------

        # --- أ) خطوات التسجيل ---
        # --- [تعديل] خطوات تسجيل السائق المحدثة ---
    
    # 1. استلام الاسم
    



    # --- منطق بحث الأدمن عن مستخدم بالجوال ---
        # --- منطق بحث الأدمن عن مستخدم بالـ ID ---
    if state == 'ADMIN_WAIT_SEARCH_ID' and user_id in ADMIN_IDS:
        search_id = text.strip()
        
        # التأكد أن المدخل أرقام فقط
        if not search_id.isdigit():
            await update.message.reply_text("⚠️ يرجى إدخال معرف (ID) صحيح (أرقام فقط).")
            return

        conn = get_db_connection()
        user_found = None
        if conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # تغيير الاستعلام للبحث بـ user_id
                cur.execute("SELECT * FROM users WHERE user_id = %s", (search_id,))
                user_found = cur.fetchone()
            conn.close()

        if user_found:
            res_txt = (
                f"✅ **بيانات المستخدم:**\n\n"
                f"👤 **الاسم:** {user_found['name']}\n"
                f"🆔 **ID:** `{user_found['user_id']}`\n"
                f"📱 **الجوال:** {user_found['phone'] or 'غير مسجل'}\n"
                f"🛠 **الرتبة:** {'كابتن' if user_found['role'] == 'driver' else 'عميل'}\n"
                f"💰 **الرصيد:** {user_found['balance']} ريال\n"
                f"🚫 **الحالة:** {'❌ محظور' if user_found['is_blocked'] else '✅ نشط'}"
            )
            # أزرار تحكم سريعة لهذا المستخدم
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 شحن رصيد", callback_data=f"admin_quickcash_{user_found['user_id']}")],
                [InlineKeyboardButton("🚫 حظر/إلغاء حظر", callback_data=f"admin_toggle_block_{user_found['user_id']}")]
            ])
            await update.message.reply_text(res_txt, reply_markup=kb, parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ لا يوجد مستخدم مسجل في القاعدة يحمل المعرف: `{search_id}`")
        
        context.user_data['state'] = None 
        return


    # --- استقبال رقم الجوال وإتمام التسجيل ---
    if state == 'WAIT_RIDER_PHONE':
        phone = text.strip()
        user_info = update.effective_user
        
        # 1. التحقق من صحة الرقم (بدءاً بـ 05 وطول 10 أرقام)
        if not re.fullmatch(r'05\d{8}', phone):
            await update.message.reply_text("⚠️ الرقم غير صحيح.. لازم يبدأ بـ 05 ويتكون من 10 أرقام.")
            return

        # 2. إنشاء الحساب أو تحديثه في القاعدة
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (user_id, chat_id, role, name, phone, is_verified)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE 
                    SET phone = EXCLUDED.phone, role = 'rider', is_verified = True
                """, (user_id, update.effective_chat.id, 'rider', user_info.full_name, phone, True))
                conn.commit()
            conn.close()
            await sync_all_users(force=True)

        # 3. فحص سبب التسجيل (رابط خارجي أم يدوي)
        pending_driver = context.user_data.get('pending_order_driver')
        
        if pending_driver:
            if pending_driver == "general":
                context.user_data.update({
                    'state': 'WAIT_GENERAL_DETAILS',
                    'pending_order_driver': None
                })
                await update.message.reply_text("✅ تم تسجيلك بنجاح.\n\nالآن **أرسل وجهتك** (مثال: من حي المروج إلى العزيزية):")
            else:
                context.user_data.update({
                    'driver_to_order': pending_driver,
                    'state': 'WAIT_TRIP_DETAILS',
                    'pending_order_driver': None
                })
                await update.message.reply_text(
                    "✅ تم تسجيلك بنجاح.\n\nالآن **أرسل وجهتك** لإرسالها للكابتن:",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ إلغاء الطلب")]], resize_keyboard=True)
                )
        else:
            # حالة التسجيل اليدوي (من داخل البوت بدون طلب مسبق)
            context.user_data['state'] = None 
            await update.message.reply_text(
                "🎉 **أهلاً بك! تم إكمال تسجيلك بنجاح.**\n\nيمكنك الآن طلب رحلتك الأولى بالضغط على (🚖 طلب رحلة) من القائمة بالأسفل.",
                reply_markup=get_main_kb("rider", True) 
            )
        return

        
    if update.message.text == "📍 تحديث موقعي":
        # إنشاء لوحة مفاتيح تحتوي على زر خاص بطلب الموقع مع إزاحة 4 مسافات
        location_kb = ReplyKeyboardMarkup([
            [KeyboardButton("📍 إرسال موقعي الآن", request_location=True)],
            [KeyboardButton("🔙 العودة للقائمة الرئيسية")]
        ], resize_keyboard=True, one_time_keyboard=True)
        
        await update.message.reply_text(
            "يرجى الضغط على الزر أدناه لمشاركة موقعك الحالي وتحديثه في النظام:",
            reply_markup=location_kb
        )
        return

    # --- معالجة زر العودة للقائمة الرئيسية ---
    


    # --- منطق حذف العضو ---
    if state == 'ADMIN_WAIT_DELETE_ID' and user_id in ADMIN_IDS:
        target_id = text.strip()
        if not target_id.isdigit():
            await update.message.reply_text("❌ خطأ: يرجى إرسال ID صحيح (أرقام فقط).")
            return

        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    # التحقق من وجود المستخدم قبل الحذف
                    cur.execute("SELECT name FROM users WHERE user_id = %s", (target_id,))
                    user_exists = cur.fetchone()
                    
                    if user_exists:
                        # تنفيذ الحذف
                        cur.execute("DELETE FROM users WHERE user_id = %s", (target_id,))
                        conn.commit()
                        await update.message.reply_text(f"✅ تم حذف المستخدم ( {user_exists[0]} ) وجميع بياناته بنجاح.")
                    else:
                        await update.message.reply_text("❌ لم يتم العثور على مستخدم بهذا الـ ID.")
            except Exception as e:
                await update.message.reply_text(f"⚠️ حدث خطأ أثناء الحذف: {e}")
            finally:
                conn.close()
        
        context.user_data['state'] = None  # إعادة تعيين الحالة
        return


        # --- ب) طلب مشوار خاص (كابتن محدد) ---

    if state == 'WAIT_TRIP_DETAILS':
        context.user_data['trip_details'] = text 
        context.user_data['state'] = 'WAIT_TRIP_PRICE'
        await update.message.reply_text("💰 **كم السعر المعروض؟** (أرقام فقط):")
        return

    if state == 'WAIT_TRIP_PRICE':
        if not text.isdigit(): # التأكد أنها أرقام فقط
            await update.message.reply_text("⚠️ أرقام فقط لو سمحت.")
            return

        price = text 
        details = context.user_data.get('trip_details')
        driver_id = context.user_data.get('driver_to_order')
        
        # إعداد الزر للكابتن
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ قبول", callback_data=f"accept_ride_{user_id}_{price}"),
             InlineKeyboardButton("❌ رفض", callback_data=f"reject_ride_{user_id}")]
        ])
        
        try:
            await context.bot.send_message(
                chat_id=driver_id,
                text=f"🚨 **طلب خاص لك!**\n📝 التفاصيل: {details}\n💰 السعر: {price} ريال",
                reply_markup=kb
            )
            await update.message.reply_text("✅ تم إرسال العرض للكابتن، انتظر الموافقة.")
        except:
            await update.message.reply_text("❌ تعذر الوصول للكابتن (قد يكون حظر البوت).")
        
        context.user_data['state'] = None 
        return

    # --- ج) طلب مشوار عام (لأقرب كابتن/GPS) ---
    if state == 'WAIT_GENERAL_DETAILS':
        context.user_data['search_district'] = text 
        context.user_data['state'] = 'WAIT_GENERAL_PRICE'
        await update.message.reply_text("💰 **كم السعر المقترح؟** (أرقام فقط):")
        return

    if state == 'WAIT_GENERAL_PRICE':
        if not text.replace('.', '', 1).isdigit():
            await update.message.reply_text("⚠️ أرقام فقط.")
            return

        context.user_data['order_price'] = float(text)
        
        # طلب الموقع لإتمام العملية
        kb = ReplyKeyboardMarkup([
            [KeyboardButton("📍 مشاركة موقعي لإرسال الطلب", request_location=True)],
            [KeyboardButton("❌ إلغاء الطلب")]
        ], resize_keyboard=True, one_time_keyboard=True)
        
        await update.message.reply_text(
            "📍 الآن اضغط الزر بالأسفل لمشاركة موقعك وتعميم الطلب:",
            reply_markup=kb
        )
        context.user_data['state'] = 'WAIT_LOCATION_FOR_ORDER' 
        return
    # --- د) إعدادات السائقين والبحث ---
    if state == 'WAIT_DISTRICTS':
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET districts = %s WHERE user_id = %s", (text, user_id))
            conn.commit()
        conn.close() 
        
        await sync_all_users() 
        await update.message.reply_text("✅ تم تحديث مناطق عملك بنجاح.")
        context.user_data['state'] = None
        return

    if state == 'WAIT_ELITE_DISTRICT':
        found = []
        await sync_all_users() 
        
        for d in CACHED_DRIVERS:
            if d.get('districts') and text in d['districts']:
                found.append(d)

        if not found:
            await update.message.reply_text(f"❌ لا يوجد كابتن مسجل في حي '{text}' حالياً.")
        else:
            await update.message.reply_text(f"✅ وجدنا {len(found)} كابتن:")
            for d in found:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"📞 طلب {d['name']}", callback_data=f"book_{d['user_id']}_{text}")]])
                await update.message.reply_text(f"👤 {d['name']}\n🚗 {d.get('car_info', 'غير محدد')}", reply_markup=kb)
        
        context.user_data['state'] = None
        return

    # --- هـ) تواصل الإدارة الصريح ---
    if state == 'WAIT_ADMIN_MESSAGE':
        if text == "❌ إلغاء المراسلة":
            context.user_data['state'] = None
            await update.message.reply_text("تم الإلغاء.", reply_markup=get_main_kb(context.user_data.get('role', 'rider')))
            return
        pass 

    # ---------------------------------------------------------
    # [الفلتر الرابع] أوامر القائمة الرئيسية (Buttons)
    # ---------------------------------------------------------
    # نضع جميع نصوص الأزرار هنا لمنع وصولها للأدمن
    if text == "🚖 طلب رحلة":
        await order_ride_options(update, context)
        return

    if text == "📞 تواصل مع الإدارة":
        await contact_admin_start(update, context)
        return

    if text == "📍 تحديث موقعي":
        await update.message.reply_text("📍 لتحديث موقعك، أرسل (Location) من المشبك 📎")
        return

    if text == "💰 محفظتي":
        user_data = USER_CACHE.get(user_id)
        bal = user_data.get('balance', 0) if user_data else 0
        await update.message.reply_text(f"💳 رصيدك الحالي: {bal} ريال")
        return

    if text == "📍 مناطق عملي" or text == "📝 تحديث الأحياء":
        await districts_settings_view(update, context)
        return

    if text == "ℹ️ حالة اشتراكي":
        user_data = USER_CACHE.get(user_id)
        if user_data and user_data.get('subscription_expiry'):
             # تأكد أن expiry كائن datetime
             expiry = user_data['subscription_expiry']
             # تحويل بسيط للتاريخ
             fmt_date = expiry.strftime('%Y-%m-%d') if hasattr(expiry, 'strftime') else str(expiry)
             await update.message.reply_text(f"📅 اشتراكك ينتهي في: {fmt_date}")
        else:
             await update.message.reply_text("❌ ليس لديك اشتراك فعال.")
        return
    
    # يمكن إضافة "❌ إلغاء الطلب" هنا أيضاً إذا كان زر عام
    if text == "❌ إلغاء الطلب":
        context.user_data['state'] = None
        await update.message.reply_text("تم الإلغاء.", reply_markup=get_main_kb(context.user_data.get('role', 'rider')))
        return

    # ---------------------------------------------------------
    # [المرحلة النهائية] إرسال الرسائل المجهولة للأدمن
    # ---------------------------------------------------------
    # إذا وصل الكود هنا، فهذا يعني:
    # 1. ليست محادثة نشطة.
    # 2. ليست خطوة تسجيل أو طلب.
    # 3. ليس زر قائمة رئيسية.
    # إذن هي --> رسالة استفسار/دعم فني.

    # تأكيد أخير أنها في الخاص وليست في مجموعة
        # تعديل بسيط في النهاية
    # التأكد أن الرسالة خاصة، تحتوي نصاً، والمرسل ليس من الإدارة
    if update.message.chat.type == "private" and text and user_id not in ADMIN_IDS:
        
        # 1. تجهيز الرسالة للأدمن باستخدام HTML لمنع أخطاء الرموز الخاصة
        admin_text = (
            f"📩 <b>رسالة واردة (دعم فني)</b>\n"
            f"👤 <b>الاسم:</b> {user.full_name}\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
            f"🔗 <b>المعرف:</b> @{user.username if user.username else 'لا يوجد'}\n"
            f"📝 <b>النص:</b> {text}\n"
            f"─────────────────\n"
            f"💡 للرد عليه، قم بعمل (Reply) على هذه الرسالة."
        )

        # 2. أزرار التحكم
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🚫 حظر", callback_data=f"admin_block_{user_id}"),
                InlineKeyboardButton("💰 شحن", callback_data=f"admin_quickcash_{user_id}")
            ]
        ])

        # 3. الإرسال لكل المشرفين باستخدام التنسيق الجديد
        for aid in ADMIN_IDS:
            try:
                # إرسال بيانات المستخدم بتنسيق HTML
                await context.bot.send_message(
                    chat_id=aid, 
                    text=admin_text, 
                    reply_markup=kb, 
                    parse_mode="HTML" # تم التغيير من MARKDOWN إلى HTML لضمان عدم حدوث خطأ parse
                )
                # تحويل الرسالة الأصلية
                await context.bot.copy_message(
                    chat_id=aid, 
                    from_chat_id=user_id, 
                    message_id=update.message.message_id
                )
            except Exception as e:
                print(f"Error sending to admin {aid}: {e}")

        # 4. حفظ في السجل
        save_chat_log(user_id, ADMIN_IDS[0], text or "[ملف/موقع]", "support_msg")

        # 5. إشعار المستخدم
        await update.message.reply_text("📨 تم استلام رسالتك وتحويلها لفريق الدعم.")
        
        return

# --- معالجة المواقع (Location) ---

async def admin_panel_view(update, context):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    # جلب الإحصائيات
    conn = get_db_connection()
    stats = {"users": 0, "drivers": 0}
    if conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            stats['users'] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM users WHERE role = 'driver'")
            stats['drivers'] = cur.fetchone()[0]
        conn.close()

        keyboard = [
        [
            InlineKeyboardButton("🔍 بحث بالمعرف", callback_data="admin_search_id"),
            InlineKeyboardButton("🗑️ حذف عضو", callback_data="admin_delete_user_start")
        ],
        [
            InlineKeyboardButton("📢 إذاعة عامة", callback_data="admin_broadcast_opt"),
            InlineKeyboardButton("💰 شحن رصيد", callback_data="admin_manage_cash")
        ],
        [
            InlineKeyboardButton("🚫 المحظورين", callback_data="admin_manage_blocked"),
            InlineKeyboardButton("📜 سجل المحادثات", callback_data="admin_logs_help")
        ], # <--- هذه الفاصلة كانت ناقصة هنا
        [
            InlineKeyboardButton("👥 عرض الأعضاء", callback_data="admin_view_users_0")
        ]
    ]

    
    reply_markup = InlineKeyboardMarkup(keyboard)
    admin_text = (
        f"🛠 **لوحة تحكم الإدارة**\n\n"
        f"👥 إجمالي المستخدمين: {stats['users']}\n"
        f"🚖 عدد الكباتن: {stats['drivers']}\n\n"
        f"اختر من القائمة أدناه لإدارة النظام:"
    )

    # معالجة ذكية للإرسال والتعديل
    if update.callback_query:
        await update.callback_query.answer()
        try:
            # محاولة تعديل الرسالة الحالية
            await update.callback_query.edit_message_text(admin_text, reply_markup=reply_markup, parse_mode="Markdown")
        except Exception:
            # إذا فشل التعديل (رسالة محذوفة أو قديمة)، أرسل رسالة جديدة تماماً
            await context.bot.send_message(chat_id=user_id, text=admin_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        # إرسال رسالة جديدة في حال استخدام الأمر /admin
        await update.message.reply_text(admin_text, reply_markup=reply_markup, parse_mode="Markdown")

async def start_order_timer(context: ContextTypes.DEFAULT_TYPE, messages_info: list, rider_id: int, status_msg_id: int):
    try:
        # جلب البيانات الأولية
        await sync_all_users()
        user_data = USER_CACHE.get(rider_id) or USER_CACHE.get(str(rider_id)) or {}
        user_role = user_data.get('role', 'rider')
        is_verified = user_data.get('is_verified', False)

        for minutes_left in range(30, 0, -1):
            # تحديث نص الرسالة في بداية كل دقيقة
            try:
                await context.bot.edit_message_text(
                    chat_id=rider_id,
                    message_id=status_msg_id,
                    text=f"📡 جاري البحث عن كباتن...\n⏳ الوقت المتبقي لصلاحية الطلب: {minutes_left} دقيقة",
                    parse_mode="Markdown"
                )
            except Exception: pass

            # --- التحقق الذكي كل ثانية بدلاً من كل دقيقة ---
            for _ in range(60): 
                user_context_data = context.application.user_data.get(rider_id, {})
                if user_context_data.get('order_status') == 'ACCEPTED':
                    try:
                        await context.bot.delete_message(chat_id=rider_id, message_id=status_msg_id)
                    except: pass
                    return # الخروج فوراً عند القبول

                await asyncio.sleep(1) # انتظر ثانية واحدة فقط ثم تحقق مجدداً
            # ---------------------------------------------

        # منطق انتهاء الوقت (إذا لم يتم القبول)
        for info in messages_info:
            try:
                await context.bot.delete_message(chat_id=info['chat_id'], message_id=info['message_id'])
            except: pass

        await context.bot.send_message(
            chat_id=rider_id, 
            text="✨ **شكراً لثقتكم بنا، ممتنون لاختياركم خدمتنا.**\n\nيمكنك الآن تحديث موقعك وإرسال طلب جديد لنقوم بخدمتك بشكل أفضل. نحن دائماً بانتظارك! 🌹",
            reply_markup=get_main_kb(user_role, is_verified),
            parse_mode="Markdown"
        )

        if rider_id in context.application.user_data:
            context.application.user_data[rider_id]['order_status'] = None

    except Exception as e:
        print(f"Error in start_order_timer: {e}")


async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.edited_message
    if not msg or not msg.location:
        return

    user_id = update.effective_user.id
    lat_val, lon_val = msg.location.latitude, msg.location.longitude
    state = context.user_data.get('state')
    current_time = time.time()

    # جلب بيانات المستخدم من الكاش
    user_data = USER_CACHE.get(user_id) or {}
    user_role = user_data.get('role', UserRole.RIDER) # الافتراضي راكب

    # 1. تحديث الكاش المحلي فوراً
    if user_id in USER_CACHE:
        USER_CACHE[user_id]['lat'] = lat_val
        USER_CACHE[user_id]['lon'] = lon_val
    
    # 2. تحديث قاعدة البيانات "بذكاء" (كل 30 ثانية فقط لتجنب الثقل)
    last_upd = LAST_DB_UPDATE.get(user_id, 0)
    if (current_time - last_upd) > 60:
        LAST_DB_UPDATE[user_id] = current_time
        asyncio.create_task(update_db_silent(user_id, lat_val, lon_val))

    # 3. تمرير الموقع في المحادثات النشطة (فقط إذا كان هناك شات قائم)
    if context.user_data.get('in_active_chat'):
        partner_id = get_chat_partner(user_id)
        if partner_id:
            try:
                await context.bot.copy_message(chat_id=partner_id, from_chat_id=user_id, message_id=msg.message_id)
                return 
            except: pass

    # 4. معالجة السائق (استخدام الـ Enum هنا)
    if user_role == UserRole.DRIVER and state != 'WAIT_LOCATION_FOR_ORDER':
        if update.message: # حذف الرسالة الجديدة فقط
            try: await update.message.delete()
            except: pass
        return 

    # 5. معالجة الراكب (عند طلب رحلة جديد)
    if state == 'WAIT_LOCATION_FOR_ORDER':
        # تجميد الحالة فوراً لمنع تكرار الطلب مع كل تحرك للراكب
        context.user_data['state'] = 'SEARCHING'
        
        processing_msg = await msg.reply_text("📡 جاري البحث عن كباتن قريباً منك...")
        sent_info = await broadcast_general_order(update, context)
        
        if sent_info:
            keyboard = []
            for info in sent_info[:10]:
                d_id = info['chat_id']
                driver_data = USER_CACHE.get(d_id) or {}
                driver_name = driver_data.get('name', 'كابتن متوفر')
                button = [InlineKeyboardButton(text=f"🚕 {driver_name}", callback_data="none")]
                keyboard.append(button)

            final_text = (
                f"✅ **تم تعميم طلبك بنجاح!**\n\n"
                f"وصل طلبك إلى **{len(sent_info)}** كابتن متواجدين حالياً.\n"
                f"⏳ يرجى الانتظار، سيتم التواصل معك هنا فور قبول أحدهم."
            )

            try:
                await context.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=processing_msg.message_id,
                    text=final_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
            except:
                await context.bot.send_message(chat_id=user_id, text=final_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            
            asyncio.create_task(start_order_timer(context, sent_info, user_id, processing_msg.message_id))
        else:
            await context.bot.send_message(chat_id=user_id, text="⚠️ نعتذر، لا يوجد كباتن متاحين حالياً.", reply_markup=get_main_kb(UserRole.RIDER, True))
            try: await processing_msg.delete()
            except: pass
        
        context.user_data['state'] = None


# ==================== دالة عرض الأحياء (محدثة) ====================

async def show_districts_by_city(update: Update, context: ContextTypes.DEFAULT_TYPE, city_name: str = "المدينة المنورة", is_edit=False):
    # تحديد المستخدم والكائن المستهدف
    if update.callback_query:
        user_id = update.callback_query.from_user.id
        target_msg = update.callback_query.message
    else:
        user_id = update.effective_user.id
        target_msg = update.message

    # 1. جلب البيانات (أولوية للكاش ثم قاعدة البيانات)
    if user_id not in USER_CACHE:
        # إذا لم يكن في الكاش، نجلبه من القاعدة
        conn = get_db_connection()
        current_districts = ""
        if conn:
            with conn.cursor() as cur:
                cur.execute("SELECT districts FROM users WHERE user_id = %s", (user_id,))
                res = cur.fetchone()
                if res and res[0]:
                    current_districts = res[0]
            conn.close()
        USER_CACHE[user_id] = {'districts': current_districts}
    
    # تحويل النص إلى قائمة
    user_info = USER_CACHE.get(user_id, {})
    current_str = user_info.get('districts', "") or ""
    current_list = [d.strip() for d in current_str.replace("،", ",").split(",") if d.strip()]

    # 2. بناء الأزرار (أيقونات ✅ و ❌)
    all_districts = CITIES_DISTRICTS.get(city_name, [])
    keyboard = []
    
    # صفين لكل حي (لترتيب جميل)
    for i in range(0, len(all_districts), 2):
        row = []
        for j in range(2):
            if i + j < len(all_districts):
                d_name = all_districts[i + j]
                status = "✅ " if d_name in current_list else "❌ "
                # نرسل toggle_dist_ لتمييزه عن الأزرار الأخرى
                row.append(InlineKeyboardButton(f"{status}{d_name}", callback_data=f"toggle_dist_{d_name}"))
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("💾 حفظ وإنهاء", callback_data="driver_home")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text_msg = (
        f"🏙 **إدارة أحياء {city_name}**\n\n"
        "اضغط على الحي لتغيير حالته:\n"
        "✅ = مفعل (تصلك طلبات)\n"
        "❌ = غير مفعل"
    )

    # 3. التنفيذ الآمن (يمنع خطأ NoneType)
    try:
        if is_edit and target_msg:
            # تعديل الرسالة الموجودة
            await target_msg.edit_text(text=text_msg, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            # إرسال رسالة جديدة
            if update.callback_query:
                 # إذا كان الاستدعاء من زر، نستخدم message لإرسال رد جديد
                 await update.callback_query.message.reply_text(text_msg, reply_markup=reply_markup, parse_mode="Markdown")
            else:
                 # إذا كان أمر كتابي
                 await context.bot.send_message(chat_id=update.effective_chat.id, text=text_msg, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception as e:
        # تجاهل خطأ "الرسالة لم تتغير"
        if "Message is not modified" not in str(e):
            print(f"Error showing districts: {e}")


# ==================== معالج الأزرار الشامل (محدث) ====================

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id

    # محاولة إغلاق مؤشر التحميل لتجنب التعليق
    try: await query.answer()
    except: pass

    if data == "districts_settings":
        # عرض أحياء المدينة المنورة للسائق فوراً
        from_city = "المدينة المنورة"
        await show_districts_by_city(update, context, from_city)
        return

    # ===============================================================
    # [A] قسم الكابتن: إعدادات المناطق (تفعيل/إلغاء)
    # ===============================================================

    if data == "help_delivery_orders":
        await query.answer()  # لإخفاء علامة التحميل من الزر فوراً
        
        help_text = (
            "🛍️ **طريقة طلب توصيل الطلبات:**\n\n"
            "للعثور على مندوب توصيل معتمد في حي معين، "
            "اكتب رسالة في الجروب تحتوي على كلمة **'طلبات'** واسم **'الحي'**.\n\n"
            "📝 *مثال:* \n"
            "\"محتاج توصيل طلبات في حي العزيزية\"\n\n"
            "👇 جرب الكتابة الآن في الجروب!"
        )
        
        try:
            # نرسل الرسالة في نفس المحادثة (الجروب) كرد على الرسالة الأصلية
            await query.message.reply_text(help_text, parse_mode="Markdown")
        except Exception as e:
            print(f"Error in delivery help: {e}")

    elif data.startswith("toggle_dist_"):
        # استخراج اسم الحي (الذي يأتي بعد toggle_dist_)
        dist_name = data.split("_", 2)[2]
        
        # 1. تحديث الكاش المحلي فوراً (Fast UI)
        if user_id not in USER_CACHE:
            USER_CACHE[user_id] = {'districts': ""} # تهيئة احتياطية
            
        user_info = USER_CACHE[user_id]
        current_str = user_info.get('districts', "") or ""
        current_list = [x.strip() for x in current_str.replace("،", ",").split(",") if x.strip()]
        
        # منطق التبديل
        if dist_name in current_list:
            current_list.remove(dist_name)
            alert_msg = f"❌ تم تعطيل {dist_name}"
        else:
            current_list.append(dist_name)
            alert_msg = f"✅ تم تفعيل {dist_name}"
        
        # حفظ القائمة الجديدة في الكاش
        new_districts_str = ",".join(current_list)
        USER_CACHE[user_id]['districts'] = new_districts_str

        # 2. تحديث الواجهة (إعادة رسم الأزرار فقط)
        # نستدعي دالة العرض بوضع التعديل True
        await show_districts_by_city(update, context, is_edit=True)
        
        # إشعار سريع يختفي (Toast)
        await query.answer(alert_msg)

        # 3. تحديث قاعدة البيانات في الخلفية (Background Task)
        # نستخدم thread لكي لا ينتظر البوت استجابة قاعدة البيانات
        import threading
        def save_db():
            conn = get_db_connection()
            if conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute("UPDATE users SET districts = %s WHERE user_id = %s", (new_districts_str, user_id))
                        conn.commit()
                except Exception as db_e:
                    print(f"DB Save Error: {db_e}")
                finally:
                    conn.close()
        
        threading.Thread(target=save_db).start()



    elif data.startswith("admin_u_info_"):
        target_id = data.split("_")[3]
        await admin_show_user_details(update, context, target_id)

    # 1. عرض القائمة أو التنقل بين الصفحات
    elif data.startswith("admin_view_users_"):
        page = int(data.split("_")[3])
        await admin_list_users(update, context, page)

    # 2. تأكيد الحذف (سؤال الأدمن قبل الحذف النهائي)
    elif data.startswith("admin_confirm_del_"):
        target_id = data.split("_")[3]
        keyboard = [
            [InlineKeyboardButton("✅ نعم، احذفه", callback_data=f"admin_final_del_{target_id}")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="admin_view_users_0")]
        ]
        await query.edit_message_text(
            f"⚠️ **تنبيه!**\nهل أنت متأكد من حذف العضو ذو المعرف `{target_id}` نهائياً؟",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    # 3. الحذف النهائي من قاعدة البيانات
    elif data.startswith("admin_final_del_"):
        target_id = data.split("_")[3]
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM users WHERE user_id = %s", (target_id,))
                conn.commit()
            conn.close()
            await query.answer("✅ تم حذف العضو بنجاح", show_alert=True)
            await admin_list_users(update, context, 0) # العودة للقائمة
        # 1. عند ضغط السائق على زر "اقتراح سعر آخر"
    if query.data.startswith("bid_req_"):
        rider_id = query.data.split("_")[2]
        # حفظ آيدي الراكب في بيانات السائق المؤقتة
        context.user_data['bidding_for_rider'] = rider_id
        context.user_data['state'] = 'DRIVER_SENDING_BID'
        
        await query.message.reply_text("📝 كم السعر الذي تقترحه لهذا المشوار؟\n(أرسل الرقم فقط)")
        await query.answer()
        return

    # 2. عند قبول الراكب لعرض سعر السائق (المزايدة)
    

        # رصد الضغط على زر المندوبين المعتمدين وإبلاغ الأدمن
    if data == "show_all_delivery":
        for admin_id in ADMIN_IDS:
            try:
                user_link = f"tg://user?id={user_id}"
                user_name = query.from_user.first_name
                
                admin_msg = (
                    "👀 **إشعار: استعلام عن المناديب**\n"
                    "--------------------------\n"
                    f"👤 **المستخدم:** [{user_name}]({user_link})\n"
                    f"🆔 **المعرف:** `{user_id}`\n"
                    f"🔎 قام بالاطلاع على قائمة المندوبين المعتمدين الآن.\n"
                    "--------------------------"
                )
                
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_msg,
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )
            except Exception as e:
                print(f"Error notifying admin: {e}")

        # هنا تضع الكود الخاص بك الذي يعرض قائمة المناديب للمستخدم
        # مثلاً: await show_delivery_list(update, context)

    # --- قسم لوحة تحكم الأدمن ---
    elif data == "admin_stats_view":
        await query.answer("جاري تحديث البيانات...")
        # يمكنك إضافة تفاصيل أكثر هنا (رصيد النظام، عدد الرحلات اليوم)
        await query.message.reply_text("الإحصائيات مفصلة ستظهر هنا قريباً...")

    elif data == "admin_broadcast_opt":
        await query.edit_message_text(
            "📢 **إرسال إذاعة:**\n\nأرسل الأمر التالي مع رسالتك:\n`/broadcast نص الرسالة هنا`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]])
        )

    elif data == "admin_manage_cash":
        await query.edit_message_text(
            "💰 **شحن رصيد مستخدم:**\n\nأرسل الأمر بالتنسيق التالي:\n`/cash ID AMOUNT`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]])
        )

    elif data == "admin_logs_help":
        await query.edit_message_text(
            "📜 **مراقبة السجلات:**\n\nاستخدم الأمر:\n`/logs ID1 ID2` لعرض المحادثة بين طرفين.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]])
        )
    
    elif data == "admin_back":
        # العودة للوحة الرئيسية (تحتاج لتحويلها لدالة تستقبل query)
        await query.message.delete()
        await admin_panel_view(update, context)

    elif data == "admin_search_id":
        context.user_data['state'] = 'ADMIN_WAIT_SEARCH_ID'
        await query.edit_message_text(
            "🔎 **البحث بالمعرف (ID):**\n\nمن فضلك أرسل معرف التليجرام (User ID) المطلوب البحث عنه:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="admin_back")]])
        )



    elif data == "admin_delete_user_start":
        context.user_data['state'] = 'ADMIN_WAIT_DELETE_ID'
        await query.edit_message_text(
            "⚠️ **حذف مستخدم نهائياً:**\n\nمن فضلك أرسل (ID التليجرام) الخاص بالعضو المراد حذفه.\n\n*ملاحظة: سيتم حذف كافة بياناته وسجلاته ولا يمكن التراجع.*",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="admin_back")]])
        )


    # --- [3] قسم التسجيل (الذي كان لديك) ---
    elif data in ["reg_rider", "reg_driver"]:
        user = query.from_user # التأكد من تعريف user
        role = "rider" if data == "reg_rider" else "driver"
        context.user_data['reg_role'] = role
        
        if role == "rider":
            context.user_data['state'] = 'WAIT_RIDER_PHONE'
            await query.edit_message_text(
                text=f"🎉 **أهلاً بك يا {user.first_name}**\n\nمن فضلك أرسل **رقم جوالك** الآن بكتابته في الشات (مثال: 050xxxxxxx):",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            context.user_data['state'] = 'WAIT_NAME'
            await query.edit_message_text(text="📝 يرجى كتابة **اسمك الثلاثي** الآن:", parse_mode=ParseMode.MARKDOWN)

    elif data == "driver_home" or data == "main_menu":
        user_id = update.effective_user.id
        
        # 1. جلب الأحياء المختارة من الكاش (أو قاعدة البيانات)
        user_info = USER_CACHE.get(user_id, {})
        districts_str = user_info.get('districts', "")
        
        # تنظيف النص وتحويله لقائمة للعرض بشكل جميل
        if districts_str and districts_str.strip():
            dist_list = [d.strip() for d in districts_str.split(",") if d.strip()]
            formatted_districts = "\n- ".join(dist_list)
            confirmation_text = (
                "✅ **تم حفظ مناطق عملك بنجاح!**\n\n"
                "الأحياء المسجلة حالياً:\n"
                f"- {formatted_districts}\n\n"
                "💡 ستصلك الآن طلبات الركاب من هذه المناطق فقط."
            )
        else:
            confirmation_text = (
                "⚠️ **تنبيه:** لم تقم باختيار أي أحياء عمل.\n"
                "لن تتمكن من استلام طلبات حتى تحدد مناطق عملك."
            )

        # 2. تحويل الرسالة (حذف الأزرار وتغيير النص)
        try:
            await query.message.edit_text(
                text=confirmation_text,
                parse_mode="Markdown",
                reply_markup=None # هذا السطر هو الذي يحذف الأزرار تماماً
            )
        except Exception as e:
            print(f"Error finishing selection: {e}")
            # في حال الفشل نرسل رسالة جديدة
            await context.bot.send_message(chat_id=user_id, text=confirmation_text, parse_mode="Markdown")


    elif data == "show_all_delivery":
        await query.answer() # إيقاف علامة التحميل
        
        await sync_all_users()
        # جلب الكباتن الذين لديهم كلمة "توصيل" في عمود الأحياء
        all_delivery_drivers = [
            d for d in CACHED_DRIVERS 
            if "توصيل" in str(d.get('districts', ''))
        ]
        
        if all_delivery_drivers:
            keyboard = []
            for d in all_delivery_drivers:
                # عرض اسم الكابتن مع رابط الطلب الخاص به
                keyboard.append([InlineKeyboardButton(f"📦 المندوب: {d['name']}", url=f"https://t.me/{context.bot.username}?start=order_{d['user_id']}")])
            
            await query.message.reply_text(
                "📋 **قائمة كباتن توصيل الطلبات المعتمدين:**\nإضغط على اسم المندوب للطلب منه مباشرة:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.message.reply_text("⚠️ لا يوجد كباتن توصيل طلبات مسجلين حالياً.")

        # ... (داخل دالة handle_callbacks) ...
    
    # معالجة أزرار المجموعات
    elif data.startswith("admin_msg_"):
        gid = data.split("_")[2]
        context.user_data['target_group'] = gid
        context.user_data['state'] = 'WAITING_GROUP_MSG'
        await query.message.reply_text(f"📝 **وضع المراسلة:**\nأرسل الآن الرسالة التي تريد نشرها في المجموعة `{gid}`:")
        await query.answer()
        return

    elif data.startswith("admin_leave_"):
        gid = data.split("_")[2]
        try:
            await context.bot.leave_chat(chat_id=gid)
            
            # حذف من القاعدة
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("DELETE FROM bot_groups WHERE group_id = %s", (gid,))
                conn.commit()
            
            await query.edit_message_text(f"✅ تم الخروج من المجموعة `{gid}` بنجاح.")
        except Exception as e:
            await query.answer(f"❌ خطأ: {e}", show_alert=True)
        return

    # ===============================================================
    # [B] قسم الراكب: البحث عن كابتن (النخبة)
    # ===============================================================

    # --- قسم الراكب: عرض الأحياء ---
        # 1. عند الضغط على زر "طلب رحلة بالاحياء"
    elif data == "order_by_district":
        # جلب قائمة الأحياء
        districts = CITIES_DISTRICTS.get("المدينة المنورة", [])
        if not districts:
            await query.answer("⚠️ قائمة الأحياء غير متوفرة حالياً.")
            return

        keyboard = []
        # بناء أزرار الأحياء (صفين في كل سطر)
        for i in range(0, len(districts), 2):
            row = []
            dist1 = districts[i]
            # نستخدم بادئة searchdist_ التي يعالجها البوت
            row.append(InlineKeyboardButton(dist1, callback_data=f"searchdist_{dist1}"))
            if i + 1 < len(districts):
                dist2 = districts[i+1]
                row.append(InlineKeyboardButton(dist2, callback_data=f"searchdist_{dist2}"))
            keyboard.append(row)

        keyboard.append([InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="main_menu")])
        
        await query.edit_message_text(
            "📍 **أحياء المدينة المنورة:**\nاختر الحي الذي تود البحث فيه عن كابتن:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # 2. عند اختيار حي محدد للبحث عن كابتن
    elif data.startswith("searchdist_"):
        # استخراج اسم الحي من الـ callback
        target_dist = data.replace("searchdist_", "")
        
        await sync_all_users() # تحديث قائمة الكباتن من القاعدة
        
        def clean(t): 
            return t.replace("ة", "ه").replace("أ", "ا").replace("إ", "ا").replace(" ", "").strip()
        
        target_clean = clean(target_dist)
        matched_drivers = []

        # البحث عن الكباتن الذين لديهم هذا الحي
        for d in CACHED_DRIVERS:
            if d.get('role') == 'driver' and d.get('districts'):
                # تنظيف وتحويل النص المخزن (الذي يحتوي فواصل) إلى قائمة
                d_dists = [clean(x) for x in d['districts'].replace("،", ",").split(",")]
                if target_clean in d_dists:
                    matched_drivers.append(d)

        if not matched_drivers:
            kb = [[InlineKeyboardButton("🌍 طلب GPS (بالموقع)", callback_data="order_general")],
                  [InlineKeyboardButton("🔙 اختيار حي آخر", callback_data="order_by_district")]]
            await query.edit_message_text(
                f"⚠️ نعتذر، لا يوجد كباتن نخبة متاحين حالياً في حي **{target_dist}**.",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        else:
            keyboard = []
            for d in matched_drivers[:8]:
                keyboard.append([InlineKeyboardButton(
                    f"🚖 {d['name']} ({d.get('car_info', 'سيارة')})", 
                    callback_data=f"book_{d['user_id']}_{target_dist}"
                )])
            keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="order_by_district")])
            
            await query.edit_message_text(
                f"✅ وجدنا {len(matched_drivers)} كابتن متاحين في {target_dist}:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return

    # ===============================================================
    # [C] عمليات الحجز والقبول (Logic)
    # ===============================================================
    
    # ===============================================================
    # 1. القائمة الرئيسية للبحث (أقرب كابتن vs بحث بالأحياء)
    # ===============================================================

    # --- خيار أ: أقرب كابتن (البحث بالموقع GPS) ---
    if data == "order_general":
        context.user_data['state'] = 'WAIT_GENERAL_DETAILS' 
        await query.edit_message_text(
            "🌍 **البحث عن أقرب كابتن (GPS):**\n\n"
            "📝الى اين وجهتك ؟؟",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # --- خيار ب: كابتن نخبة (بحث باختيار المدينة والحي) ---
    

    # ===============================================================
    # 2. التنقل داخل قائمة المدن والأحياء
    # ===============================================================

    # --- تم اختيار المدينة -> عرض الأحياء ---
    

    # --- تم اختيار الحي -> عرض الكباتن ---
    
    # ===============================================================
    # 3. بدء عملية حجز كابتن محدد (Book)
    # ===============================================================
        

    # --- منطق تبديل الأحياء ---
        # --- 1. معالجة الضغط على اسم الحي (تبديل الحالة) ---
    



    # ===============================================================
    # 4. قبول الكابتن للطلب (عام أو خاص)
    # ===============================================================
        # طباعة بيانات الزر في التيرمنال لمعرفة ماذا يصل بالضبط (للتشخيص)
    print(f"DEBUG: Button Clicked -> {data}") 

    # ---------------------------------------------------------
    # 1. معالجة قبول الكابتن للطلب (الخطوة الأولى)
    # ---------------------------------------------------------
    if data.startswith("accept_gen_") or data.startswith("accept_ride_"):
        try:
            parts = data.split("_")
            rider_id = int(parts[2])
            price = parts[3]
            driver_id = query.from_user.id

            # 1️⃣ منع التضارب (التحقق من قاعدة البيانات)
            conn = get_db_connection()
            if conn:
                try:
                    with conn.cursor() as cur:
                        # التحقق هل الطلب مقبول مسبقاً من سائق آخر
                        cur.execute("SELECT partner_id FROM active_chats WHERE user_id = %s", (rider_id,))
                        existing_chat = cur.fetchone()

                        if existing_chat:
                            # 🛑 تم قبول الطلب مسبقاً
                            await query.answer("⚠️ المشوار غير متاح", show_alert=False)
                            await context.bot.send_message(
                                chat_id=driver_id,
                                text="❌ **نعتذر منك..**\nهذا الطلب تم قبوله من قبل كابتن آخر منذ لحظات. حظاً موفقاً في الطلب القادم! 🚕",
                                parse_mode="Markdown"
                            )
                            try:
                                await query.message.delete()
                            except:
                                pass
                            return

                        # التحقق هل السائق نفسه مشغول في رحلة أخرى؟
                        cur.execute("SELECT partner_id FROM active_chats WHERE user_id = %s", (driver_id,))
                        if cur.fetchone():
                            await query.answer("⚠️ لا يمكنك قبول طلب جديد وأنت في رحلة نشطة حالياً!", show_alert=True)
                            return

                        # 2️⃣ حجز الطلب فوراً
                        start_chat_session(driver_id, rider_id)
                        conn.commit()
                finally:
                    conn.close()

            # 3️⃣ تحديث الذاكرة المحلية
            context.user_data.update({'chat_with': rider_id, 'order_status': 'ACCEPTED'})

            # 4️⃣ إعداد كيبورد الدردشة
            chat_kb = ReplyKeyboardMarkup([
                [KeyboardButton("📍 مشاركة موقعي الحالي", request_location=True)],
                [KeyboardButton("🏁 إنهاء المشوار والدردشة")] # تأكد من توحيد النص للإنهاء
            ], resize_keyboard=True)

            # 5️⃣ جلب الأسماء
            await sync_all_users()
            d_name = USER_CACHE.get(driver_id, {}).get('name', 'كابتن')
            r_name = USER_CACHE.get(rider_id, {}).get('name', 'عميل')

            # 6️⃣ إرسال الإشعارات للطرفين
            await query.edit_message_text(f"✅ تم قبول المشوار!\n💬 الدردشة مفتوحة مع: {r_name}")
            
            await context.bot.send_message(
                chat_id=driver_id,
                text="🚕 **بدأت الرحلة!**\nيمكنك التواصل مع الراكب الآن.",
                reply_markup=chat_kb,
                parse_mode="Markdown"
            )

            try:
                await context.bot.send_message(
                    chat_id=rider_id,
                    text=f"🎉 **أبشر! الكابتن {d_name} قبل طلبك.**\n💰 السعر: {price}\n\n💬 يمكنك مراسلته الآن:",
                    reply_markup=chat_kb,
                    parse_mode="Markdown"
                )
            except: pass

            # 7️⃣ إشعار الإدارة (الإرسال لجميع الإداريين)
            admin_msg = (
                "🚨 **رحلة نشطة حالياً**\n\n"
                f"🚕 **السائق:** {d_name}\n"
                f"👤 **الراكب:** {r_name}\n"
                f"💵 **السعر:** {price}\n\n"
                f"📱 [مراسلة السائق](tg://user?id={driver_id})\n"
                f"📱 [مراسلة الراكب](tg://user?id={rider_id})"
            )

            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id, 
                        text=admin_msg, 
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"⚠️ فشل إرسال إشعار الرحلة للآدمن {admin_id}: {e}")

        except Exception as e:
            print(f"Error in acceptance logic: {e}")
            await query.answer("⚠️ حدث خطأ فني.")
        return

    # ---------------------------------------------------------
    # 2. معالجة موافقة الراكب النهائية (فتح الدردشة)
    # ---------------------------------------------------------
    elif data.startswith("final_start_"):
        try:
            parts = data.split("_")
            driver_id = int(parts[2])
            price = float(parts[3])
            rider_id = user_id 

            if start_chat_session(driver_id, rider_id):
                # 1. إعداد لوحة مفاتيح الدردشة (داخل الـ if)
                kb_chat = ReplyKeyboardMarkup([
                    [KeyboardButton("📍 مشاركة موقعي", request_location=True)],
                    [KeyboardButton("🏁 إنهاء المشوار")]
                ], resize_keyboard=True)

                # 2. إرسال إشعار للأدمن (داخل الـ if)
                for admin_id in ADMIN_IDS:
                    try:
                        driver_link = f"tg://user?id={driver_id}"
                        rider_link = f"tg://user?id={rider_id}"
                        admin_text = (
                            "🔔 **إشعار: بدأت رحلة جديدة الآن!**\n\n"
                            f"💰 **السعر:** {price} ريال\n"
                            "--------------------------\n"
                            f"👤 **الراكب:** [رابط التواصل]({rider_link})\n"
                            f"🆔 ID: `{rider_id}`\n\n"
                            f"🚕 **الكابتن:** [رابط التواصل]({driver_link})\n"
                            f"🆔 ID: `{driver_id}`\n"
                            "--------------------------\n"
                            "📍 يمكن للأدمن التدخل في الدردشة."
                        )
                        await context.bot.send_message(
                            chat_id=admin_id,
                            text=admin_text,
                            parse_mode=ParseMode.MARKDOWN,
                            disable_web_page_preview=True
                        )
                    except Exception as e:
                        print(f"Admin Notify Error: {e}")

                # 3. تحديث الرسائل للأطراف (داخل الـ if)
                await query.edit_message_text(f"✅ تم بدء الرحلة بسعر {price} ريال.")
                
                await context.bot.send_message(
                    chat_id=rider_id, 
                    text="🟢 **الدردشة نشطة.** تواصل مع الكابتن الآن.", 
                    reply_markup=kb_chat,
                    parse_mode=ParseMode.MARKDOWN
                )
                
                try:
                    await context.bot.send_message(
                        chat_id=driver_id, 
                        text=f"🚀 **وافق الراكب!** السعر {price} ريال.\nتحدث معه الآن.", 
                        reply_markup=kb_chat,
                        parse_mode=ParseMode.MARKDOWN
                    )
                except:
                    pass
            else:
                await query.answer("خطأ: لم يتم إنشاء جلسة الدردشة.")
        except Exception as e:
            print(f"Error in final_start: {e}")
        return

    # ---------------------------------------------------------
    # 3. معالجة الرفض
    # ---------------------------------------------------------
    elif data.startswith("reject_ride_"):
        await query.edit_message_text("❌ تم رفض العرض.")
        # اختياري: إبلاغ السائق بالرفض
        driver_id = int(data.split("_")[2])
        try:
            await context.bot.send_message(chat_id=driver_id, text="⚠️ الراكب رفض العرض.")
        except: pass
        return

        # هذا الجزء يوضع داخل معالج الـ CallbackQuery (عند الضغط على زر الكابتن في القروب)
    elif data.startswith("book_"):
        parts = data.split("_")
        driver_id = parts[1]
        
        # استخراج اسم الحي إذا كان موجوداً في البيانات
        dist_name = parts[2] if len(parts) > 2 else "المحدد"

        # التحقق من نوع الشات (إذا كان في القروب نحوله للبوت)
        if update.effective_chat.type != "private":
            bot_username = context.bot.username
            
            # الرابط العميق الذي يمرر ID الكابتن لـ Start Command
            url = f"https://t.me/{bot_username}?start=order_{driver_id}"
            
            # الزر الذي ينقصك لإكمال الطلب
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🚀 إرسال تفاصيل المشوار والسعر", url=url)
            ]])
            
            await query.edit_message_text(
                f"📥 **لقد اخترت كابتن في حي {dist_name}**\n\n"
                "لإكمال الطلب وحماية خصوصيتك، اضغط على الزر بالأسفل ثم اضغط (ابدأ/Start) واكتب تفاصيل مشوارك.",
                reply_markup=kb,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            # إذا كان المستخدم يضغط من داخل البوت أصلاً (نادر الحدوث في هذا السياق)
            context.user_data.update({
                'driver_to_order': driver_id,
                'state': 'WAIT_TRIP_DETAILS'
            })
            await query.edit_message_text("📝 **اكتب تفاصيل مشوارك الآن:**")
        
        return

    elif query.data.startswith("accept_bid_"):
        _, _, driver_id, final_price = query.data.split("_")
        rider = update.effective_user
        rider_id = rider.id
        driver_id = int(driver_id)
        
        # فتح الجلسة مباشرة دون التحقق من عمود 'balance' الظاهر في قاعدة بياناتك
        # تم إلغاء أي شروط تتعلق بخصم العمولات لضمان عدم حظر السائقين
        if start_chat_session(rider_id, driver_id):
            # 1. إشعار الراكب وتفعيل لوحة مفاتيح الدردشة
            await query.edit_message_text(
                f"✅ تم قبول العرض ({final_price} ريال).\nتم فتح دردشة وسيطة مع الكابتن الآن.",
                reply_markup=None
            )
            
            finish_kb = ReplyKeyboardMarkup([["🏁 إنهاء المشوار والدردشة"]], resize_keyboard=True)

            await context.bot.send_message(
                chat_id=rider_id,
                text="💬 **الدردشة مفعلة:** اكتب أي رسالة هنا وستصل للكابتن مباشرة.",
                reply_markup=finish_kb,
                parse_mode=ParseMode.MARKDOWN
            )

            # 2. إشعار السائق (يتم التجاهل التام لرصيده الصفري)
            await context.bot.send_message(
                chat_id=driver_id,
                text=f"🚀 **مبروك!** وافق الراكب على عرضك ({final_price} ريال).\nتم فتح دردشة وسيطة معه الآن، أرسل رسائلك هنا مباشرة.",
                reply_markup=finish_kb,
                parse_mode=ParseMode.MARKDOWN
            )

            # 3. إرسال إشعار للأدمن بروابط التواصل المباشرة
            try:
                driver_info = await context.bot.get_chat(driver_id)
                driver_name = driver_info.full_name
                
                rider_link = f"tg://user?id={rider_id}"
                driver_link = f"tg://user?id={driver_id}"
                
                admin_msg = (
                    f"🔔 **إشعار مشوار جديد (بدون عمولة)**\n\n"
                    f"💰 **السعر:** {final_price} ريال\n"
                    f"👤 **الراكب:** [{rider.full_name}]({rider_link})\n"
                    f"🚕 **السائق:** [{driver_name}]({driver_link})\n\n"
                    f"⚙️ **الحالة:** تم فتح دردشة وسيطة (رصيد السائق لم يتأثر)."
                )

                for admin_id in ADMIN_IDS:
                    try:
                        await context.bot.send_message(
                            chat_id=admin_id,
                            text=admin_msg,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    except:
                        continue
            except Exception as e:
                print(f"Error in admin notification: {e}")

        else:
            # في حال فشل الاتصال بجدول active_chats في Supabase
            await query.answer("⚠️ فشل فتح الدردشة، تأكد من إعدادات قاعدة البيانات.")
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


    # داخل handle_callbacks
    if data.startswith("admin_block_"):
        target_id = int(data.split("_")[2])
        # هنا تضع منطق الحظر في قاعدة البيانات (تحديث is_blocked = True)
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET is_blocked = TRUE WHERE user_id = %s", (target_id,))
            conn.commit()
        conn.close()
        await query.answer("✅ تم حظر المستخدم بنجاح")
        await query.edit_message_caption(caption=query.message.caption + "\n\n🚫 (تم حظر هذا العضو)")

    elif data.startswith("admin_quickcash_"):
        target_id = data.split("_")[2]
        await query.message.reply_text(f"لشحن رصيد هذا العضو، استخدم الأمر التالي:\n`/cash {target_id} 50`")
        await query.answer()


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
        try:
            markup = get_main_kb('driver', is_verified) # نرسل الكيبورد بناءً على الحالة الجديدة
            await context.bot.send_message(chat_id=target_uid, text=msg, reply_markup=markup)
        except: pass

        # 🔥 تحديث الكاش فوراً وإجباري
        await sync_all_users(force=True) 
        return



# ---------------------------------------------------------
# نظام إدارة المجموعات (Admin Group Management)
# ---------------------------------------------------------

# 1. دالة تتبع دخول وخروج البوت من المجموعات تلقائياً
async def on_status_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if not result: return
    
    chat = result.chat
    
    # نتحقق أن التحديث يخص مجموعة وليس محادثة خاصة
    if chat.type in ['group', 'supergroup']:
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    new_status = result.new_chat_member.status
                    # التعديل داخل دالة on_status_change
                    if new_status in ['member', 'administrator']:
                        cur.execute("""
                            INSERT INTO bot_groups (group_id, title) 
                            VALUES (%s, %s) 
                            ON CONFLICT (group_id) 
                            DO UPDATE SET title = EXCLUDED.title
                        """, (chat.id, chat.title))

                    
                    # إذا غادر البوت أو تم طرده
                    elif new_status in ['left', 'kicked']:
                        cur.execute("DELETE FROM bot_groups WHERE group_id = %s", (chat.id,))
                        print(f"❌ Left group: {chat.title}")
                        
                    conn.commit()
            except Exception as e:
                print(f"Error updating group status: {e}")
            finally:
                conn.close()


# 2. دالة عرض المجموعات للأدمن (يتم استدعاؤها بـ /groups)
async def list_groups_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS: return

    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT group_id, title FROM bot_groups")
                groups = cur.fetchall()
                
                if not groups:
                    await update.message.reply_text("❌ البوت غير موجود في أي مجموعات حالياً.")
                    return

                text = "📋 **لوحة التحكم بالمجموعات:**\n\n"
                
                # سنقوم بعرض المجموعات، ونظراً لقيود طول الرسالة، سنرسل كل مجموعة مع أزرارها
                await update.message.reply_text(f"🔢 عدد المجموعات النشطة: {len(groups)}")
                
                for gid, title in groups:
                    group_text = f"🔹 **المجموعة:** {title}\n🆔 ID: `{gid}`"
                    
                    keyboard = [
                        [
                            InlineKeyboardButton("✉️ مراسلة", callback_data=f"admin_msg_{gid}"),
                            InlineKeyboardButton("🚪 مغادرة", callback_data=f"admin_leave_{gid}")
                        ]
                    ]
                    
                    await update.message.reply_text(
                        group_text, 
                        reply_markup=InlineKeyboardMarkup(keyboard), 
                        parse_mode="Markdown"
                    )
        finally:
            conn.close()


# 3. معالجة الرسائل الموجهة للمجموعات (توضع داخل دالة استقبال النصوص العامة)
# ملاحظة: يجب دمج منطق هذا الجزء داخل دالة handle_message الموجودة لديك
async def handle_admin_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = context.user_data.get('state')
    
    if user_id in ADMIN_IDS and state == 'WAITING_GROUP_MSG':
        target_gid = context.user_data.get('target_group')
        text_to_send = update.message.text
        
        if not target_gid:
            await update.message.reply_text("❌ خطأ: لم يتم تحديد مجموعة.")
            context.user_data['state'] = None
            return

        try:
            # إرسال الرسالة للمجموعة
            await context.bot.send_message(chat_id=target_gid, text=text_to_send)
            await update.message.reply_text(f"✅ تم الإرسال للمجموعة بنجاح.")
        except Exception as e:
            await update.message.reply_text(f"⚠️ فشل الإرسال (قد يكون البوت طُرد): {e}")
        
        # إعادة تعيين الحالة
        context.user_data['state'] = None
        context.user_data['target_group'] = None
        return True # لإخبار النظام أن الرسالة تمت معالجتها
    
    return False

async def track_groups_from_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    # التحقق أن الرسالة من مجموعة وليست خاص
    if chat and chat.type in ['group', 'supergroup']:
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO bot_groups (group_id, title) 
                        VALUES (%s, %s) 
                        ON CONFLICT (group_id) 
                        DO UPDATE SET title = EXCLUDED.title
                    """, (chat.id, chat.title))
                    conn.commit()
            except: pass
            finally: conn.close()


async def districts_settings_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # بدلاً من بناء قائمة المدن، ننتقل مباشرة لعرض أحياء المدينة المنورة
    await show_districts_by_city(update, context, "المدينة المنورة")


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

        # 🔥 الخطوة الذهبية: تحديث الكاش إجبارياً فوراً
        await sync_all_users(force=True)

        await update.message.reply_text(f"✅ تم إضافة {amount} ريال للعضو {uid}.")
        
        # جلب الرصيد الجديد من الكاش لإرساله في الرسالة
        new_balance = USER_CACHE.get(uid, {}).get('balance', 0)
        
        await context.bot.send_message(
            chat_id=uid, 
            text=f"💰 **تم شحن رصيدك بنجاح!**\n\nالمبلغ المضاف: {amount} ريال\nرصيدك الحالي الآن: {new_balance} ريال"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: تأكد من الصيغة /cash [ID] [Amount]\n{e}")

async def promote_to_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # 1. التحقق من أن المرسل هو الأدمن
    if user.id not in ADMIN_IDS:
        return

    target_user_id = None
    
    # 2. جلب ID الشخص المستهدف (سواء بالرد على رسالته أو بكتابة الـ ID)
    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
    elif context.args:
        target_user_id = context.args[0]

    if not target_user_id:
        await update.message.reply_text("❌ يرجى الرد على رسالة العضو بكلمة 'مندوب' أو كتابة: `/make_delivery ID`", parse_mode="Markdown")
        return

    # 3. تحديث قاعدة البيانات (إضافة وسم 'توصيل')
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                # جلب الأحياء الحالية أولاً لعدم مسحها
                cur.execute("SELECT districts FROM users WHERE user_id = %s", (str(target_user_id),))
                res = cur.fetchone()
                
                current_dists = res[0] if res and res[0] else ""
                
                if "توصيل" in current_dists:
                    await update.message.reply_text("✅ العضو مسجل بالفعل كمندوب توصيل.")
                    return

                new_dists = f"توصيل, {current_dists}".strip(", ")
                
                cur.execute("UPDATE users SET districts = %s WHERE user_id = %s", (new_dists, str(target_user_id)))
                conn.commit()
                
                # تحديث الكاش فوراً
                await sync_all_users()
                
                await update.message.reply_text(f"🚀 تم ترقية العضو `{target_user_id}` إلى **مندوب توصيل معتمد** بنجاح.", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ في القاعدة: {e}")
        finally:
            conn.close()




# ==============================================================================
# 1. دالة الإرسال التلقائي (تعمل كل 30 دقيقة)
# ==============================================================================
async def send_periodic_advertisement(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    
    welcome_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📍 اطلب أقرب كابتن بالمدينة (GPS) 📍", url=f"https://t.me/{context.bot.username}?start=order_general")],
        [InlineKeyboardButton("🚕 تسجيل كابتن جديد", url=f"https://t.me/{context.bot.username}?start=driver_reg")]
    ])
    
    try:
        await context.bot.send_message(
            chat_id=job.chat_id,
            text=(
                "📢 **تذكير تلقائي:**\n\n"
                "✨ **خدمة توصيل المدينة المنورة** ✨\n"
                "هل تحتاج إلى مشوار سريع أو تاكسي؟\n"
                "نحن هنا لخدمتك على مدار الساعة.\n\n"
                "👇 **اضغط بالأسفل لطلب كابتن فوراً** 👇"
            ),
            reply_markup=welcome_kb,
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"⚠️ فشل الإرسال التلقائي للمجموعة {job.chat_id}: {e}")

# ==============================================================================
# 2. الدالة الرئيسية: مراقب الجروب الذكي (Scanner)
# ==============================================================================
async def group_order_scanner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    chat_id = update.effective_chat.id
    text = update.message.text
    
    def clean_text(t):
        return t.lower().replace("ة", "ه").replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").strip()

    msg_clean = clean_text(text)
    # تقطيع الرسالة إلى كلمات للتأكد من أنها كلمة واحدة فقط
    words = msg_clean.split()

    # ------------------------------------------------------------------
    # 🕒 تشغيل المؤقت التلقائي (يبقى كما هو)
    # ------------------------------------------------------------------
    if context.job_queue:
        current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
        if not current_jobs:
            context.job_queue.run_repeating(
                send_periodic_advertisement, 
                interval=1800, 
                first=10, 
                chat_id=chat_id, 
                name=str(chat_id)
            )

    # ------------------------------------------------------------------
    # 1. حذف السبام فوراً (يبقى كما هو)
    # ------------------------------------------------------------------
    REAL_SPAM_KEYWORDS = [
        "استثمار", "ربح سريع", "تداول", "عملات رقمية", "شغل من البيت",
        "سيكليف", "سيكليفات", "سكليف", "سكليفات", "عذر طبي", "اعذار طبيه"
    ]
    if any(k in msg_clean for k in REAL_SPAM_KEYWORDS):
        try: await update.message.delete()
        except: pass
        return

    # ------------------------------------------------------------------
    # 2. إشعار الآدمن بالطلبات الشهرية (يبقى كما هو)
    # ------------------------------------------------------------------
    MONTHLY_KEYWORDS = ["شهري", "عقد", "مشوار شهري", "نقل طالبات", "نقل موظفات"]
    if any(k in msg_clean for k in MONTHLY_KEYWORDS):
        admin_text = (
            "🚨 **طلب تعاقد شهري (المدينة المنورة):**\n\n"
            f"👤 العميل: {user.first_name}\n"
            f"📝 النص: {text}\n"
            f"🔗 [تواصل مع العميل](tg://user?id={user.id})"
        )
        for admin_id in ADMIN_IDS:
            try: await context.bot.send_message(chat_id=admin_id, text=admin_text, parse_mode="Markdown")
            except: pass
        return

    # ------------------------------------------------------------------
    # 🚀 منطق الرد الجديد: الكلمات الثلاث فقط ومفردة
    # ------------------------------------------------------------------
    
    # الكلمات المسموح بها
    TARGET_WORDS = ["مشوار", "تكسي", "تاكسي"]
    
    should_reply = False

    # الشرط: أن تتكون الرسالة من كلمة واحدة فقط، وأن تكون ضمن القائمة
    if len(words) == 1 and words[0] in TARGET_WORDS:
        should_reply = True

    # ميزة إضافية: كلمة "رن" للمسؤول للاختبار
    if msg_clean == "رن" and user.id in ADMIN_IDS:
        should_reply = True

    # ------------------------------------------------------------------
    # ✅ إرسال الرد
    # ------------------------------------------------------------------
    if should_reply:
        welcome_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📍 اطلب أقرب كابتن بالمدينة (GPS) 📍", url=f"https://t.me/{context.bot.username}?start=order_general")],
            [InlineKeyboardButton("🚕 تسجيل كابتن جديد", url=f"https://t.me/{context.bot.username}?start=driver_reg")]
        ])
        
        await update.message.reply_text(
            f"✨ **أبشر يا {user.first_name}، طلبك في المدينة المنورة مجاب!** ✨\n\n"
            "للحصول على كابتن بسرعة وبدقة:\n"
            "✅ **اضغط على زر (طلب عبر GPS) بالأسفل** وسيتواصل معك الكباتن فوراً.", 
            reply_markup=welcome_kb,
            parse_mode="Markdown"
        )

async def handle_chat_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. حماية: نتجاهل أي تحديث ليس رسالة (تجاهل ضغطات الأزرار CallbackQueries)
    if not update.message: 
        return

    user_id = update.effective_user.id
    partner_id = get_chat_partner(user_id)

    # 2. إذا لم يكن هناك شريك، نخرج فوراً لكي يكمل البوت طريقه للأدمن أو الأوامر
    if not partner_id: 
        return

    # 3. معالجة زر الإنهاء (يجب أن يكون النص مطابقت تماماً لما في الكيبورد)
    if update.message.text == "🏁 إنهاء المشوار والدردشة":
        # تنظيف قاعدة البيانات (تأكد أن دالتك تمسح السجل للطرفين)
        await end_chat_session(user_id) 
        
        await update.message.reply_text("✅ تم إنهاء المشوار والدردشة.", reply_markup=ReplyKeyboardRemove())
        try:
            await context.bot.send_message(
                chat_id=partner_id, 
                text="🏁 قام الطرف الآخر بإنهاء المشوار والدردشة.", 
                reply_markup=ReplyKeyboardRemove()
            )
        except: pass
        
        raise ApplicationHandlerStop

    # 4. منع إرسال الأوامر (مثل /start) للطرف الآخر
    if update.message.text and update.message.text.startswith('/'):
        return

    # 5. نقل الرسالة (موقع، نص، صور) باستخدام copy_message
    # هذه الطريقة هي التي تحل مشكلة ظهور سجلات غريبة في التيرمنال
    try:
        await context.bot.copy_message(
            chat_id=partner_id,
            from_chat_id=user_id,
            message_id=update.message.message_id
        )
    except Exception as e:
        print(f"Relay Error: {e}")
        # لا نرسل تنبيه للمستخدم هنا لكي لا ينزعج عند كل رسالة
    
    # 6. إيقاف المعالجة لضمان عدم وصول الرسالة لمعالج الأدمن
    raise ApplicationHandlerStop

async def broadcast_to_riders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # 1. التحقق من أن المرسل هو الأدمن
    if user_id not in ADMIN_IDS:
        return

    # 2. تحديد مصدر الرسالة (سواء كانت نصاً مكتوباً مع الأمر أو رداً على صورة/ملف)
    target_msg = None
    if update.message.reply_to_message:
        target_msg = update.message.reply_to_message
    elif context.args:
        broadcast_text = " ".join(context.args)
    else:
        await update.message.reply_text(
            "💡 **طريقة الاستخدام:**\n"
            "• لإرسال نص: اكتب `/send_riders` متبوعاً بنص الرسالة.\n"
            "• لإرسال صورة/فيديو: قم بالرد (Reply) على الصورة واكتب `/send_riders`.",
            parse_mode="Markdown"
        )
        return

    # 3. جلب قائمة الركاب فقط من الكاش
    # نفترض أن role == 'rider'
    riders = [u_id for u_id, data in USER_CACHE.items() if data.get('role') == 'rider']
    
    if not riders:
        await update.message.reply_text("❌ لم يتم العثور على ركاب مسجلين في القاعدة.")
        return

    await update.message.reply_text(f"⏳ جاري الإرسال إلى {len(riders)} راكب... يرجى الانتظار.")

    success = 0
    fail = 0

    for r_id in riders:
        try:
            if target_msg:
                # إذا كان رداً على رسالة (صورة، ملف، فيديو، نص)
                await context.bot.copy_message(
                    chat_id=r_id,
                    from_chat_id=update.message.chat_id,
                    message_id=target_msg.message_id
                )
            else:
                # إذا كان نصاً عادياً
                await context.bot.send_message(
                    chat_id=r_id,
                    text=f"📢 **إعلان للمشتركين:**\n\n{broadcast_text}",
                    parse_mode="Markdown"
                )
            
            success += 1
            # تأخير بسيط (0.05 ثانية) لتجنب الـ Flood
            await asyncio.sleep(0.05)
        except Exception:
            fail += 1

    await update.message.reply_text(
        f"✅ **اكتمل الإرسال للركاب!**\n\n"
        f"🟢 تم بنجاح: {success}\n"
        f"🔴 فشل (بوت محظور): {fail}"
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
    
    # النص يجب أن يكون داخل علامات تنصيص محكمة
    admin_text = (
        "📝 **أرسل رسالتك أو شكواك الآن في رسالة واحدة:**\n\n"
        "أو يمكنك التحدث مباشرة عبر الرابط التالي:\n"
        "👤 @x3FreTx"
    )
    
    await update.message.reply_text(
        text=admin_text,
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("❌ إلغاء المراسلة")]], 
            resize_keyboard=True
        ),
        parse_mode="Markdown" # لتفعيل التنسيق العريض (Bold)
    )




async def broadcast_to_drivers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # 1. التحقق من صلاحية الأدمن
    if user_id not in ADMIN_IDS:
        return

    # 2. التأكد من وجود نص للرسالة
    if not context.args:
        await update.message.reply_text(
            "⚠️ **خطأ:** يرجى كتابة الرسالة بعد الأمر.\n"
            "مثال: `/send_drivers السلام عليكم يا كباتن، يرجى تحديث اللوحات`",
            parse_mode="Markdown"
        )
        return

    broadcast_msg = " ".join(context.args)
    
    # 3. جلب السائقين فقط من الكاش أو قاعدة البيانات
    # نفترض أن USER_CACHE يحتوي على بيانات المستخدمين مع 'role'
    drivers = [u_id for u_id, data in USER_CACHE.items() if data.get('role') == 'driver']
    
    if not drivers:
        await update.message.reply_text("❌ لم يتم العثور على سائقين مسجلين في القاعدة.")
        return

    await update.message.reply_text(f"⏳ جاري إرسال الرسالة إلى {len(drivers)} كابتن... يرجى الانتظار.")

    success = 0
    fail = 0

    for d_id in drivers:
        try:
            # إرسال الرسالة بتنسيق رسمي
            await context.bot.send_message(
                chat_id=d_id,
                text=f"📢 **إشعار إداري للكباتن فقط:**\n\n{broadcast_msg}",
                parse_mode="Markdown"
            )
            success += 1
            # تأخير بسيط جداً لتجنب حظر تليجرام عند الإرسال الجماعي
            await asyncio.sleep(0.05) 
        except Exception:
            fail += 1

    await update.message.reply_text(
        f"✅ **اكتملت عملية الإرسال!**\n\n"
        f"🟢 تم بنجاح: {success}\n"
        f"🔴 فشل (بوت محظور): {fail}"
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
    # 1. أهم حماية: التأكد أن التحديث هو رسالة حقيقية وليس "حدث زر"
    if not update.message: 
        return

    user_id = update.effective_user.id
    partner_id = get_chat_partner(user_id)
    
    # 2. إذا لم تكن هناك رحلة نشطة، اترك الرسالة تمر للعمليات الأخرى (مثل الأدمن)
    if not partner_id:
        return 

    text = update.message.text

    # 3. استثناء الأوامر وأزرار التحكم من النقل
    # تأكد أن النص هنا يطابق تماماً النص الموجود في الكيبورد الخاص بك
    if text and (text.startswith('/') or text == "❌ إنهاء المحادثة" or text == "🏁 إنهاء المشوار والدردشة"):
        return 

    # 4. تحديد محتوى السجل (Logs) لقاعدة البيانات
    msg_type = "text"
    msg_content = text
    
    if update.message.location:
        msg_type = "location"
        msg_content = f"📍 موقع: {update.message.location.latitude}, {update.message.location.longitude}"
    elif update.message.photo:
        msg_type = "photo"
        msg_content = "🖼️ [صورة]"
    elif update.message.voice:
        msg_type = "voice"
        msg_content = "🎤 [رسالة صوتية]"
    elif not text:
        msg_type = "other"
        msg_content = "📎 [وسائط]"

    # 5. الحفظ في قاعدة البيانات (السجلات)
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
            print(f"❌ SQL Log Error: {e}")
        finally:
            conn.close()

    # 6. نقل الرسالة للطرف الآخر (Relay)
    # استخدام copy_message هو الأصح لأنه ينقل الخريطة كخريطة والصورة كصورة
    try:
        await context.bot.copy_message(
            chat_id=partner_id,
            from_chat_id=user_id,
            message_id=update.message.message_id
        )
        # إرسال الكيبورد للتأكد من بقائه أمام المستخدم (اختياري)
    except Exception as e:
        print(f"❌ Relay Failure: {e}")

    # 7. 🔥 الأهم: منع الرسالة من الوصول لأي معالج آخر (مثل معالج الأدمن)
    raise ApplicationHandlerStop

async def admin_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    msg_text = update.message.text or "[ملف/صورة]"

    # --- (أ) إذا كان المرسل هو الأدمن (يريد الرد على عضو) ---
    if chat_id in ADMIN_IDS and update.message.reply_to_message:
        original_msg = update.message.reply_to_message.text or update.message.reply_to_message.caption
        if not original_msg: return

        try:
            # استخراج ID العضو من نص الرسالة الأصلية
            target_user_id = int(re.search(r"ID:\s*`?(\d+)`?", original_msg).group(1))
            
            # 1. إرسال الرد للعضو
            await context.bot.copy_message(
                chat_id=target_user_id,
                from_chat_id=chat_id,
                message_id=update.message.message_id
            )
            
            # 2. حفظ الرد في السجلات (من الأدمن للعضو)
            save_chat_log(chat_id, target_user_id, msg_text, "admin_reply")

            await update.message.reply_text(f"✅ تم إرسال الرد وحفظه في السجل.")
            
        except AttributeError:
             await update.message.reply_text("⚠️ انتظر قليلا .... ")
        except Exception as e:
            await update.message.reply_text(f"❌ حدث خطأ: {e}")
        return

    # --- (ب) إذا وصلت رسالة هنا ولم تكن رداً (نعتبرها رسالة مجهولة من الأدمن نفسه) ---
    # يمكن تجاهلها أو معالجتها كأي رسالة أخرى
    pass


async def group_districts_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    districts = CITIES_DISTRICTS.get("المدينة المنورة", [])
    if not districts: return

    keyboard = []
    # توزيع الأحياء في صفوف (3 أحياء في كل صف لتوفير المساحة في القروب)
    for i in range(0, len(districts), 3):
        row = [InlineKeyboardButton(districts[i], url=f"https://t.me/{context.bot.username}?start=sd_{i}")]
        if i + 1 < len(districts):
            row.append(InlineKeyboardButton(districts[i+1], url=f"https://t.me/{context.bot.username}?start=sd_{i+1}"))
        if i + 2 < len(districts):
            row.append(InlineKeyboardButton(districts[i+2], url=f"https://t.me/{context.bot.username}?start=sd_{i+2}"))
        keyboard.append(row)

    await update.message.reply_text(
        "📍 **أحياء المدينة المنورة المتاحة:**\nإضغط على الحي لعرض الكباتن المتوفرين والطلب مباشرة عبر الخاص 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    

    
async def admin_list_users(update, context, page=0):
    query = update.callback_query
    limit = 10
    offset = page * limit

    conn = get_db_connection()
    users = []
    total_users = 0
    if conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            total_users = cur.fetchone()['count']
            cur.execute("SELECT * FROM users ORDER BY user_id DESC LIMIT %s OFFSET %s", (limit, offset))
            users = cur.fetchall()
        conn.close()

    if not users:
        await query.answer("لا يوجد أعضاء حالياً.")
        return

    text = f"👥 **قائمة الأعضاء - صفحة {page + 1}**\nاضغط على الاسم لعرض التفاصيل:"
    keyboard = []

    # عرض الأسماء فقط في أزرار
    for u in users:
        role_icon = "🚕" if u.get('role') == 'driver' else "👤"
        name = u.get('name') or "بدون اسم"
        # عند الضغط يرسل الـ ID لعرض البيانات
        keyboard.append([InlineKeyboardButton(f"{role_icon} {name}", callback_data=f"admin_u_info_{u['user_id']}")])

    # أزرار التنقل
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"admin_view_users_{page-1}"))
    if offset + limit < total_users:
        nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"admin_view_users_{page+1}"))
    if nav: keyboard.append(nav)
    
    keyboard.append([InlineKeyboardButton("🔙 العودة للوحة الإدارة", callback_data="admin_back")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


# 3. أمر إرسال صورة ونص للسائقين (للمسؤولين فقط)
# ==============================================================================
async def admin_pic_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # 1. التحقق من أن المستخدم آدمن
    if user_id not in ADMIN_IDS:
        return

    # 2. التحقق مما إذا كان المستخدم قام بعمل ريبلي (Reply)
    if not update.message.reply_to_message:
        await update.message.reply_text("💡 **طريقة الاستخدام:**\nقم بالرد (Reply) على الصورة أو الرسالة التي تريد تعميمها واكتب `/picsend`.")
        return

    replied_msg = update.message.reply_to_message
    
    # 3. تحديد نوع المحتوى المردود عليه (صورة أو نص)
    photo_file_id = replied_msg.photo[-1].file_id if replied_msg.photo else None
    # النص المردود عليه (سواء كان شرح صورة أو رسالة نصية)
    final_text = replied_msg.caption if replied_msg.photo else replied_msg.text

    # 4. جلب معرفات السائقين من قاعدة البيانات
    drivers_to_send = []
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM users WHERE role = %s", (UserRole.DRIVER.value,))
                drivers_to_send = [row[0] for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Error fetching drivers: {e}")
        finally:
            conn.close()

    if not drivers_to_send:
        await update.message.reply_text("⚠️ لا يوجد سائقين مسجلين.")
        return

    status_msg = await update.message.reply_text(f"⏳ جاري تعميم الرسالة إلى {len(drivers_to_send)} كابتن...")

    success = 0
    failed = 0

    # 5. حلقة الإرسال
    for d_id in drivers_to_send:
        try:
            if photo_file_id:
                await context.bot.send_photo(chat_id=d_id, photo=photo_file_id, caption=final_text, parse_mode="Markdown")
            else:
                await context.bot.send_message(chat_id=d_id, text=final_text, parse_mode="Markdown")
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ **اكتمل الإرسال الجماعي بنظام الرد**\n\n"
        f"🟢 تم بنجاح: {success}\n"
        f"🔴 فشل: {failed}"
    )



# ------------------------------------------------------------------
# ⚠️ لا تنسى إضافة المعالج (Handler) داخل دالة main:
# 
# ------------------------------------------------------------------

async def admin_show_user_details(update, context, target_id):
    query = update.callback_query
    conn = get_db_connection()
    user_data = None
    if conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (target_id,))
            user_data = cur.fetchone()
        conn.close()

    if not user_data:
        await query.answer("❌ لم يتم العثور على بيانات العضو.")
        return

    res_txt = (
        f"👤 **تفاصيل العضو**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📝 **الاسم:** {user_data['name']}\n"
        f"🆔 **المعرف:** `{user_data['user_id']}`\n"
        f"📱 **الجوال:** `{user_data['phone']}`\n"
        f"🛠 **الرتبة:** {'كابتن 🚕' if user_data['role'] == 'driver' else 'عميل 👤'}\n"
        f"💰 **الرصيد:** {user_data['balance']} ريال\n"
        f"🚫 **الحالة:** {'❌ محظور' if user_data.get('is_blocked') else '✅ نشط'}\n"
    )

    kb = [
        [InlineKeyboardButton("💰 شحن رصيد", callback_data=f"admin_quickcash_{target_id}"),
         InlineKeyboardButton("🚫 حظر/إلغاء", callback_data=f"admin_toggle_block_{target_id}")],
        [InlineKeyboardButton("🗑️ حذف العضو نهائياً", callback_data=f"admin_confirm_del_{target_id}")],
        [InlineKeyboardButton("🔙 العودة للقائمة", callback_data="admin_view_users_0")]
    ]

    await query.edit_message_text(res_txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


# ==================== 🌐 5. خادم Flask (للبقاء نشطاً) ====================

# ==================== 🏁 6. التشغيل الرئيسي ====================
def main():
    # 1. تهيئة السيرفر وقاعدة البيانات
    threading.Thread(target=run_flask, daemon=True).start()
    init_db()

    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # ---------------------------------------------------------
    # المجموعة 0: الأوامر والعمليات الفورية (أولوية مطلقة)
    # ---------------------------------------------------------
    application.add_handler(CommandHandler("start", start_command), group=0)
    application.add_handler(CommandHandler("cash", admin_cash), group=0)
    application.add_handler(CommandHandler("sub", admin_add_days), group=0)
    application.add_handler(CommandHandler("broadcast", admin_broadcast), group=0)
    application.add_handler(CommandHandler("logs", admin_get_logs), group=0)
    application.add_handler(CommandHandler("send", admin_send_to_user), group=0) # أضف هذا السطر
    
    application.add_handler(CommandHandler("admin", admin_panel_view), group=0)
# أو ككلمة نصية
    application.add_handler(MessageHandler(filters.Regex("^لوحة التحكم$") & filters.User(ADMIN_IDS), admin_panel_view), group=0)
    application.add_handler(CommandHandler("send_drivers", broadcast_to_drivers), group=0)
    application.add_handler(CommandHandler("send_riders", broadcast_to_riders), group=0)
    
# أضف هذا السطر في دالة main
    application.add_handler(CommandHandler("picsend", admin_pic_send))





    
    # 1. كأمر مباشر /make_delivery
    application.add_handler(CommandHandler("make_delivery", promote_to_delivery), group=0)

    # 2. ككلمة يرد بها الأدمن على العضو (مندوب)
    application.add_handler(
        MessageHandler(
            filters.REPLY & filters.Regex("^(مندوب|ترقية مندوب)$"), 
            promote_to_delivery
        ), 
        group=0
    )
    # الحل الأبسط والأفضل: إزالة الفلتر ليتم معالجة كل شيء داخل الدالة
    


# أضف هذا داخل دالة main قبل معالجات النصوص العامة
    # أضف هذا السطر داخل دالة main
# تأكد من وضعه في المجموعة 0 (group=0) ليكون له الأولوية
    # تحديث المعالج ليتوافق مع أزرار إنهاء المشوار الجديدة
    



    application.add_handler(CallbackQueryHandler(handle_callbacks), group=0)
    application.add_handler(MessageHandler(filters.Regex("^❌"), start_command), group=0)
    application.add_handler(
    MessageHandler(
        # استخدام فلتر النص المباشر أدق من Regex في حالات أزرار الـ ReplyKeyboard
        filters.Text([
            "🏁 إنهاء المشوار والدردشة", 
            "❌ إنهاء المحادثة", 
            "🛑 تم إنهاء المحادثة."
        ]), 
        end_chat_command
    ), 
    group=0
)


    # 2. أزرار القائمة الرئيسية (نصوص محددة) - Group 0
    # أضف السطر هنا

# أضف هذا السطر لمراقبة كلمة "احياء" في المجموعات
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex("^(احياء|الأحياء|الأحياء المتاحة)$"), group_districts_handler), group=0)
    application.add_handler(CommandHandler("groups", list_groups_admin), group=0)
    application.add_handler(ChatMemberHandler(on_status_change, ChatMemberHandler.MY_CHAT_MEMBER), group=0)
    # هذا السطر سيلتقط أي عضو جديد يدخل المجموعة
    


    # ---------------------------------------------------------
    # المجموعة 1: ردود الأدمن والنظام (قبل الدردشة العامة)
    # ---------------------------------------------------------
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.REPLY & filters.User(ADMIN_IDS), 
        admin_reply_handler
    ), group=1)
    
    # يُفضل وضع معالج الإنهاء في مجموعة أولوية (group=-1) 
# لضمان اعتراضه قبل أن يذهب النص لمعالج الـ Proxy أو الـ Global
    
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, handle_admin_group_message), group=1)
    # يوضع في مجموعة (group) ليعمل مع بقية الأوامر
    
    
    
    
    application.add_handler(MessageHandler(
    filters.LOCATION & filters.UpdateType.EDITED_MESSAGE, 
    location_handler
), group=1)

    # ---------------------------------------------------------
    # المجموعة 2: إدارة الحالات (التسجيل والقوائم - Global)
    # ---------------------------------------------------------
    # ملاحظة: تم رفع الـ global_handler قبل الـ relay لضمان عمل التسجيل
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (filters.TEXT | filters.PHOTO | filters.LOCATION) & ~filters.COMMAND, 
        global_handler
    ), group=2)
    
    application.add_handler(MessageHandler(filters.ChatType.GROUPS, track_groups_from_messages), group=2)


    # ---------------------------------------------------------
    # المجموعة 3: نظام التوجيه (Chat Relay)
    # ---------------------------------------------------------
    # لا تعمل هذه إلا إذا لم تكن الرسالة (أمر) أو (بيانات تسجيل)
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (filters.TEXT | filters.LOCATION) & ~filters.COMMAND,
        chat_relay_handler
    ), group=3)

    # ---------------------------------------------------------
    # المجموعة 4: المواقع والمجموعات العامة
    # ---------------------------------------------------------
    application.add_handler(MessageHandler(filters.LOCATION, location_handler), group=4)
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT, group_order_scanner), group=4)

    # 3. بدء التشغيل
    print("🚀 البوت يعمل الآن بنظام المجموعات (0 -> 4) بنجاح...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()