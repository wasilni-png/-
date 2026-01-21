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
BOT_TOKEN = "8498451295:AAGt1R7THllSjYtEe5hvIEPnPhRkS_iBcnU"
# آيدي المشرفين
ADMIN_IDS = [8563113166, 7996171713, 7580027135, 5027690233]

# الكلمات المفتاحية للبحث في المجموعات
KEYWORDS = ["مشوار", "توصيل", "سائق", "كابتن", "سيارة", "وينك", "متاح", "مطلوب", "ابي", "بغيت"]
# --- 1. إعدادات الأحياء الذكية ---
# --- 1. إعدادات الأحياء الذكية (المدينة المنورة) ---
CITIES_DISTRICTS = {
    "المدينة المنورة": [
        "الإسكان", "البحر", "البدراني", "الجرف", "الحزام", "الحمراء", "الخالدية", 
        "الدويخله", "الرانوناء", "الشروق", "الشرق", "العاقول", "العريض", "العزيزية", 
        "العنابس", "القبلتين", "الملك فهد", "المطار", "المغيسله", "الهجرة", "باقدو", 
        "بني حارثة", "حديقة الملك فهد", "سيد الشهداء", "شوران", "قباء", "مهزور"
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

async def send_fancy_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # التأكد من أن التحديث يحتوي على رسالة وأعضاء جدد
    if not update.message or not update.message.new_chat_members:
        return

    chat_id = update.effective_chat.id
    bot_username = context.bot.username

    # روابط الدخول العميق (توجه المستخدم لـ start_command مع المعامل المناسب)
    url_rider = f"https://t.me/{bot_username}?start=reg_rider"
    url_driver = f"https://t.me/{bot_username}?start=reg_driver"

    # رابط الفيديو (يفضل استخدام File ID إذا توفر، أو رابط قناة عامة)
    video_url = "https://t.me/mishwarii/4436" 

    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            continue # تجاهل الترحيب بالبوت نفسه

        welcome_text = (
            f"🚀 **أهلاً بك يا {member.first_name} في منصة مشواري!**\n\n"
            "المنصة الأسهل لربط الكباتن بالركاب.\n"
            "👇 **اختر دورك الآن للبدء فوراً:**"
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👤 دخول كراكب", url=url_rider),
                InlineKeyboardButton("🚗 دخول ككابتن", url=url_driver)
            ],
            [InlineKeyboardButton("📜 قناة التعليمات", url="https://t.me/mishwarii")]
        ])

        try:
            # محاولة إرسال الفيديو
            await context.bot.send_video(
                chat_id=chat_id,
                video=video_url,
                caption=welcome_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            # البديل النصي في حال فشل الفيديو
            await context.bot.send_message(
                chat_id=chat_id,
                text=welcome_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )

async def welcome_on_first_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # نتحقق أن الرسالة من جروب وليست خاص
    if not update.effective_chat or update.effective_chat.type == "private":
        return

    user_id = update.effective_user.id
    user_name = update.effective_user.first_name

    # فحص هل تم الترحيب بالعضو مسبقاً في هذه الجلسة؟ 
    # (نستخدم context.user_data لضمان عدم تكرار الرسالة لكل رسالة يكتبها)
    if context.user_data.get('welcomed'):
        return

    # إعداد الروابط والأزرار
    bot_username = context.bot.username
    url_rider = f"https://t.me/{bot_username}?start=reg_rider"
    url_driver = f"https://t.me/{bot_username}?start=reg_driver"
    video_url = "https://t.me/mishwarii/4436" # رابط الفيديو الخاص بك

    welcome_text = (
        f"🚀 **أهلاً بك يا {user_name} في منصة مشواري!**\n\n"
        "يبدو أنك جديد هنا، المنصة الأسهل لربط الكباتن بالركاب.\n"
        "👇 **اختر دورك الآن للبدء:**"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👤 دخول كراكب", url=url_rider),
            InlineKeyboardButton("🚗 دخول ككابتن", url=url_driver)
        ],
        [InlineKeyboardButton("📜 قناة التعليمات", url="https://t.me/mishwarii")]
    ])

    try:
        # إرسال الترحيب كرد (Reply) على رسالته الأولى
        await update.message.reply_video(
            video=video_url,
            caption=welcome_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        # تسجيل أنه تم الترحيب به حتى لا يزعجه البوت مرة أخرى
        context.user_data['welcomed'] = True
        
    except Exception as e:
        print(f"Error in welcoming: {e}")




async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name

    # 1. تنظيف الذاكرة لضمان بداية جديدة
    context.user_data.clear()

    # 2. فحص المعاملات القادمة من الروابط (Deep Linking)
    if context.args:
        arg_value = context.args[0]

        # ---------------------------------------------------------
        # (أ) حالة التسجيل المباشر كراكب (من زر الترحيب)
        # ---------------------------------------------------------
        if arg_value == "reg_rider":
            # 1. تسجيل المستخدم في قاعدة البيانات فوراً
            await auto_register_rider(update) 
            
            # 2. إرسال رسالة ترحيب وعرض القائمة الرئيسية
            await update.message.reply_text(
                f"🎉 **حياك الله يا {first_name}!**\n"
                "تم تسجيل دخولك كراكب بنجاح.\nيمكنك الآن طلب المشاوير بسهولة.",
                reply_markup=get_main_kb('rider', True), # قائمة الراكب
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # ---------------------------------------------------------
        # (ب) حالة التسجيل ككابتن (من زر الترحيب)
        # ---------------------------------------------------------
        elif arg_value == "reg_driver":
            # 1. تهيئة الذاكرة لاستقبال بيانات الكابتن
            context.user_data['reg_role'] = 'driver'
            context.user_data['state'] = 'WAIT_NAME' # تحويل الحالة لانتظار الاسم

            # 2. طلب الاسم الأول
            msg = (
                "🚗 **أهلاً بك يا كابتن في فريقنا!**\n\n"
                "لإتمام تسجيلك، نحتاج لبعض البيانات البسيطة.\n"
                "📝 **يرجى كتابة اسمك الثلاثي الآن:**"
            )
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        # ---------------------------------------------------------
        # (ج) حالة طلب مشوار محدد (order_ID)
        # ---------------------------------------------------------
        elif arg_value.startswith("order_") and arg_value != "order_general":
            try:
                driver_id = arg_value.split("_")[1]
                
                # تسجيل الراكب تلقائياً إذا كان جديداً
                await sync_all_users()
                if user_id not in USER_CACHE:
                    await auto_register_rider(update)

                context.user_data.update({
                    'driver_to_order': driver_id,
                    'state': 'WAIT_TRIP_DETAILS'
                })

                await update.message.reply_text(
                    f"👋 أهلاً بك يا {first_name}\n"
                    "📝 **يرجى كتابة تفاصيل مشوارك الآن:**\n"
                    "(مثال: من حي الخالدية إلى الراشد مول، الساعة 8)",
                    reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ إلغاء الطلب")]], resize_keyboard=True),
                    parse_mode=ParseMode.MARKDOWN
                )
                return 
            except Exception as e:
                print(f"Error: {e}")

        # ---------------------------------------------------------
        # (د) حالة الطلب العام (order_general)
        # ---------------------------------------------------------
        elif arg_value == "order_general":
            await sync_all_users()
            if user_id not in USER_CACHE:
                await auto_register_rider(update)

            context.user_data['state'] = 'WAIT_GENERAL_DETAILS'
            await update.message.reply_text(
                "🌍 **بدء طلب مشوار عام (عبر GPS)**\n\n"
                "📝 اكتب تفاصيل مشوارك الآن (الوجهة والوقت):",
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
        # عرض أزرار التسجيل اليدوي (للمستخدم الذي يبحث عن البوت يدوياً)
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
    await query.answer()
    data = query.data

    # --- 1. قسم إدارة المدن والأحياء ---
    

    # --- 2. قسم تسجيل الحساب الجديد (راكب/سائق) ---
    if data in ["reg_rider", "reg_driver"]:
        role = "rider" if data == "reg_rider" else "driver"
        context.user_data['reg_role'] = role

        if role == "rider":
            # تسجيل الراكب فوراً
            first_name = user.first_name or "راكب"
            last_name = user.last_name or ""
            full_name = f"{first_name} {last_name}".strip()
            
            context.user_data['reg_phone'] = "0000000000" 
            
            await query.edit_message_text(text="⏳ جاري إنشاء حسابك كراكب...")
            await complete_registration(update, context, full_name)
        
        elif role == "driver":
            # تسجيل الكابتن (يحتاج خطوات إضافية)
            context.user_data['state'] = 'WAIT_NAME'
            msg = f"✅ اخترت: **كابتن (سائق)**\n\n📝 يرجى كتابة **اسمك الثلاثي** الآن للتوثيق:"
            await query.edit_message_text(text=msg, parse_mode=ParseMode.MARKDOWN)
        
        return # إنهاء المعالجة بعد التسجيل
     
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

        # --- حالة الكابتن (يرسل إشعار للأدمن) ---
        if role == 'driver':
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ **أبشرك تم استلام طلبك يا كابتن {name}**\n\nحسابك الحين تحت المراجعة، وأول ما يتفعل بيجيك إشعار. خلك قريب!",
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
    # 1. التحقق المبدئي: هل يوجد رسالة؟
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
    if state:
        # --- أ) خطوات التسجيل ---
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

            price = text # نحفظه كنص أو نحوله لـ float حسب رغبتك
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
            context.user_data['search_district'] = text # أو تفاصيل المشوار
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
            # نغير الحالة لانتظار الموقع، وسيتكفل location_handler بالباقي
            context.user_data['state'] = 'WAIT_LOCATION_FOR_ORDER' 
            return

        # --- د) إعدادات السائقين والبحث ---
        if state == 'WAIT_DISTRICTS':
            # تحديث الأحياء في قاعدة البيانات
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET districts = %s WHERE user_id = %s", (text, user_id))
                conn.commit()
            conn.close() # لا تنس إغلاق الاتصال
            
            await sync_all_users() # تحديث الكاش
            await update.message.reply_text("✅ تم تحديث مناطق عملك بنجاح.")
            context.user_data['state'] = None
            return

        if state == 'WAIT_ELITE_DISTRICT':
            # البحث عن كابتن في حي معين
            found = []
            await sync_all_users() # تأكيد التحديث
            
            for d in CACHED_DRIVERS:
                # نفترض أن districts مخزنة كنص مفصول بفواصل
                if d.get('districts') and text in d['districts']:
                    found.append(d)

            if not found:
                await update.message.reply_text(f"❌ لا يوجد كابتن مسجل في حي '{text}' حالياً.")
            else:
                await update.message.reply_text(f"✅ وجدنا {len(found)} كابتن:")
                for d in found:
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"📞 طلب {d['name']}", callback_data=f"book_{d['user_id']}_{text}") ]])
                    await update.message.reply_text(f"👤 {d['name']}\n🚗 {d.get('car_info', 'غير محدد')}", reply_markup=kb)
            
            context.user_data['state'] = None
            return

        # --- هـ) تواصل الإدارة الصريح ---
        if state == 'WAIT_ADMIN_MESSAGE':
            if text == "❌ إلغاء المراسلة":
                context.user_data['state'] = None
                await update.message.reply_text("تم الإلغاء.", reply_markup=get_main_kb(context.user_data.get('role', 'rider')))
                return
            # إذا لم يلغِ، نتركه يمر للجزء الأخير (Support Msg) ليتم إرساله
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
    if state == 'WAIT_LOCATION_FOR_ORDER' and user_role == 'rider':
        processing_msg = await update.message.reply_text("📡 جاري البحث عن كباتن بالقرب منك...")
        count = await broadcast_general_order(update, context)
        
        if count > 0:
            await processing_msg.edit_text(
                f"✅ تم إرسال طلبك إلى **{count}** كابتن بنجاح.",
                reply_markup=get_main_kb("rider", True)
            )
        else:
            await processing_msg.edit_text(
                "⚠️ نعتذر، لا يوجد كباتن متاحين في نطاقك حالياً.",
                reply_markup=get_main_kb("rider", True)
            )
        # تصفير الحالة ضروري لمنع التكرار
        context.user_data['state'] = None

    # --- الخطوة 5: تحديث الموقع العادي ---
    else:
        await update.message.reply_text(
            "📍 تم تحديث موقعك الجغرافي بنجاح.",
            reply_markup=get_main_kb(user_role, is_verified)
        )



# ==================== دالة عرض الأحياء (محدثة) ====================

async def show_districts_by_city(update: Update, context: ContextTypes.DEFAULT_TYPE, city_name: str):
    query = update.callback_query
    user_id = update.effective_user.id
    
    # [هام] حفظ المدينة الحالية ليعرف البوت أين يعود بعد الضغط على حي
    context.user_data['current_managing_city'] = city_name

    # 1. جلب أحياء المستخدم الحالية من القاعدة
    conn = get_db_connection()
    current_districts = []
    if conn:
        with conn.cursor() as cur:
            cur.execute("SELECT districts FROM users WHERE user_id = %s", (user_id,))
            res = cur.fetchone()
            if res and res[0]:
                # تنظيف النص وتحويله لقائمة
                current_districts = [d.strip() for d in res[0].replace("،", ",").split(",") if d.strip()]
        conn.close()

    # 2. جلب أحياء المدينة المختارة
    all_districts = CITIES_DISTRICTS.get(city_name, [])
    
    if not all_districts:
        try: await query.answer(f"⚠️ لا توجد أحياء مسجلة لمدينة {city_name}")
        except: pass
        return

    keyboard = []
    # ترتيب الأزرار: زرين في كل صف
    for i in range(0, len(all_districts), 2):
        row = []
        for j in range(2):
            if i + j < len(all_districts):
                dist_name = all_districts[i + j]
                # إضافة علامة الصح إذا كان الحي مختاراً
                status = "✅ " if dist_name in current_districts else "⬜ "
                row.append(InlineKeyboardButton(f"{status}{dist_name}", callback_data=f"toggle_dist_{dist_name}"))
        keyboard.append(row)
    
    # أزرار التحكم السفلية
    keyboard.append([InlineKeyboardButton("🔙 العودة للمدن", callback_data="back_to_cities")])
    keyboard.append([InlineKeyboardButton("🏁 حفظ وإغلاق", callback_data="save_districts")])

    text = f"🏙 **أحياء {city_name}:**\nاختر الأحياء التي تعمل بها، ثم اضغط حفظ."
    
    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    except Exception:
        # لتجنب الخطأ إذا ضغط المستخدم الزر ولم يتغير شيء في الرسالة
        pass


# ==================== معالج الأزرار الشامل (محدث) ====================

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id

    # محاولة إغلاق مؤشر التحميل لتجنب التعليق
    try: await query.answer()
    except: pass

    # ===============================================================
    # [A] قسم الكابتن: إعدادات المناطق (تفعيل/إلغاء)
    # ===============================================================

    if data.startswith("selectcity_"):
        # عند اختيار مدينة من قائمة الإعدادات
        city_name = data.split("_")[1]
        await show_districts_by_city(update, context, city_name)
        return

    elif data == "back_to_cities":
        # العودة لقائمة المدن الرئيسية
        await districts_settings_view(update, context)
        return

    elif data.startswith("toggle_dist_"):
        # عند الضغط على اسم حي (تفعيل/إلغاء)
        dist_name = data.replace("toggle_dist_", "")
        
        # استرجاع المدينة التي كان يتصفحها الكابتن
        city_name = context.user_data.get('current_managing_city')
        
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                # 1. جلب القائمة الحالية
                cur.execute("SELECT districts FROM users WHERE user_id = %s", (user_id,))
                res = cur.fetchone()
                current_list = []
                if res and res[0]:
                    current_list = [x.strip() for x in res[0].replace("،", ",").split(",") if x.strip()]
                
                # 2. التبديل (إضافة أو حذف)
                if dist_name in current_list:
                    current_list.remove(dist_name)
                else:
                    current_list.append(dist_name)
                
                # 3. الحفظ في القاعدة
                new_districts_str = "، ".join(current_list)
                cur.execute("UPDATE users SET districts = %s WHERE user_id = %s", (new_districts_str, user_id))
                conn.commit()
            conn.close()

            # 4. تحديث الكاش وإعادة عرض القائمة
            await sync_all_users(force=True)
            
            if city_name:
                await show_districts_by_city(update, context, city_name)
            else:
                # لو فقدنا السياق (نادر جداً)، نعيده لاختيار المدينة
                await districts_settings_view(update, context)
        return

    elif data == "save_districts":
        # الحفظ النهائي
        await query.edit_message_text(
            "✅ **تم حفظ مناطق عملك بنجاح!**\nسيصلك إشعار فور طلب أي مشوار في هذه الأحياء.\n\nشكراً لك يا كابتن.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # ===============================================================
    # [B] قسم الراكب: البحث عن كابتن (النخبة)
    # ===============================================================

        elif data == "order_by_district":
        districts = CITIES_DISTRICTS.get("المدينة المنورة", [])
        keyboard = []
        for i in range(0, len(districts), 2):
            row = [InlineKeyboardButton(districts[i], callback_data=f"searchdist_المدينة المنورة_{districts[i]}")]
            if i + 1 < len(districts):
                row.append(InlineKeyboardButton(districts[i+1], callback_data=f"searchdist_المدينة المنورة_{districts[i+1]}"))
            keyboard.append(row)
        
        await query.edit_message_text(
            "📍 **أحياء المدينة المنورة:**\nاختر الحي للبحث عن كباتن متوفرين حالياً:", 
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        return


    elif data.startswith("searchcity_"):
        # عرض أحياء المدينة للراكب
        city_name = data.split("_")[1]
        districts = CITIES_DISTRICTS.get(city_name, [])
        
        keyboard = []
        for i in range(0, len(districts), 2):
            row = [InlineKeyboardButton(districts[i], callback_data=f"searchdist_{city_name}_{districts[i]}")]
            if i + 1 < len(districts):
                row.append(InlineKeyboardButton(districts[i+1], callback_data=f"searchdist_{city_name}_{districts[i+1]}"))
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="order_by_district")])
        await query.edit_message_text(f"📍 أحياء {city_name}:\nاختر الحي:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    elif data.startswith("searchdist_"):
        # تنفيذ البحث
        parts = data.split("_")
        city_name = parts[1]
        dist_name = parts[2] # اسم الحي المختار
        
        await sync_all_users() # تحديث البيانات للتأكد
        
        matched_drivers = []
        # دالة تنظيف للنصوص (إزالة التاء المربوطة والهمزات)
        def clean_text(text):
            return text.replace("ة", "ه").replace("أ", "ا").replace("إ", "ا")

        target_dist_clean = clean_text(dist_name)

        for d in CACHED_DRIVERS:
            if d.get('districts'):
                # تحويل قائمة أحياء الكابتن وتنظيفها
                d_list = [clean_text(x.strip()) for x in d['districts'].replace("،", ",").split(",")]
                if target_dist_clean in d_list:
                    matched_drivers.append(d)

        if not matched_drivers:
            gps_url = f"https://t.me/{context.bot.username}?start=order_general"
            kb = [
                [InlineKeyboardButton("🌍 اطلب أقرب كابتن (GPS)", url=gps_url)],
                [InlineKeyboardButton("🔙 اختيار حي آخر", callback_data=f"searchcity_{city_name}")]
            ]
            await query.edit_message_text(
                f"⚠️ **نعتذر منك..**\nلا يوجد كباتن مسجلين في حي ({dist_name}) حالياً.\n\nيمكنك تجربة الطلب عبر الموقع الجغرافي:",
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            keyboard = []
            for d in matched_drivers[:6]: # عرض 6 كباتن كحد أقصى
                keyboard.append([InlineKeyboardButton(
                    f"🚖 {d['name']} ({d.get('car_info', 'سيارة')})", 
                    callback_data=f"book_{d['user_id']}_{dist_name}"
                )])
            
            keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"searchcity_{city_name}")])
            
            await query.edit_message_text(
                f"✅ **كباتن متوفرين في {dist_name}:**\nاضغط على اسم الكابتن لطلب مشوار:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
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
        

    # --- منطق تبديل الأحياء ---
        # --- 1. معالجة الضغط على اسم الحي (تبديل الحالة) ---
    if data.startswith("toggle_dist_"):
        dist_name = data.replace("toggle_dist_", "")
        user_id = update.effective_user.id
        
        conn = get_db_connection()
        if not conn: return
        
        try:
            with conn.cursor() as cur:
                # جلب الأحياء الحالية مباشرة من القاعدة
                cur.execute("SELECT districts FROM users WHERE user_id = %s", (user_id,))
                res = cur.fetchone()
                
                # تحويل النص إلى قائمة
                current_list = []
                if res and res[0]:
                    current_list = [x.strip() for x in res[0].replace("،", ",").split(",") if x.strip()]
                
                # تبديل الحالة: إذا موجود احذفه، إذا مو موجود ضيفه
                if dist_name in current_list:
                    current_list.remove(dist_name)
                else:
                    current_list.append(dist_name)
                
                # تحويل القائمة لنص وتحديث القاعدة
                new_districts_str = "، ".join(current_list)
                cur.execute("UPDATE users SET districts = %s WHERE user_id = %s", (new_districts_str, user_id))
                conn.commit()

            # 🔄 تحديث الكاش المحلي فوراً لضمان عمل البوت في القروبات بناءً على الأحياء الجديدة
            await sync_all_users()

            # 2. إعادة بناء لوحة المفاتيح فوراً لعرض التغيير للمستخدم
            all_districts = CITIES_DISTRICTS.get("المدينة المنورة", [])
            keyboard = []
            for i in range(0, len(all_districts), 2):
                row = []
                for j in range(2):
                    if i + j < len(all_districts):
                        name = all_districts[i + j]
                        status = "✅ " if name in current_list else "⬜ "
                        row.append(InlineKeyboardButton(f"{status}{name}", callback_data=f"toggle_dist_{name}"))
                keyboard.append(row)
            
            keyboard.append([InlineKeyboardButton("🏁 حفظ وإغلاق", callback_data="save_districts")])
            
            # تحديث الرسالة الحالية بالأزرار الجديدة
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

        except Exception as e:
            print(f"❌ خطأ في تحديث الأحياء: {e}")
            await query.answer("⚠️ حدث خطأ أثناء التحديث")
        finally:
            conn.close()
        return

    # --- 2. معالجة زر الحفظ النهائي ---
    elif data == "save_districts":
        await query.answer("✅ تم حفظ إعداداتك بنجاح")
        await query.edit_message_text(
            "🚀 **تم تحديث نطاق عملك!**\n\nستصلك تنبيهات فورية في الخاص عند طلب أي مشوار في الأحياء التي اخترتها.\nشكراً لك يا كابتن.",
            parse_mode=ParseMode.MARKDOWN
        )
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
        # 1. البحث في جميع المدن والأحياء بدلاً من مدينة واحدة
    found_dist = None
    target_city = None # سنستخدم هذا لنعرف الحي تابع لأي مدينة

    for city_name, districts_list in CITIES_DISTRICTS.items():
        for dist in districts_list:
            # تنظيف اسم الحي للبحث (تحويل التاء المربوطة والهمزات)
            clean_dist = dist.replace("ة", "ه").replace("أ", "ا").replace("إ", "ا")
            if clean_dist in msg_clean:
                found_dist = dist
                target_city = city_name
                break
        if found_dist: break # إذا وجد الحي في مدينة معينة يتوقف عن البحث في باقي المدن

    # 4. إذا لم يجد اسم الحي -> يعرض أزرار المدن أولاً (لأن القائمة أصبحت كبيرة)
    if not found_dist:
        keyboard = []
        cities = list(CITIES_DISTRICTS.keys())
        for i in range(0, len(cities), 2):
            row = [InlineKeyboardButton(cities[i], callback_data=f"selectcity_search_{cities[i]}")]
            if i + 1 < len(cities):
                row.append(InlineKeyboardButton(cities[i+1], callback_data=f"selectcity_search_{cities[i+1]}"))
            keyboard.append(row)
        
        await update.message.reply_text(
            f"يا هلا بك يا {user.first_name} ✨\nيرجى اختيار مدينتك أولاً لتحديد الحي والعثور على كباتن:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # 5. إذا وجد الحي -> يبحث عن الكباتن المسجلين في هذا الحي
    await sync_all_users()
    matched_drivers = []
    
    # تحويل اسم الحي المكتشف لصيغة المقارنة (تنظيف التاء المربوطة)
    clean_found_dist = found_dist.replace("ة", "ه")

    for d in CACHED_DRIVERS:
        if d.get('districts'):
            # تنظيف قائمة أحياء الكابتن المخزنة في قاعدة البيانات للمطابقة
            d_dists = [x.strip().replace("ة", "ه") for x in d['districts'].replace("،", ",").split(",")]
            if clean_found_dist in d_dists:
                matched_drivers.append(d)

    # 6. عرض النتائج
    if matched_drivers:
        keyboard = []
        for d in matched_drivers[:6]:
            driver_id = d['user_id']
            driver_name = d['name']
            deep_link = f"https://t.me/{context.bot.username}?start=order_{driver_id}"
            keyboard.append([InlineKeyboardButton(f"🚖 اطلب الكابتن {driver_name}", url=deep_link)])

        await update.message.reply_text(
            f"✅ **أبشر! وجدنا كباتن متاحين في {found_dist} ({target_city}):**\n\n"
            "اضغط على الكابتن المناسب لك لإرسال تفاصيل مشوارك له مباشرة:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

        # 7. تنبيه الكباتن
        for d in matched_drivers:
            try:
                await context.bot.send_message(
                    chat_id=d['user_id'],
                    text=f"🔔 **تنبيه:** يوجد طلب جديد في حي **{found_dist}** بمدينة **{target_city}**. كن مستعداً!"
                )
            except: pass
    else:
        # كود عدم توفر كباتن (يبقى كما هو مع إضافة اسم المدينة)
        bot_username = context.bot.username
        search_link = f"https://t.me/{bot_username}?start=order_general"
        keyboard = [[InlineKeyboardButton("🌍 ابحث عن أقرب كابتن (GPS)", url=search_link)]]
        
        await update.message.reply_text(
            f"📍 حي {found_dist} ({target_city}): يرجى ارسال الطلب عبر البوت لارساله إلى الكباتن القريبين منك .\n\n"
            "💡 يمكنك البحث عن أقرب كابتن متاح حولك الآن بواسطة GPS:",
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
    application.add_handler(CommandHandler("end", end_chat_command), group=0)
    application.add_handler(CommandHandler("cash", admin_cash), group=0)
    application.add_handler(CommandHandler("sub", admin_add_days), group=0)
    application.add_handler(CommandHandler("broadcast", admin_broadcast), group=0)
    application.add_handler(CommandHandler("logs", admin_get_logs), group=0)
    application.add_handler(CommandHandler("send", admin_send_to_user), group=0) # أضف هذا السطر
    
    application.add_handler(CallbackQueryHandler(register_callback, pattern="^reg_"), group=0)
    application.add_handler(CallbackQueryHandler(handle_callbacks), group=0)
    application.add_handler(MessageHandler(filters.Regex("^❌"), start_command), group=0)

    # هذا السطر سيلتقط أي عضو جديد يدخل المجموعة
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, send_fancy_welcome), group=0)


    # ---------------------------------------------------------
    # المجموعة 1: ردود الأدمن والنظام (قبل الدردشة العامة)
    # ---------------------------------------------------------
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.REPLY & filters.User(ADMIN_IDS), 
        admin_reply_handler
    ), group=1)
    # يوضع في مجموعة (group) ليعمل مع بقية الأوامر
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, welcome_on_first_message), group=0)

    
    
    
    

    # ---------------------------------------------------------
    # المجموعة 2: إدارة الحالات (التسجيل والقوائم - Global)
    # ---------------------------------------------------------
    # ملاحظة: تم رفع الـ global_handler قبل الـ relay لضمان عمل التسجيل
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, 
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
