#!/umainbin/env python3
# -*- coding: utf-8 -*-

import logging
import threading
import asyncio
import os
import re
import random
import urllib.parse  # أضف هذا الاستيراد في أعلى الملف
from datetime import datetime
from math import radians, cos, sin, asin, sqrt
from enum import Enum
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import BadRequest


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
BOT_TOKEN = "8498451295:AAGt1R7THllSjYtEe5hvIEPnPhRkS_iBcnU"
# آيدي المشرفين
ADMIN_IDS = [8563113166, 7580027135, 7996171713, 5027690233]

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





async def sync_all_users(force=False): # أضفنا force=False
    """تحديث الذاكرة المؤقتة من قاعدة البيانات"""
    global USER_CACHE, CACHED_DRIVERS, LAST_CACHE_SYNC
    
    # إذا لم يكن طلباً إجبارياً، نتحقق من مرور دقيقتين
    if not force:
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





async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name

    # 1. تنظيف الذاكرة لضمان بداية جديدة
    context.user_data.clear()

    # 2. فحص المعاملات القادمة من الروابط (Deep Linking)
    if context.args:
        arg_value = context.args[0]

        if arg_value == "driver_reg":
            # 1. تحديد الحالة (انتظار الاسم)
            context.user_data['state'] = 'WAIT_NAME'
            
            # 2. حفظ "الدور" في الذاكرة (هذا هو السطر الناقص لديك)
            context.user_data['reg_role'] = 'driver'
            
            await update.message.reply_text(
                "🚖 **أهلاً بك يا كابتن في أسرة (ديرعك)**\n\nيرجى كتابة اسمك الثلاثي الآن للبدء في إجراءات التسجيل:",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode="Markdown"
            )
            return
        
        
       
        # --- حالة (sd_): معالجة ضغطة الحي من القروب ---
        if arg_value.startswith("sd_"):
            try:
                index = int(arg_value.split("_")[1])
                districts = CITIES_DISTRICTS.get("المدينة المنورة", [])
                
                if index < len(districts):
                    selected_dist = districts[index]
                    await sync_all_users()
                    
                    def clean(t): 
                        return t.replace("ة", "ه").replace("أ", "ا").replace("إ", "ا")
                    
                    target_clean = clean(selected_dist)

                    matched = [
                        d for d in CACHED_DRIVERS 
                        if d.get('districts') and target_clean in clean(d['districts'])
                    ]

                    if matched:
                        kb = [[InlineKeyboardButton(f"🚖 اطلب {d['name']}", url=f"https://t.me/{context.bot.username}?start=order_{d['user_id']}")] for d in matched[:6]]
                        await update.message.reply_text(
                            f"✅ وجدنا كباتن في حي **{selected_dist}**:\nاختر الكابتن لبدء المحادثة:", 
                            reply_markup=InlineKeyboardMarkup(kb)
                        )
                    else:
                        await update.message.reply_text(
                            f"📍 حي {selected_dist} لا يوجد به كباتن حالياً، جرب طلب مشوار عام بالـ GPS.", 
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🌍 طلب GPS", callback_data="order_general")]])
                        )
                return 
            except Exception as e:
                print(f"Error in sd_ deep link: {e}")

        # --- حالة (reg_rider): التسجيل المباشر كراكب ---
        # --- حالة (reg_rider): بدء مراحل التسجيل كراكب ---
        # --- حالة (reg_rider): التسجيل برقم الجوال فقط ---
        elif arg_value == "reg_rider":
            context.user_data['temp_name'] = first_name 
            context.user_data['state'] = 'WAIT_RIDER_PHONE'
            
            # زر لمشاركة الرقم بشكل آلي وآمن
            keyboard = [[KeyboardButton("📱 مشاركة رقم الجوال", request_contact=True)]]
            
            await update.message.reply_text(
                f"🎉 **حياك الله يا {first_name}!**\n\nلإتمام التسجيل، فضلاً اضغط على الزر أدناه لمشاركة رقم جوالك:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True),
                parse_mode=ParseMode.MARKDOWN
            )
            return




        # --- حالة (reg_driver): التسجيل ككابتن ---
        elif arg_value == "reg_driver":
            context.user_data['reg_role'] = 'driver'
            context.user_data['state'] = 'WAIT_NAME'
            msg = (
                "🚗 **أهلاً بك يا كابتن في فريقنا!**\n\n"
                "لإتمام تسجيلك، نحتاج لبعض البيانات البسيطة.\n"
                "📝 **يرجى كتابة اسمك الثلاثي الآن:**"
            )
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        # --- حالة (order_ID): طلب مشوار من كابتن محدد ---
        elif arg_value.startswith("order_") and arg_value != "order_general":
            try:
                driver_id = arg_value.split("_")[1]
                await sync_all_users()
                if user_id not in USER_CACHE:
                    await auto_register_rider(update)

                context.user_data.update({
                    'driver_to_order': driver_id,
                    'state': 'WAIT_TRIP_DETAILS'
                })

                await update.message.reply_text(
                    f"👋 أهلاً بك يا {first_name}\n📝 **يرجى كتابة تفاصيل مشوارك الآن:**\n(مثال: من حي الخالدية إلى الراشد مول، الساعة 8)",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ إلغاء الطلب")]], resize_keyboard=True),
                    parse_mode=ParseMode.MARKDOWN
                )
                return 
            except Exception as e:
                print(f"Error in order_ ID: {e}")

        # --- حالة (order_general): الطلب العام ---
        elif arg_value == "order_general":
            await sync_all_users()
            if user_id not in USER_CACHE:
                await auto_register_rider(update)

            context.user_data['state'] = 'WAIT_GENERAL_DETAILS'
            await update.message.reply_text(
                "🌍 **بدء طلب مشوار عام (عبر GPS)**\n\n📝 اكتب تفاصيل مشوارك الآن (الوجهة والوقت):",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ إلغاء الطلب")]], resize_keyboard=True),
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # 3. المسار الطبيعي (الدخول اليدوي للبوت بدون روابط)
    await sync_all_users()
    user = USER_CACHE.get(user_id)
    if user:
        await update.message.reply_text(
            f"أهلاً بك مجدداً {user['name']}", 
            reply_markup=get_main_kb(user['role'], user['is_verified'])
        )
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 تسجيل راكب", callback_data="reg_rider"),
             InlineKeyboardButton("🚗 تسجيل كابتن", callback_data="reg_driver")]
        ])
        await update.message.reply_text(
            f"مرحباً بك {first_name}، أنت غير مسجل لدينا.\nاختر نوع الحساب للبدء:", 
            reply_markup=kb
        )

# دالة مساعدة للتسجيل التلقائي لضمان عدم تكرار الكود
async def auto_register_rider(update):
    user_id = update.effective_user.id
    full_name = f"{update.effective_user.first_name} {update.effective_user.last_name or ''}".strip()
    conn = get_db_connection()
    if conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, chat_id, role, name, phone, is_verified)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO NOTHING
            """, (user_id, update.effective_chat.id, 'rider', full_name, '0000000000', True))
            conn.commit()
        conn.close()
        await sync_all_users(force=True)



        # 3. حالة طلب مشوار محدد (من إعلانات الكباتن في القروب)
                # 3. حالة طلب مشوار محدد (من إعلانات الكباتن في القروب)
    elif arg_value.startswith("order_"):
            try:
                # استخراج ID الكابتن فقط (لأن الحي لم نعد نطلبه في الرابط)
                driver_id = arg_value.split("_")[1]

                # --- [جديد] التسجيل التلقائي للراكب إذا لم يكن مسجلاً ---
                await sync_all_users()
                if user_id not in USER_CACHE:
                    conn = get_db_connection()
                    if conn:
                        with conn.cursor() as cur:
                            full_name = f"{update.effective_user.first_name} {update.effective_user.last_name or ''}".strip()
                            cur.execute("""
                                INSERT INTO users (user_id, chat_id, role, name, phone, is_verified)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                ON CONFLICT (user_id) DO NOTHING
                            """, (user_id, update.effective_chat.id, 'rider', full_name, '0000000000', True))
                            conn.commit()
                        conn.close()
                        await sync_all_users(force=True) # تحديث الذاكرة فوراً

                # --- [جديد] التحويل المباشر لطلب التفاصيل ---
                context.user_data.update({
                    'driver_to_order': driver_id,
                    'state': 'WAIT_TRIP_DETAILS'
                })

                await update.message.reply_text(
                    f"👋 أهلاً بك يا {first_name}\n"
                    "لقد اخترت كابتن من القروب.\n\n"
                    "📝 **يرجى كتابة تفاصيل مشوارك الآن:**\n"
                    "(مثال: من الراشد مول إلى الحرم، الوقت 9 مساءً)",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ إلغاء الطلب")]], resize_keyboard=True),
                    parse_mode=ParseMode.MARKDOWN
                )
                return 

            except Exception as e:
                print(f"Deep Link Error: {e}")
                await update.message.reply_text("⚠️ حدث خطأ في الرابط، يرجى المحاولة من القروب مجدداً.")
                return

    # ب) المسار العادي (بدون روابط) - فحص قاعدة البيانات
    await sync_all_users() # تأكد أن هذه الدالة موجودة لديك
    user = USER_CACHE.get(user_id)

    if user:
        # المستخدم مسجل مسبقاً -> عرض القائمة الرئيسية
        role_txt = "الكابتن" if user['role'] == 'driver' else "الراكب"
        await update.message.reply_text(
            f"👋 مرحباً بك مجدداً {role_txt} **{user['name']}**", 
            reply_markup=get_main_kb(user['role'], user['is_verified']),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        # مستخدم جديد (دخل بشكل يدوي) -> عرض خيارات التسجيل
        welcome_new = (
            f"👋 مرحباً بك يا **{first_name}** في بوت التوصيل!\n\n"
            "أنت غير مسجل لدينا، اختر نوع الحساب للبدء:"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 تسجيل كراكب", callback_data="reg_rider"),
             InlineKeyboardButton("🚗 تسجيل ككابتن", callback_data="reg_driver")]
        ])
        await update.message.reply_text(welcome_new, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


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
    elif data.startswith("accept_gen_"):
        # استخراج البيانات: accept_gen_RIDERID_PRICE
        parts = data.split("_")
        rider_id = int(parts[2])
        price = parts[3]
        driver_id = query.from_user.id

        # 1. التحقق من أن الرحلة لم يقبلها سائق آخر (اختياري حسب قاعدة بياناتك)
        # 2. جلب بيانات الكابتن والراكب
        await sync_all_users()
        driver_info = USER_CACHE.get(driver_id)
        rider_info = USER_CACHE.get(rider_id)

        if not rider_info:
            await query.edit_message_text("⚠️ عذراً، هذا الطلب لم يعد متاحاً.")
            return

        # 3. إنشاء جلسة دردشة بين السائق والراكب
        start_chat_session(driver_id, rider_id)

        # 4. تحديث رسالة السائق (إخفاء أزرار القبول)
        await query.edit_message_text(
            f"✅ **تم قبول الرحلة بنجاح!**\n\n👤 الراكب: {rider_info['name']}\n💰 السعر المتفق عليه: {price} ريال\n\n💬 يمكنك الآن التحدث مع الراكب مباشرة هنا.",
            parse_mode=ParseMode.MARKDOWN
        )

        # 5. إشعار الراكب بقبول الرحلة
        try:
            # كيبورد لإنهاء المحادثة
            end_kb = ReplyKeyboardMarkup([[KeyboardButton("❌ إنهاء المحادثة")]], resize_keyboard=True)
            
            await context.bot.send_message(
                chat_id=rider_id,
                text=(f"✅ **أبشر! الكابتن {driver_info['name']} قبل طلبك.**\n"
                      f"🚗 السيارة: {driver_info.get('car_info', 'غير مسجلة')}\n"
                      f"💰 السعر: {price} ريال\n\n"
                      "💬 يمكنك الآن مراسلته مباشرة من هنا:"),
                reply_markup=end_kb,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            print(f"Error notifying rider: {e}")


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

async def complete_registration(update, context, name):
    user = update.effective_user
    user_id = user.id
    chat_id = update.effective_chat.id
    # الحصول على المعرف (Username) إذا وجد
    username = f"@{user.username}" if user.username else "لا يوجد معرف"
    
    role = context.user_data.get('reg_role')
    # للراكب سيكون الرقم أصفار لأننا سجلناه مباشرة
    phone = context.user_data.get('reg_phone', '0000000000')

    conn = get_db_connection()
    if not conn: 
        return

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # الراكب مفعل تلقائياً، السائق يحتاج مراجعة
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
            
        # مزامنة الكاش بعد نجاح العملية في القاعدة
        await sync_all_users()
        context.user_data.clear()

        # --- معالجة مخرجات التسجيل بناءً على الدور ---
        
        if role == 'driver':
            # أزرار التواصل الشفافة
            support_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 مراسلة الإدارة", callback_data="contact_admin_start")],
                [InlineKeyboardButton("👤 الحساب المباشر", url="https://t.me/x3FreTx")]
            ])
            
            # إرسال رسالة "قيد المراجعة" للسائق
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"✅ **أبشرك تم استلام طلبك يا كابتن {name}**\n\n"
                    "حسابك الحين تحت المراجعة، وأول ما يتفعل بيجيك إشعار. خلك قريب!\n\n"
                    "📞 يمكنك التواصل معنا مباشرة عبر الأزرار التالية:"
                ),
                reply_markup=support_kb,
                parse_mode="Markdown"
            )

            # إرسال الكيبورد الرئيسي للسائق (غير مفعل)
            await context.bot.send_message(
                chat_id=chat_id,
                text="📋 قائمة التحكم الخاصة بك:",
                reply_markup=get_main_kb('driver', False)
            )
        
        

            
            # زر القبول والرفض للأدمن
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ قبول", callback_data=f"verify_ok_{user_id}"),
                 InlineKeyboardButton("❌ رفض", callback_data=f"verify_no_{user_id}")]
            ])
            
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
        
        # --- حالة الراكب (بدون إشعار للأدمن) ---
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎉 **يا هلا بيك يا {name}**\nتم تفعيل حسابك كراكب بنجاح، تقدر تطلب مشاويرك من الحين!",
                reply_markup=get_main_kb('rider', True)
            )

    except Exception as e:
        print(f"Error registration: {e}")
        # محاولة إرسال رسالة خطأ للمستخدم
        try:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ حدث خطأ أثناء التسجيل، جرب مرة ثانية.")
        except: pass
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
    """إرسال الطلب للكباتن في نطاق 5 كم فقط وإرجاع قائمة بهم"""
    
    if update.message and update.message.location:
        r_lat = update.message.location.latitude
        r_lon = update.message.location.longitude
    else:
        r_lat = context.user_data.get('lat')
        r_lon = context.user_data.get('lon')

    if r_lat is None or r_lon is None:
        return [] # نعيد قائمة فارغة

    # --- 1. تجهيز رابط الموقع ---
    # هذا الرابط يفتح تطبيق الخرائط مباشرة على إحداثيات الراكب
    map_link = f"https://www.google.com/maps/search/?api=1&query={r_lat},{r_lon}"

    price = context.user_data.get('order_price', 0)
    details = context.user_data.get('search_district', "موقع GPS")
    rider_id = update.effective_user.id

    sent_drivers_list = [] 
    await sync_all_users()

    for d in CACHED_DRIVERS:
        if d['user_id'] == rider_id or d.get('lat') is None: 
            continue

        dist = get_distance(r_lat, r_lon, d['lat'], d['lon'])

        if dist <= 5.0: 
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(f"✅ قبول ({price} ريال)", callback_data=f"accept_gen_{rider_id}_{price}")
            ]])

            try:
                # --- 2. إضافة الرابط في الرسالة ---
                await context.bot.send_message(
                    chat_id=d['user_id'],
                    text=(f"🚨 **طلب جديد قريب منك!**\n\n"
                          f"📍 المسافة: {dist:.1f} كم\n"
                          f"📝 الوجهة: {details}\n"
                          f"💰 السعر: {price} ريال\n\n"
                          f"🗺 [اضغط هنا لعرض موقع الراكب]({map_link})"), # إضافة الرابط هنا
                    reply_markup=kb,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=False # تفعيل المعاينة لتظهر الخريطة المصغرة
                )
                sent_drivers_list.append(d)
            except: 
                continue

    return sent_drivers_list

async def end_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # 1. إنهاء الجلسة في قاعدة البيانات وجلب آيدي الطرف الآخر
    partner_id = end_chat_session(user_id)
    
    # 2. تنظيف ذاكرة البوت للمستخدم الحالي
    context.user_data.clear()
    
    # 3. جلب بيانات المستخدم لتحديد الكيبورد المناسب (سائق أم راكب)
    await sync_all_users()
    user = USER_CACHE.get(user_id)
    role = user['role'] if user else 'rider'
    is_v = user.get('is_verified', True) if user else True
    
    # 4. إرسال رسالة التأكيد والعودة للقائمة الرئيسية
    await update.message.reply_text(
        "🛑 تم إنهاء المحادثة والعودة للقائمة الرئيسية.",
        reply_markup=get_main_kb(role, is_v)
    )

    # 5. إبلاغ الطرف الآخر إذا كان موجوداً
    if partner_id:
        try:
            p_user = USER_CACHE.get(partner_id)
            p_role = p_user['role'] if p_user else 'rider'
            p_v = p_user.get('is_verified', True) if p_user else True
            
            await context.bot.send_message(
                chat_id=partner_id,
                text="🛑 قام الطرف الآخر بإنهاء المحادثة.",
                reply_markup=get_main_kb(p_role, p_v)
            )
        except Exception as e:
            print(f"Error notifying partner: {e}")

# --- المعالج الشامل (Global Handler) ---


# --- المعالج الشامل (Global Handler) ---
async def global_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get('state')
    text = update.message.text
    user_id = update.effective_user.id

        # --- [تعديل] خطوات تسجيل السائق المحدثة ---
    
    # 1. استلام الاسم
    if state == 'WAIT_NAME':
            context.user_data['reg_name'] = text
            context.user_data['state'] = 'WAIT_PHONE'
            await update.message.reply_text("📱 **أبشر، الحين أرسل رقم جوالك:**\n(مثال: 05xxxxxxxx)")
            return

    if state == 'WAIT_PHONE':
            phone_input = text.strip()
            # التحقق من صحة الرقم (يبدأ بـ 05 و 10 أرقام)
            if not re.fullmatch(r'05\d{8}', phone_input):
                await update.message.reply_text("⚠️ **الرقم غير صحيح..**\nلازم يبدأ بـ 05 ويتكون من 10 أرقام.")
                return
            
            # الحفظ والإتمام
            context.user_data['reg_phone'] = phone_input
            await complete_registration(update, context, context.user_data['reg_name'])
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

    if not update.message: return
    
    # استخراج البيانات
    user = update.effective_user
    user_id = user.id
    state = context.user_data.get('state')
    # نستخدم النص إذا وجد، وإلا نص فارغ (لتجنب الأخطاء مع الصور)
    text = update.message.text if update.message.text else ""

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
        
        if not phone.isdigit() or len(phone) < 9:
            await update.message.reply_text("⚠️ يرجى إرسال رقم جوال صحيح.")
            return

        # 1. إنشاء الحساب بالرقم الحقيقي
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (user_id, chat_id, role, name, phone, is_verified)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE 
                    SET phone = EXCLUDED.phone, role = 'rider'
                """, (user_id, update.effective_chat.id, 'rider', user_info.full_name, phone, True))
                conn.commit()
            conn.close()
            await sync_all_users(force=True)

        # 2. فحص هل كان قادماً من رابط طلب؟
        pending_driver = context.user_data.get('pending_order_driver')
        if pending_driver:
            context.user_data.update({
                'driver_to_order': pending_driver,
                'state': 'WAIT_TRIP_DETAILS',
                'pending_order_driver': None # تنظيف الذاكرة
            })
            await update.message.reply_text(
                f"✅ تم تسجيل رقمك: `{phone}`\n\nالآن، **اكتب تفاصيل مشوارك** لإرسالها للكابتن:",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ إلغاء الطلب")]], resize_keyboard=True)
            )
        else:
            # دخول عادي للمنيو
            context.user_data['state'] = None
            await update.message.reply_text(
                "✅ تم التسجيل بنجاح!",
                reply_markup=get_main_kb('rider', True)
            )
        return


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
    if update.message.chat.type == "private":
        
        # 1. تجهيز الرسالة للأدمن
        admin_text = (
            f"📩 **رسالة واردة (دعم فني)**\n"
            f"👤 الاسم: {user.full_name}\n"
            f"🆔 ID: `{user_id}`\n"
            f"🔗 المعرف: @{user.username if user.username else 'لا يوجد'}\n"
            f"📝 النص: {text}\n"
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

        # 3. الإرسال لكل المشرفين
        for aid in ADMIN_IDS:
            try:
                # إرسال بطاقة المعلومات
                await context.bot.send_message(chat_id=aid, text=admin_text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
                # تحويل رسالة المستخدم الأصلية (مفيد إذا كانت صورة أو فيديو)
                await context.bot.copy_message(chat_id=aid, from_chat_id=user_id, message_id=update.message.message_id)
            except: pass

        # 4. حفظ في السجل
        # تأكد من أن دالة save_chat_log موجودة ومستوردة
        save_chat_log(user_id, ADMIN_IDS[0], text or "[ملف/موقع]", "support_msg")

        # 5. إشعار المستخدم (مرة واحدة)
        # لتجنب التكرار، نرسل التأكيد فقط إذا لم يكن في حالة تواصل مسبق
        # (اختياري: يمكنك إزالة هذا السطر إذا كنت تراه مزعجاً)
        await update.message.reply_text("📨 تم استلام رسالتك وتحويلها لفريق الدعم.")

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

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    location = update.message.location
    state = context.user_data.get('state')

    # --- الخطوة 1: فحص المحادثة النشطة (الأولوية القصوى) ---
    # إذا كان المستخدم في محادثة، نرسل الموقع للطرف الآخر فقط وننهي الدالة
    partner_id = get_chat_partner(user_id)
    if partner_id:
        try:
            # توجيه الموقع للطرف الآخر
            await context.bot.copy_message(
                chat_id=partner_id,
                from_chat_id=user_id,
                message_id=update.message.message_id
            )
            # اختياري: حفظ في السجلات
            msg_content = f"📍 موقع: {location.latitude}, {location.longitude}"
            conn = get_db_connection()
            if conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO chat_logs (sender_id, receiver_id, message_content, msg_type) VALUES (%s, %s, %s, %s)",
                                (int(user_id), int(partner_id), msg_content, "location"))
                    conn.commit()
                conn.close()
            return # إنهاء الدالة هنا يمنع تكرار طلب الرحلة
        except Exception as e:
            print(f"❌ فشل تمرير الموقع للمشترك: {e}")

    # --- الخطوة 2: تحديث الإحداثيات العامة ---
    context.user_data['lat'] = location.latitude
    context.user_data['lon'] = location.longitude
    threading.Thread(target=update_db_location, args=(user_id, location.latitude, location.longitude)).start()

    # --- الخطوة 3: جلب بيانات المستخدم ---
    await sync_all_users() 
    user_data = USER_CACHE.get(user_id, {})
    user_role = user_data.get('role', 'rider')
    is_verified = user_data.get('is_verified', False)

    # --- الخطوة 4: معالجة طلب الرحلة (في حال عدم وجود محادثة) ---
    # --- الخطوة 4: معالجة طلب الرحلة ---
    if state == 'WAIT_LOCATION_FOR_ORDER' and user_role == 'rider':
        processing_msg = await update.message.reply_text("📡 جاري البحث عن أقرب كباتن (نطاق 5 كم)...")
        
        # استدعاء الدالة الجديدة التي تعيد القائمة
        drivers_list = await broadcast_general_order(update, context)
        
        if drivers_list:
            keyboard = []
            current_row = []
            
            # عرض السائقين الفعليين الذين استلموا الطلب
            for d in drivers_list[:10]: # حد أقصى 10
                d_name = d.get('name', 'كابتن')
                d_id = d.get('user_id')
                
                # زر للتواصل المباشر مع الكابتن
                button = InlineKeyboardButton(
                    text=f"📞 {d_name}", 
                    url=f"https://t.me/{context.bot.username}?start=order_{d_id}"
                )
                current_row.append(button)
                
                if len(current_row) == 2:
                    keyboard.append(current_row)
                    current_row = []
            
            if current_row:
                keyboard.append(current_row)

            await processing_msg.edit_text(
                f"✅ تم إرسال طلبك إلى **{len(drivers_list)}** كابتن بالقرب منك.\n\n"
                "يمكنك انتظار قبول أحدهم، أو التواصل معهم مباشرة عبر الأزرار:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        else:
            await processing_msg.edit_text(
                "⚠️ لم يتم العثور على كباتن في نطاق 5 كم حالياً.",
                reply_markup=get_main_kb("rider", True)
            )
        
        context.user_data['state'] = None


    # --- الخطوة 5: تحديث الموقع العادي ---
    else:
        await update.message.reply_text(
            "📍 تم تحديث موقعك الجغرافي بنجاح.",
            reply_markup=get_main_kb(user_role, is_verified)
        )



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
            "📝 يرجى كتابة **تفاصيل مشوارك** الآن (من وين لوين؟):",
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

async def group_order_scanner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    text = update.message.text
    # 1. تنظيف النص (يجب أن تكون دالة normalize_text موجودة في ملفك)
    msg_clean = normalize_text(text)

    # 2. تعريف قوائم الكلمات (يجب تعريفها في البداية لتجنب الأخطاء)
    REQUEST_KEYWORDS = [
        "توصيل", "طلب", "طلبات", "غرض", "اغراض", "مقاضي", "مشوار", "مشاوير", "روحه", "جيه", "توصيلة", "توصيله", 
        "كابتن", "سواق", "سائق", "سيارة", "سياره", "ابي", "ابغى", "محتاج", "في احد", "وديني", "استلام", 
        "مطعم", "اكل", "وجبة", "عشاء", "غداء", "فطور", "سحور", "حلويات", "كوفي", "قهوة", "عصير", "البيك", 
        "تموينات", "بقالة", "خضار", "هدية", "ورد", "باقة", "كيك", "شحنه", "طرد", "صيدلية", "علاج", "دواء",
        "دوام", "عمل", "جامعة", "كلية", "مدرسة", "معهد", "الحرم", "المطار", "مستشفى", "موعد", "سوق", "بنات"
    ]

    SPAM_KEYWORDS = [
        "شهري", "حل واجبات", "راتب", "استثمار", "ربح سريع", "تداول", 
        "منصة استثمار", "تسديد ديون", "قرض", "تمويل شخصي", "زيادة متابعين", 
        "بيع حسابات", "عملات رقمية", "بوت ربح", "هدية مالية", "مسابقة كبرى"
    ]

    # 3. نظام الحماية من الاحتيال (فحص فوري)
    if any(k in msg_clean for k in SPAM_KEYWORDS):
        contact_url = f"tg://user?id={user.id}"
        if user.username: contact_url = f"https://t.me/{user.username}"
        
        admin_report = (f"⚠️ **رسالة محجوبة:**\n👤 العميل: {user.full_name}\n🆔 الآيدي: `{user.id}`\n💬 النص: {text}")
        admin_kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬 مراسلة العميل", url=contact_url)]])

        for admin_id in ADMIN_IDS:
            try: await context.bot.send_message(chat_id=admin_id, text=admin_report, reply_markup=admin_kb, parse_mode="Markdown")
            except: pass
        
        try: await update.message.delete()
        except: pass
        return

    # 4. البحث عن الحي في الرسالة
    found_dist = None
    districts_list = CITIES_DISTRICTS.get("المدينة المنورة", [])
    for dist in sorted(districts_list, key=len, reverse=True):
        if normalize_text(dist) in msg_clean:
            found_dist = dist
            break

    # 5. التحقق من الحالات (أدمن، طلب، حي)
    is_admin_run = (msg_clean.strip() == "رن" and user.id in ADMIN_IDS)
    has_request = any(k in msg_clean for k in REQUEST_KEYWORDS)

    # الحالة أ: أمر "رن" أو وجود "طلب" بدون ذكر "الحي"
    if is_admin_run or (has_request and not found_dist):
        welcome_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🚕 تسجيل كابتن", url=f"https://t.me/{context.bot.username}?start=driver_reg"),
                InlineKeyboardButton("📱 طلب مشوار", url=f"https://t.me/{context.bot.username}?start=order_general")
            ],
            [InlineKeyboardButton("📋 المندوبين المعتمدين", callback_data="show_all_delivery")],
            [InlineKeyboardButton("🛍️ تعليمات المتاجر", callback_data="help_delivery_orders")]
        ])
        
        await update.message.reply_text(
            f"🌴 **حياك الله في {context.bot.name}** 🌴\n\n"
            f"يا {user.first_name}، لخدمتك بشكل أسرع:\n"
            f"✅ اكتب طلبك مع **اسم الحي** في رسالة واحدة.\n"
            f"أو اختر من القائمة التالية:", 
            reply_markup=welcome_kb,
            parse_mode="Markdown"
        )
        
        if is_admin_run:
            try: await update.message.delete()
            except: pass
        return

    # الحالة ب: وجود "طلب" مع "الحي" -> إظهار الكباتن
     # 5. إذا وجد الحي والطلب (عرض جميع السائقين)
       # 3. تعديل المنطق: إذا وجد الحي، نعرض السائقين فوراً
    if found_dist:
        await sync_all_users()
        # جلب جميع السائقين في هذا الحي
        matched_drivers = [d for d in CACHED_DRIVERS if found_dist in str(d.get('districts', ''))]

        if matched_drivers:
            
            random.shuffle(matched_drivers)
            
            keyboard = []
            current_row = []
            for d in matched_drivers:
                button = InlineKeyboardButton(f"📞 {d['name']}", url=f"https://t.me/{context.bot.username}?start=order_{d['user_id']}")
                current_row.append(button)
                if len(current_row) == 2:
                    keyboard.append(current_row)
                    current_row = []
            if current_row: keyboard.append(current_row)
            
            await update.message.reply_text(
                f"✅ وجدنا **{len(matched_drivers)}** كابتن في حي **{found_dist}**:", 
                reply_markup=InlineKeyboardMarkup(keyboard), 
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            # نرد بعدم التوفر فقط إذا كان الكلام أصلاً يحتوي على "كلمة طلب"
            # لكي لا يحرج البوت نفسه بالرد "لا يوجد" على شخص ذكر اسم الحي صدفة
            if has_request:
                await update.message.reply_text(f"📍 حي {found_dist}: لا يوجد كباتن متاحين حالياً.")
        return # إنهاء المعالجة هنا

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
    partner_id = get_chat_partner(user_id)
    
    # إذا لم يكن هناك طرف آخر (ليست رحلة نشطة)، اترك الرسالة تمر للمعالج التالي
    if not partner_id:
        return 
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
             await update.message.reply_text("⚠️ لم أتمكن من استخراج ID العضو. تأكد أنك ترد على رسالة البوت التي تحتوي على البيانات.")
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
    application.add_handler(MessageHandler(filters.Regex("^(❌ إنهاء المحادثة|🛑 تم إنهاء المحادثة.)$"), end_chat_command), group=0)


    application.add_handler(CallbackQueryHandler(handle_callbacks), group=0)
    application.add_handler(MessageHandler(filters.Regex("^❌"), start_command), group=0)


    # 2. أزرار القائمة الرئيسية (نصوص محددة) - Group 0
    # أضف السطر هنا

# أضف هذا السطر لمراقبة كلمة "احياء" في المجموعات
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex("^(احياء|الأحياء|الأحياء المتاحة)$"), group_districts_handler), group=0)


    # هذا السطر سيلتقط أي عضو جديد يدخل المجموعة
    


    # ---------------------------------------------------------
    # المجموعة 1: ردود الأدمن والنظام (قبل الدردشة العامة)
    # ---------------------------------------------------------
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.REPLY & filters.User(ADMIN_IDS), 
        admin_reply_handler
    ), group=1)
    # يوضع في مجموعة (group) ليعمل مع بقية الأوامر
    
    
    
    
    

    # ---------------------------------------------------------
    # المجموعة 2: إدارة الحالات (التسجيل والقوائم - Global)
    # ---------------------------------------------------------
    # ملاحظة: تم رفع الـ global_handler قبل الـ relay لضمان عمل التسجيل
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (filters.TEXT | filters.PHOTO | filters.LOCATION) & ~filters.COMMAND, 
        global_handler
    ), group=2)


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
    main()#!/umainbin/env python3
# -*- coding: utf-8 -*-

import logging
import threading
import asyncio
import os
import re
import random
import urllib.parse  # أضف هذا الاستيراد في أعلى الملف
from datetime import datetime
from math import radians, cos, sin, asin, sqrt
from enum import Enum
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import BadRequest


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
BOT_TOKEN = "8284667095:AAEVzyE8cutBHYT8y-IF-OHZoRT9IN7LXqw"
# آيدي المشرفين
ADMIN_IDS = [8563113166, 7580027135, 7996171713, 5027690233]

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





async def sync_all_users(force=False): # أضفنا force=False
    """تحديث الذاكرة المؤقتة من قاعدة البيانات"""
    global USER_CACHE, CACHED_DRIVERS, LAST_CACHE_SYNC
    
    # إذا لم يكن طلباً إجبارياً، نتحقق من مرور دقيقتين
    if not force:
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





async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name

    # 1. تنظيف الذاكرة لضمان بداية جديدة
    context.user_data.clear()

    # 2. فحص المعاملات القادمة من الروابط (Deep Linking)
    if context.args:
        arg_value = context.args[0]

        if arg_value == "driver_reg":
            # 1. تحديد الحالة (انتظار الاسم)
            context.user_data['state'] = 'WAIT_NAME'
            
            # 2. حفظ "الدور" في الذاكرة (هذا هو السطر الناقص لديك)
            context.user_data['reg_role'] = 'driver'
            
            await update.message.reply_text(
                "🚖 **أهلاً بك يا كابتن في أسرة (ديرعك)**\n\nيرجى كتابة اسمك الثلاثي الآن للبدء في إجراءات التسجيل:",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode="Markdown"
            )
            return
        
        
       
        # --- حالة (sd_): معالجة ضغطة الحي من القروب ---
        if arg_value.startswith("sd_"):
            try:
                index = int(arg_value.split("_")[1])
                districts = CITIES_DISTRICTS.get("المدينة المنورة", [])
                
                if index < len(districts):
                    selected_dist = districts[index]
                    await sync_all_users()
                    
                    def clean(t): 
                        return t.replace("ة", "ه").replace("أ", "ا").replace("إ", "ا")
                    
                    target_clean = clean(selected_dist)

                    matched = [
                        d for d in CACHED_DRIVERS 
                        if d.get('districts') and target_clean in clean(d['districts'])
                    ]

                    if matched:
                        kb = [[InlineKeyboardButton(f"🚖 اطلب {d['name']}", url=f"https://t.me/{context.bot.username}?start=order_{d['user_id']}")] for d in matched[:6]]
                        await update.message.reply_text(
                            f"✅ وجدنا كباتن في حي **{selected_dist}**:\nاختر الكابتن لبدء المحادثة:", 
                            reply_markup=InlineKeyboardMarkup(kb)
                        )
                    else:
                        await update.message.reply_text(
                            f"📍 حي {selected_dist} لا يوجد به كباتن حالياً، جرب طلب مشوار عام بالـ GPS.", 
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🌍 طلب GPS", callback_data="order_general")]])
                        )
                return 
            except Exception as e:
                print(f"Error in sd_ deep link: {e}")

        # --- حالة (reg_rider): التسجيل المباشر كراكب ---
        # --- حالة (reg_rider): بدء مراحل التسجيل كراكب ---
        # --- حالة (reg_rider): التسجيل برقم الجوال فقط ---
        elif arg_value == "reg_rider":
            context.user_data['temp_name'] = first_name 
            context.user_data['state'] = 'WAIT_RIDER_PHONE'
            
            # زر لمشاركة الرقم بشكل آلي وآمن
            keyboard = [[KeyboardButton("📱 مشاركة رقم الجوال", request_contact=True)]]
            
            await update.message.reply_text(
                f"🎉 **حياك الله يا {first_name}!**\n\nلإتمام التسجيل، فضلاً اضغط على الزر أدناه لمشاركة رقم جوالك:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True),
                parse_mode=ParseMode.MARKDOWN
            )
            return




        # --- حالة (reg_driver): التسجيل ككابتن ---
        elif arg_value == "reg_driver":
            context.user_data['reg_role'] = 'driver'
            context.user_data['state'] = 'WAIT_NAME'
            msg = (
                "🚗 **أهلاً بك يا كابتن في فريقنا!**\n\n"
                "لإتمام تسجيلك، نحتاج لبعض البيانات البسيطة.\n"
                "📝 **يرجى كتابة اسمك الثلاثي الآن:**"
            )
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        # --- حالة (order_ID): طلب مشوار من كابتن محدد ---
        elif arg_value.startswith("order_") and arg_value != "order_general":
            try:
                driver_id = arg_value.split("_")[1]
                await sync_all_users()
                if user_id not in USER_CACHE:
                    await auto_register_rider(update)

                context.user_data.update({
                    'driver_to_order': driver_id,
                    'state': 'WAIT_TRIP_DETAILS'
                })

                await update.message.reply_text(
                    f"👋 أهلاً بك يا {first_name}\n📝 **يرجى كتابة تفاصيل مشوارك الآن:**\n(مثال: من حي الخالدية إلى الراشد مول، الساعة 8)",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ إلغاء الطلب")]], resize_keyboard=True),
                    parse_mode=ParseMode.MARKDOWN
                )
                return 
            except Exception as e:
                print(f"Error in order_ ID: {e}")

        # --- حالة (order_general): الطلب العام ---
        elif arg_value == "order_general":
            await sync_all_users()
            if user_id not in USER_CACHE:
                await auto_register_rider(update)

            context.user_data['state'] = 'WAIT_GENERAL_DETAILS'
            await update.message.reply_text(
                "🌍 **بدء طلب مشوار عام (عبر GPS)**\n\n📝 اكتب تفاصيل مشوارك الآن (الوجهة والوقت):",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ إلغاء الطلب")]], resize_keyboard=True),
                parse_mode=ParseMode.MARKDOWN
            )
            return

    # 3. المسار الطبيعي (الدخول اليدوي للبوت بدون روابط)
    await sync_all_users()
    user = USER_CACHE.get(user_id)
    if user:
        await update.message.reply_text(
            f"أهلاً بك مجدداً {user['name']}", 
            reply_markup=get_main_kb(user['role'], user['is_verified'])
        )
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 تسجيل راكب", callback_data="reg_rider"),
             InlineKeyboardButton("🚗 تسجيل كابتن", callback_data="reg_driver")]
        ])
        await update.message.reply_text(
            f"مرحباً بك {first_name}، أنت غير مسجل لدينا.\nاختر نوع الحساب للبدء:", 
            reply_markup=kb
        )

# دالة مساعدة للتسجيل التلقائي لضمان عدم تكرار الكود
async def auto_register_rider(update):
    user_id = update.effective_user.id
    full_name = f"{update.effective_user.first_name} {update.effective_user.last_name or ''}".strip()
    conn = get_db_connection()
    if conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, chat_id, role, name, phone, is_verified)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO NOTHING
            """, (user_id, update.effective_chat.id, 'rider', full_name, '0000000000', True))
            conn.commit()
        conn.close()
        await sync_all_users(force=True)



        # 3. حالة طلب مشوار محدد (من إعلانات الكباتن في القروب)
                # 3. حالة طلب مشوار محدد (من إعلانات الكباتن في القروب)
    elif arg_value.startswith("order_"):
            try:
                # استخراج ID الكابتن فقط (لأن الحي لم نعد نطلبه في الرابط)
                driver_id = arg_value.split("_")[1]

                # --- [جديد] التسجيل التلقائي للراكب إذا لم يكن مسجلاً ---
                await sync_all_users()
                if user_id not in USER_CACHE:
                    conn = get_db_connection()
                    if conn:
                        with conn.cursor() as cur:
                            full_name = f"{update.effective_user.first_name} {update.effective_user.last_name or ''}".strip()
                            cur.execute("""
                                INSERT INTO users (user_id, chat_id, role, name, phone, is_verified)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                ON CONFLICT (user_id) DO NOTHING
                            """, (user_id, update.effective_chat.id, 'rider', full_name, '0000000000', True))
                            conn.commit()
                        conn.close()
                        await sync_all_users(force=True) # تحديث الذاكرة فوراً

                # --- [جديد] التحويل المباشر لطلب التفاصيل ---
                context.user_data.update({
                    'driver_to_order': driver_id,
                    'state': 'WAIT_TRIP_DETAILS'
                })

                await update.message.reply_text(
                    f"👋 أهلاً بك يا {first_name}\n"
                    "لقد اخترت كابتن من القروب.\n\n"
                    "📝 **يرجى كتابة تفاصيل مشوارك الآن:**\n"
                    "(مثال: من الراشد مول إلى الحرم، الوقت 9 مساءً)",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ إلغاء الطلب")]], resize_keyboard=True),
                    parse_mode=ParseMode.MARKDOWN
                )
                return 

            except Exception as e:
                print(f"Deep Link Error: {e}")
                await update.message.reply_text("⚠️ حدث خطأ في الرابط، يرجى المحاولة من القروب مجدداً.")
                return

    # ب) المسار العادي (بدون روابط) - فحص قاعدة البيانات
    await sync_all_users() # تأكد أن هذه الدالة موجودة لديك
    user = USER_CACHE.get(user_id)

    if user:
        # المستخدم مسجل مسبقاً -> عرض القائمة الرئيسية
        role_txt = "الكابتن" if user['role'] == 'driver' else "الراكب"
        await update.message.reply_text(
            f"👋 مرحباً بك مجدداً {role_txt} **{user['name']}**", 
            reply_markup=get_main_kb(user['role'], user['is_verified']),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        # مستخدم جديد (دخل بشكل يدوي) -> عرض خيارات التسجيل
        welcome_new = (
            f"👋 مرحباً بك يا **{first_name}** في بوت التوصيل!\n\n"
            "أنت غير مسجل لدينا، اختر نوع الحساب للبدء:"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 تسجيل كراكب", callback_data="reg_rider"),
             InlineKeyboardButton("🚗 تسجيل ككابتن", callback_data="reg_driver")]
        ])
        await update.message.reply_text(welcome_new, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


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
    elif data.startswith("accept_gen_"):
        # استخراج البيانات: accept_gen_RIDERID_PRICE
        parts = data.split("_")
        rider_id = int(parts[2])
        price = parts[3]
        driver_id = query.from_user.id

        # 1. التحقق من أن الرحلة لم يقبلها سائق آخر (اختياري حسب قاعدة بياناتك)
        # 2. جلب بيانات الكابتن والراكب
        await sync_all_users()
        driver_info = USER_CACHE.get(driver_id)
        rider_info = USER_CACHE.get(rider_id)

        if not rider_info:
            await query.edit_message_text("⚠️ عذراً، هذا الطلب لم يعد متاحاً.")
            return

        # 3. إنشاء جلسة دردشة بين السائق والراكب
        start_chat_session(driver_id, rider_id)

        # 4. تحديث رسالة السائق (إخفاء أزرار القبول)
        await query.edit_message_text(
            f"✅ **تم قبول الرحلة بنجاح!**\n\n👤 الراكب: {rider_info['name']}\n💰 السعر المتفق عليه: {price} ريال\n\n💬 يمكنك الآن التحدث مع الراكب مباشرة هنا.",
            parse_mode=ParseMode.MARKDOWN
        )

        # 5. إشعار الراكب بقبول الرحلة
        try:
            # كيبورد لإنهاء المحادثة
            end_kb = ReplyKeyboardMarkup([[KeyboardButton("❌ إنهاء المحادثة")]], resize_keyboard=True)
            
            await context.bot.send_message(
                chat_id=rider_id,
                text=(f"✅ **أبشر! الكابتن {driver_info['name']} قبل طلبك.**\n"
                      f"🚗 السيارة: {driver_info.get('car_info', 'غير مسجلة')}\n"
                      f"💰 السعر: {price} ريال\n\n"
                      "💬 يمكنك الآن مراسلته مباشرة من هنا:"),
                reply_markup=end_kb,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            print(f"Error notifying rider: {e}")


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

async def complete_registration(update, context, name):
    user = update.effective_user
    user_id = user.id
    chat_id = update.effective_chat.id
    # الحصول على المعرف (Username) إذا وجد
    username = f"@{user.username}" if user.username else "لا يوجد معرف"
    
    role = context.user_data.get('reg_role')
    # للراكب سيكون الرقم أصفار لأننا سجلناه مباشرة
    phone = context.user_data.get('reg_phone', '0000000000')

    conn = get_db_connection()
    if not conn: 
        return

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # الراكب مفعل تلقائياً، السائق يحتاج مراجعة
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
            
        # مزامنة الكاش بعد نجاح العملية في القاعدة
        await sync_all_users()
        context.user_data.clear()

        # --- معالجة مخرجات التسجيل بناءً على الدور ---
        
        if role == 'driver':
            # أزرار التواصل الشفافة
            support_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 مراسلة الإدارة", callback_data="contact_admin_start")],
                [InlineKeyboardButton("👤 الحساب المباشر", url="https://t.me/x3FreTx")]
            ])
            
            # إرسال رسالة "قيد المراجعة" للسائق
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"✅ **أبشرك تم استلام طلبك يا كابتن {name}**\n\n"
                    "حسابك الحين تحت المراجعة، وأول ما يتفعل بيجيك إشعار. خلك قريب!\n\n"
                    "📞 يمكنك التواصل معنا مباشرة عبر الأزرار التالية:"
                ),
                reply_markup=support_kb,
                parse_mode="Markdown"
            )

            # إرسال الكيبورد الرئيسي للسائق (غير مفعل)
            await context.bot.send_message(
                chat_id=chat_id,
                text="📋 قائمة التحكم الخاصة بك:",
                reply_markup=get_main_kb('driver', False)
            )
        
        

            
            # زر القبول والرفض للأدمن
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ قبول", callback_data=f"verify_ok_{user_id}"),
                 InlineKeyboardButton("❌ رفض", callback_data=f"verify_no_{user_id}")]
            ])
            
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
        
        # --- حالة الراكب (بدون إشعار للأدمن) ---
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎉 **يا هلا بيك يا {name}**\nتم تفعيل حسابك كراكب بنجاح، تقدر تطلب مشاويرك من الحين!",
                reply_markup=get_main_kb('rider', True)
            )

    except Exception as e:
        print(f"Error registration: {e}")
        # محاولة إرسال رسالة خطأ للمستخدم
        try:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ حدث خطأ أثناء التسجيل، جرب مرة ثانية.")
        except: pass
    finally:
        conn.close()

# --- طلب الرحلات ---

async def broadcast_general_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال الطلب للكباتن في نطاق 5 كم فقط وإرجاع قائمة بهم"""
    
    if update.message and update.message.location:
        r_lat = update.message.location.latitude
        r_lon = update.message.location.longitude
    else:
        r_lat = context.user_data.get('lat')
        r_lon = context.user_data.get('lon')

    if r_lat is None or r_lon is None:
        return [] # نعيد قائمة فارغة

    # --- 1. تجهيز رابط الموقع ---
    # هذا الرابط يفتح تطبيق الخرائط مباشرة على إحداثيات الراكب
    map_link = f"https://www.google.com/maps/search/?api=1&query={r_lat},{r_lon}"

    price = context.user_data.get('order_price', 0)
    details = context.user_data.get('search_district', "موقع GPS")
    rider_id = update.effective_user.id

    sent_drivers_list = [] 
    await sync_all_users()

    for d in CACHED_DRIVERS:
        if d['user_id'] == rider_id or d.get('lat') is None: 
            continue

        dist = get_distance(r_lat, r_lon, d['lat'], d['lon'])

        if dist <= 5.0: 
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(f"✅ قبول ({price} ريال)", callback_data=f"accept_gen_{rider_id}_{price}")
            ]])

            try:
                # --- 2. إضافة الرابط في الرسالة ---
                await context.bot.send_message(
                    chat_id=d['user_id'],
                    text=(f"🚨 **طلب جديد قريب منك!**\n\n"
                          f"📍 المسافة: {dist:.1f} كم\n"
                          f"📝 الوجهة: {details}\n"
                          f"💰 السعر: {price} ريال\n\n"
                          f"🗺 [اضغط هنا لعرض موقع الراكب]({map_link})"), # إضافة الرابط هنا
                    reply_markup=kb,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=False # تفعيل المعاينة لتظهر الخريطة المصغرة
                )
                sent_drivers_list.append(d)
            except: 
                continue

    return sent_drivers_list

async def end_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # 1. إنهاء الجلسة في قاعدة البيانات وجلب آيدي الطرف الآخر
    partner_id = end_chat_session(user_id)
    
    # 2. تنظيف ذاكرة البوت للمستخدم الحالي
    context.user_data.clear()
    
    # 3. جلب بيانات المستخدم لتحديد الكيبورد المناسب (سائق أم راكب)
    await sync_all_users()
    user = USER_CACHE.get(user_id)
    role = user['role'] if user else 'rider'
    is_v = user.get('is_verified', True) if user else True
    
    # 4. إرسال رسالة التأكيد والعودة للقائمة الرئيسية
    await update.message.reply_text(
        "🛑 تم إنهاء المحادثة والعودة للقائمة الرئيسية.",
        reply_markup=get_main_kb(role, is_v)
    )

    # 5. إبلاغ الطرف الآخر إذا كان موجوداً
    if partner_id:
        try:
            p_user = USER_CACHE.get(partner_id)
            p_role = p_user['role'] if p_user else 'rider'
            p_v = p_user.get('is_verified', True) if p_user else True
            
            await context.bot.send_message(
                chat_id=partner_id,
                text="🛑 قام الطرف الآخر بإنهاء المحادثة.",
                reply_markup=get_main_kb(p_role, p_v)
            )
        except Exception as e:
            print(f"Error notifying partner: {e}")

# --- المعالج الشامل (Global Handler) ---


# --- المعالج الشامل (Global Handler) ---
async def global_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get('state')
    text = update.message.text
    user_id = update.effective_user.id

        # --- [تعديل] خطوات تسجيل السائق المحدثة ---
    
    # 1. استلام الاسم
    if state == 'WAIT_NAME':
            context.user_data['reg_name'] = text
            context.user_data['state'] = 'WAIT_PHONE'
            await update.message.reply_text("📱 **أبشر، الحين أرسل رقم جوالك:**\n(مثال: 05xxxxxxxx)")
            return

    if state == 'WAIT_PHONE':
            phone_input = text.strip()
            # التحقق من صحة الرقم (يبدأ بـ 05 و 10 أرقام)
            if not re.fullmatch(r'05\d{8}', phone_input):
                await update.message.reply_text("⚠️ **الرقم غير صحيح..**\nلازم يبدأ بـ 05 ويتكون من 10 أرقام.")
                return
            
            # الحفظ والإتمام
            context.user_data['reg_phone'] = phone_input
            await complete_registration(update, context, context.user_data['reg_name'])
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

    if not update.message: return
    
    # استخراج البيانات
    user = update.effective_user
    user_id = user.id
    state = context.user_data.get('state')
    # نستخدم النص إذا وجد، وإلا نص فارغ (لتجنب الأخطاء مع الصور)
    text = update.message.text if update.message.text else ""

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
        
        if not phone.isdigit() or len(phone) < 9:
            await update.message.reply_text("⚠️ يرجى إرسال رقم جوال صحيح.")
            return

        # 1. إنشاء الحساب بالرقم الحقيقي
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (user_id, chat_id, role, name, phone, is_verified)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE 
                    SET phone = EXCLUDED.phone, role = 'rider'
                """, (user_id, update.effective_chat.id, 'rider', user_info.full_name, phone, True))
                conn.commit()
            conn.close()
            await sync_all_users(force=True)

        # 2. فحص هل كان قادماً من رابط طلب؟
        pending_driver = context.user_data.get('pending_order_driver')
        if pending_driver:
            context.user_data.update({
                'driver_to_order': pending_driver,
                'state': 'WAIT_TRIP_DETAILS',
                'pending_order_driver': None # تنظيف الذاكرة
            })
            await update.message.reply_text(
                f"✅ تم تسجيل رقمك: `{phone}`\n\nالآن، **اكتب تفاصيل مشوارك** لإرسالها للكابتن:",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ إلغاء الطلب")]], resize_keyboard=True)
            )
        else:
            # دخول عادي للمنيو
            context.user_data['state'] = None
            await update.message.reply_text(
                "✅ تم التسجيل بنجاح!",
                reply_markup=get_main_kb('rider', True)
            )
        return


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
    if update.message.chat.type == "private":
        
        # 1. تجهيز الرسالة للأدمن
        admin_text = (
            f"📩 **رسالة واردة (دعم فني)**\n"
            f"👤 الاسم: {user.full_name}\n"
            f"🆔 ID: `{user_id}`\n"
            f"🔗 المعرف: @{user.username if user.username else 'لا يوجد'}\n"
            f"📝 النص: {text}\n"
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

        # 3. الإرسال لكل المشرفين
        for aid in ADMIN_IDS:
            try:
                # إرسال بطاقة المعلومات
                await context.bot.send_message(chat_id=aid, text=admin_text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
                # تحويل رسالة المستخدم الأصلية (مفيد إذا كانت صورة أو فيديو)
                await context.bot.copy_message(chat_id=aid, from_chat_id=user_id, message_id=update.message.message_id)
            except: pass

        # 4. حفظ في السجل
        # تأكد من أن دالة save_chat_log موجودة ومستوردة
        save_chat_log(user_id, ADMIN_IDS[0], text or "[ملف/موقع]", "support_msg")

        # 5. إشعار المستخدم (مرة واحدة)
        # لتجنب التكرار، نرسل التأكيد فقط إذا لم يكن في حالة تواصل مسبق
        # (اختياري: يمكنك إزالة هذا السطر إذا كنت تراه مزعجاً)
        await update.message.reply_text("📨 تم استلام رسالتك وتحويلها لفريق الدعم.")

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

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    location = update.message.location
    state = context.user_data.get('state')

    # --- الخطوة 1: فحص المحادثة النشطة (الأولوية القصوى) ---
    # إذا كان المستخدم في محادثة، نرسل الموقع للطرف الآخر فقط وننهي الدالة
    partner_id = get_chat_partner(user_id)
    if partner_id:
        try:
            # توجيه الموقع للطرف الآخر
            await context.bot.copy_message(
                chat_id=partner_id,
                from_chat_id=user_id,
                message_id=update.message.message_id
            )
            # اختياري: حفظ في السجلات
            msg_content = f"📍 موقع: {location.latitude}, {location.longitude}"
            conn = get_db_connection()
            if conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO chat_logs (sender_id, receiver_id, message_content, msg_type) VALUES (%s, %s, %s, %s)",
                                (int(user_id), int(partner_id), msg_content, "location"))
                    conn.commit()
                conn.close()
            return # إنهاء الدالة هنا يمنع تكرار طلب الرحلة
        except Exception as e:
            print(f"❌ فشل تمرير الموقع للمشترك: {e}")

    # --- الخطوة 2: تحديث الإحداثيات العامة ---
    context.user_data['lat'] = location.latitude
    context.user_data['lon'] = location.longitude
    threading.Thread(target=update_db_location, args=(user_id, location.latitude, location.longitude)).start()

    # --- الخطوة 3: جلب بيانات المستخدم ---
    await sync_all_users() 
    user_data = USER_CACHE.get(user_id, {})
    user_role = user_data.get('role', 'rider')
    is_verified = user_data.get('is_verified', False)

    # --- الخطوة 4: معالجة طلب الرحلة (في حال عدم وجود محادثة) ---
    # --- الخطوة 4: معالجة طلب الرحلة ---
    if state == 'WAIT_LOCATION_FOR_ORDER' and user_role == 'rider':
        processing_msg = await update.message.reply_text("📡 جاري البحث عن أقرب كباتن (نطاق 5 كم)...")
        
        # استدعاء الدالة الجديدة التي تعيد القائمة
        drivers_list = await broadcast_general_order(update, context)
        
        if drivers_list:
            keyboard = []
            current_row = []
            
            # عرض السائقين الفعليين الذين استلموا الطلب
            for d in drivers_list[:10]: # حد أقصى 10
                d_name = d.get('name', 'كابتن')
                d_id = d.get('user_id')
                
                # زر للتواصل المباشر مع الكابتن
                button = InlineKeyboardButton(
                    text=f"📞 {d_name}", 
                    url=f"https://t.me/{context.bot.username}?start=order_{d_id}"
                )
                current_row.append(button)
                
                if len(current_row) == 2:
                    keyboard.append(current_row)
                    current_row = []
            
            if current_row:
                keyboard.append(current_row)

            await processing_msg.edit_text(
                f"✅ تم إرسال طلبك إلى **{len(drivers_list)}** كابتن بالقرب منك.\n\n"
                "يمكنك انتظار قبول أحدهم، أو التواصل معهم مباشرة عبر الأزرار:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        else:
            await processing_msg.edit_text(
                "⚠️ لم يتم العثور على كباتن في نطاق 5 كم حالياً.",
                reply_markup=get_main_kb("rider", True)
            )
        
        context.user_data['state'] = None


    # --- الخطوة 5: تحديث الموقع العادي ---
    else:
        await update.message.reply_text(
            "📍 تم تحديث موقعك الجغرافي بنجاح.",
            reply_markup=get_main_kb(user_role, is_verified)
        )



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
            "📝 يرجى كتابة **تفاصيل مشوارك** الآن (من وين لوين؟):",
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

async def group_order_scanner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    text = update.message.text
    # 1. تنظيف النص (يجب أن تكون دالة normalize_text موجودة في ملفك)
    msg_clean = normalize_text(text)

    # 2. تعريف قوائم الكلمات (يجب تعريفها في البداية لتجنب الأخطاء)
    REQUEST_KEYWORDS = [
        "توصيل", "طلب", "طلبات", "غرض", "اغراض", "مقاضي", "مشوار", "مشاوير", "روحه", "جيه", "توصيلة", "توصيله", 
        "كابتن", "سواق", "سائق", "سيارة", "سياره", "ابي", "ابغى", "محتاج", "في احد", "وديني", "استلام", 
        "مطعم", "اكل", "وجبة", "عشاء", "غداء", "فطور", "سحور", "حلويات", "كوفي", "قهوة", "عصير", "البيك", 
        "تموينات", "بقالة", "خضار", "هدية", "ورد", "باقة", "كيك", "شحنه", "طرد", "صيدلية", "علاج", "دواء",
        "دوام", "عمل", "جامعة", "كلية", "مدرسة", "معهد", "الحرم", "المطار", "مستشفى", "موعد", "سوق", "بنات"
    ]

    SPAM_KEYWORDS = [
        "شهري", "حل واجبات", "راتب", "استثمار", "ربح سريع", "تداول", 
        "منصة استثمار", "تسديد ديون", "قرض", "تمويل شخصي", "زيادة متابعين", 
        "بيع حسابات", "عملات رقمية", "بوت ربح", "هدية مالية", "مسابقة كبرى"
    ]

    # 3. نظام الحماية من الاحتيال (فحص فوري)
    if any(k in msg_clean for k in SPAM_KEYWORDS):
        contact_url = f"tg://user?id={user.id}"
        if user.username: contact_url = f"https://t.me/{user.username}"
        
        admin_report = (f"⚠️ **رسالة محجوبة:**\n👤 العميل: {user.full_name}\n🆔 الآيدي: `{user.id}`\n💬 النص: {text}")
        admin_kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬 مراسلة العميل", url=contact_url)]])

        for admin_id in ADMIN_IDS:
            try: await context.bot.send_message(chat_id=admin_id, text=admin_report, reply_markup=admin_kb, parse_mode="Markdown")
            except: pass
        
        try: await update.message.delete()
        except: pass
        return

    # 4. البحث عن الحي في الرسالة
    found_dist = None
    districts_list = CITIES_DISTRICTS.get("المدينة المنورة", [])
    for dist in sorted(districts_list, key=len, reverse=True):
        if normalize_text(dist) in msg_clean:
            found_dist = dist
            break

    # 5. التحقق من الحالات (أدمن، طلب، حي)
    is_admin_run = (msg_clean.strip() == "رن" and user.id in ADMIN_IDS)
    has_request = any(k in msg_clean for k in REQUEST_KEYWORDS)

    # الحالة أ: أمر "رن" أو وجود "طلب" بدون ذكر "الحي"
    if is_admin_run or (has_request and not found_dist):
        welcome_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🚕 تسجيل كابتن", url=f"https://t.me/{context.bot.username}?start=driver_reg"),
                InlineKeyboardButton("📱 طلب مشوار", url=f"https://t.me/{context.bot.username}?start=order_general")
            ],
            [InlineKeyboardButton("📋 المندوبين المعتمدين", callback_data="show_all_delivery")],
            [InlineKeyboardButton("🛍️ تعليمات المتاجر", callback_data="help_delivery_orders")]
        ])
        
        await update.message.reply_text(
            f"🌴 **حياك الله في {context.bot.name}** 🌴\n\n"
            f"يا {user.first_name}، لخدمتك بشكل أسرع:\n"
            f"✅ اكتب طلبك مع **اسم الحي** في رسالة واحدة.\n"
            f"أو اختر من القائمة التالية:", 
            reply_markup=welcome_kb,
            parse_mode="Markdown"
        )
        
        if is_admin_run:
            try: await update.message.delete()
            except: pass
        return

    # الحالة ب: وجود "طلب" مع "الحي" -> إظهار الكباتن
     # 5. إذا وجد الحي والطلب (عرض جميع السائقين)
       # 3. تعديل المنطق: إذا وجد الحي، نعرض السائقين فوراً
    if found_dist:
        await sync_all_users()
        # جلب جميع السائقين في هذا الحي
        matched_drivers = [d for d in CACHED_DRIVERS if found_dist in str(d.get('districts', ''))]

        if matched_drivers:
            
            random.shuffle(matched_drivers)
            
            keyboard = []
            current_row = []
            for d in matched_drivers:
                button = InlineKeyboardButton(f"📞 {d['name']}", url=f"https://t.me/{context.bot.username}?start=order_{d['user_id']}")
                current_row.append(button)
                if len(current_row) == 2:
                    keyboard.append(current_row)
                    current_row = []
            if current_row: keyboard.append(current_row)
            
            await update.message.reply_text(
                f"✅ وجدنا **{len(matched_drivers)}** كابتن في حي **{found_dist}**:", 
                reply_markup=InlineKeyboardMarkup(keyboard), 
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            # نرد بعدم التوفر فقط إذا كان الكلام أصلاً يحتوي على "كلمة طلب"
            # لكي لا يحرج البوت نفسه بالرد "لا يوجد" على شخص ذكر اسم الحي صدفة
            if has_request:
                await update.message.reply_text(f"📍 حي {found_dist}: لا يوجد كباتن متاحين حالياً.")
        return # إنهاء المعالجة هنا

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
    partner_id = get_chat_partner(user_id)
    
    # إذا لم يكن هناك طرف آخر (ليست رحلة نشطة)، اترك الرسالة تمر للمعالج التالي
    if not partner_id:
        return 
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
             await update.message.reply_text("⚠️ لم أتمكن من استخراج ID العضو. تأكد أنك ترد على رسالة البوت التي تحتوي على البيانات.")
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
    application.add_handler(MessageHandler(filters.Regex("^(❌ إنهاء المحادثة|🛑 تم إنهاء المحادثة.)$"), end_chat_command), group=0)


    application.add_handler(CallbackQueryHandler(handle_callbacks), group=0)
    application.add_handler(MessageHandler(filters.Regex("^❌"), start_command), group=0)


    # 2. أزرار القائمة الرئيسية (نصوص محددة) - Group 0
    # أضف السطر هنا

# أضف هذا السطر لمراقبة كلمة "احياء" في المجموعات
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex("^(احياء|الأحياء|الأحياء المتاحة)$"), group_districts_handler), group=0)


    # هذا السطر سيلتقط أي عضو جديد يدخل المجموعة
    


    # ---------------------------------------------------------
    # المجموعة 1: ردود الأدمن والنظام (قبل الدردشة العامة)
    # ---------------------------------------------------------
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.REPLY & filters.User(ADMIN_IDS), 
        admin_reply_handler
    ), group=1)
    # يوضع في مجموعة (group) ليعمل مع بقية الأوامر
    
    
    
    
    

    # ---------------------------------------------------------
    # المجموعة 2: إدارة الحالات (التسجيل والقوائم - Global)
    # ---------------------------------------------------------
    # ملاحظة: تم رفع الـ global_handler قبل الـ relay لضمان عمل التسجيل
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (filters.TEXT | filters.PHOTO | filters.LOCATION) & ~filters.COMMAND, 
        global_handler
    ), group=2)


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