#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import threading
import os
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
ADMIN_IDS = [8563113166, 7996171713]

# الكلمات المفتاحية للبحث في المجموعات
KEYWORDS = ["مشوار", "توصيل", "سائق", "كابتن", "سيارة", "وينك", "متاح", "مطلوب", "ابي", "بغيت"]
# --- 1. إعدادات الأحياء الذكية ---
# --- 1. إعدادات الأحياء الذكية (المدينة المنورة) ---
CITIES_DISTRICTS = {
    "المدينة المنورة": [
        "العزيزية", "البحر", "الدويخي", "بني حارثة", 
        "الجرف", "العريض", "سيد الشهداء", "الخالدية", 
        "الهجرة", "شوران", "الرانوناء", "القبلتين"
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
            [KeyboardButton("💰 محفظتي"), KeyboardButton("ℹ️ حالة اشتراكي")]
        ], resize_keyboard=True)

    # للراكب
    return ReplyKeyboardMarkup([
        [KeyboardButton("🚖 طلب رحلة"), KeyboardButton("📍 موقعي")],
        [KeyboardButton("💰 محفظتي")]
    ], resize_keyboard=True)

# ==================== 🤖 4. المعالجات (Handlers) ====================

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # التحقق من وجود أعضاء جدد في الرسالة
    for new_member in update.message.new_chat_members:
        # إذا كان العضو الجديد هو البوت نفسه، لا يرسل ترحيب (اختياري)
        if new_member.id == context.bot.id:
            continue

        first_name = new_member.first_name
        welcome_text = (
            f"يا هلا وغلا بك يا {first_name} في قروبنا! ✨\n\n"
            "نورتنا في منصة التوصيل الذكية 🚖\n"
            "إذا كنت **كابتن** وتبغى تسجل معنا، ارسل كلمة (تسجيل) في الخاص.\n"
            "إذا كنت **عميل** وتبغى مشوار، بس اكتب (مطلوب مشوار في حي ...) والشباب ما يقصرون معك."
        )

        # إضافة أزرار تحت رسالة الترحيب (اختياري)
        keyboard = [
            [InlineKeyboardButton("شرح طريقة الاستخدام 📖", url="https://t.me/mishwarii?start=help")],
            [InlineKeyboardButton("قناة التنبيهات 📢", url="https://t.me/mishwarii")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # إرسال الرسالة
        await update.message.reply_text(text=welcome_text, reply_markup=reply_markup)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    
    # التحقق من وجود بيانات طلب مشوار في الرابط (Deep Link)
    if context.args and context.args[0].startswith("order_"):
        parts = context.args[0].split("_")
        # parts[1] هو آيدي الكابتن، parts[2] هو اسم الحي
        driver_id = parts[1]
        dist_name = parts[2]
        
        # تخزين بيانات الطلب مؤقتاً في ذاكرة المستخدم
        context.user_data['driver_to_order'] = driver_id
        context.user_data['order_dist'] = dist_name
        
        # تغيير الحالة لانتظار التفاصيل
        context.user_data['state'] = 'WAIT_TRIP_DETAILS'
        
        await update.message.reply_text(
            f"👋 أهلاً بك يا {first_name}\n\n"
            f"📍 أنت تطلب كابتن في حي: **{dist_name}**\n\n"
            "📝 **يرجى كتابة تفاصيل مشوارك الآن:**\n"
            "(مثلاً: من شارع.. إلى حي.. الساعة.. عدد الركاب..)",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # محاولة الجلب من الكاش أولاً
    await sync_all_users()
    user = USER_CACHE.get(user_id)

    if user:
        role_name = "الكابتن" if user['role'] == 'driver' else "الراكب"
        status_icon = "✅ موثق" if user['is_verified'] else "⏳ قيد المراجعة"
        welcome_text = (
            f"👋 أهلاً بك مجدداً، {role_name} **{user['name']}**\n"
            f"🛡️ الحالة: {status_icon}\n"
            "─────────────────\n"
            "🚀 استخدم القائمة بالأسفل للتحكم."
        )
        await update.message.reply_text(welcome_text, reply_markup=get_main_kb(user['role'], user['is_verified']), parse_mode=ParseMode.MARKDOWN)
    else:
        welcome_new = (
            f"👋 مرحباً بك يا **{first_name}** في بوت التوصيل الذكي!\n\n"
            "يرجى اختيار نوع الحساب للتسجيل:"
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
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    role = context.user_data.get('reg_role')
    phone = context.user_data.get('reg_phone', '000000')
    car = context.user_data.get('reg_car', None)

    conn = get_db_connection()
    if not conn: return

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            is_verified = True if role == 'rider' else False

            cur.execute("""
                INSERT INTO users (user_id, chat_id, role, name, phone, car_info, is_verified)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    phone = EXCLUDED.phone,
                    car_info = EXCLUDED.car_info,
                    role = EXCLUDED.role,
                    is_verified = EXCLUDED.is_verified
                RETURNING *;
            """, (user_id, chat_id, role, name, phone, car, is_verified))
            conn.commit()

            # تحديث الذاكرة
            await sync_all_users()

        context.user_data.clear()

        if role == 'driver':
            await update.message.reply_text(
                f"✅ شكراً لك يا كابتن {name}.\nطلبك قيد المراجعة، سيتم إشعارك عند التفعيل.",
                reply_markup=get_main_kb('driver', False)
            )
            # تنبيه الأدمن
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ قبول", callback_data=f"verify_ok_{user_id}"),
                 InlineKeyboardButton("❌ رفض", callback_data=f"verify_no_{user_id}")]
            ])
            for aid in ADMIN_IDS:
                try:
                    await context.bot.send_message(chat_id=aid, text=f"🔔 **تسجيل كابتن جديد**\nالاسم: {name}\nالسيارة: {car}", reply_markup=kb)
                except: pass
        else:
            await update.message.reply_text(
                f"🎉 أهلاً بك {name}، تم تفعيل حسابك كراكب.",
                reply_markup=get_main_kb('rider', True)
            )

    except Exception as e:
        print(f"Error registration: {e}")
        await update.message.reply_text("حدث خطأ، حاول لاحقاً.")
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
    """إرسال الطلب للكباتن القريبين"""
    r_lat = context.user_data.get('lat')
    r_lon = context.user_data.get('lon')

    # إذا لم يكن في الكاش، خذ من الرسالة الحالية
    if update.message.location:
        r_lat = update.message.location.latitude
        r_lon = update.message.location.longitude

    if not r_lat:
        await update.message.reply_text("📍 لم يتم تحديد الموقع!")
        return

    price = context.user_data.get('order_price', 0)
    district = context.user_data.get('search_district', "موقع GPS")

    count = 0
    await sync_all_users()

    for d in CACHED_DRIVERS:
        # تجاهل من ليس لديه موقع
        if not d.get('lat'): continue

        dist = get_distance(r_lat, r_lon, d['lat'], d['lon'])

        if dist <= 50: # نطاق 50 كم
            warning = ""
            if not d.get('is_verified') or d.get('balance', 0) <= -50:
                warning = "\n⚠️ **تنبيه:** يجب تسديد العمولة بعد الرحلة."

            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ قبول الرحلة", callback_data=f"accept_gen_{update.effective_user.id}_{price}")
            ]])

            try:
                await context.bot.send_message(
                    chat_id=d['user_id'],
                    text=f"🚖 **طلب رحلة جديد!**\n📍 الحي: {district}\n💰 السعر: {price} ريال\n 📏 البعد: {dist:.1f} كم{warning}",
                    reply_markup=kb,
                    parse_mode=ParseMode.MARKDOWN
                )
                count += 1
            except: continue

    await update.message.reply_text(f"📡 تم إرسال طلبك لـ {count} كابتن قريب.")

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
    if not update.message or not update.message.text: return
    text = update.message.text
    user_id = update.effective_user.id
    state = context.user_data.get('state')

    # 1. معالجة خطوات التسجيل المتسلسلة
    if state == 'WAIT_NAME':
        context.user_data['reg_name'] = text
        await update.message.reply_text("📱 **الآن أرسل رقم جوالك:**")
        context.user_data['state'] = 'WAIT_PHONE'
        return

    if state == 'WAIT_PHONE':
        context.user_data['reg_phone'] = text
        role = context.user_data.get('reg_role')
        if role == 'driver':
            await update.message.reply_text("🚗 **أخيراً، ما هو نوع وموديل سيارتك؟**\n(مثال: كامري 2020)")
            context.user_data['state'] = 'WAIT_CAR'
        else:
            await complete_registration(update, context, context.user_data['reg_name'])
            context.user_data['state'] = None
        return

    if state == 'WAIT_CAR':
        context.user_data['reg_car'] = text
        await complete_registration(update, context, context.user_data['reg_name'])
        context.user_data['state'] = None
        return

    # معالجة تفاصيل التوصيل
    if state == 'WAIT_TRIP_DETAILS':
        details = text
        driver_id = context.user_data.get('driver_to_order')
        dist = context.user_data.get('order_dist')
        rider_name = update.effective_user.first_name
        
        # إرسال الطلب للكابتن في الخاص
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ قبول (10% عمولة)", callback_data=f"accept_ride_{user_id}_0"), # نضع 0 مؤقتاً للسعر
             InlineKeyboardButton("❌ رفض", callback_data=f"reject_ride_{user_id}")]
        ])
        
        await context.bot.send_message(
            chat_id=driver_id,
            text=f"🔔 **طلب مشوار جديد من القروب!**\n\n👤 الراكب: {rider_name}\n📍 الحي: {dist}\n📋 التفاصيل: {details}\n\n*يرجى الاتفاق على السعر في الدردشة بعد القبول.*",
            reply_markup=kb,
            parse_mode=ParseMode.MARKDOWN
        )
        await update.message.reply_text("✅ تم إرسال طلبك للكابتن، بانتظار قبوله لفتح الدردشة.")
        context.user_data['state'] = None
        return

 # 3. الحالة المعدلة: استقبال السعر وعرض الكباتن (استبدل القديمة بهذه) ✅
    if state == 'WAIT_PRICE_FOR_DISTRICT_SEARCH':
        try:
            price = float(text)
            details = context.user_data.get('trip_details_text')
            selected_dist = context.user_data.get('selected_district_search')
            
            await sync_all_users()
            # فحص الأحياء (تأكد من تنظيف النص للمقارنة)
            found = []
            for d in CACHED_DRIVERS:
                if d.get('districts'):
                    d_dists = [x.strip() for x in d['districts'].replace("،", ",").split(",")]
                    if selected_dist in d_dists:
                        found.append(d)
            
            if not found:
                await update.message.reply_text(f"❌ للأسف لا يوجد كباتن متوفرين حالياً في حي {selected_dist}.")
            else:
                keyboard = []
                for d in found[:8]:
                    # نمرر آيدي السائق والسعر في الزر
                    keyboard.append([InlineKeyboardButton(f"🚖 {d['name']} ({d['car_info']})", callback_data=f"req_driver_{d['user_id']}_{price}")])
                
                await update.message.reply_text(
                    f"✅ **تم تجهيز طلبك بنجاح!**\n\n"
                    f"📋 **التفاصيل المرسلة:**\n{details}\n\n"
                    f"💰 **السعر المعروض:** {price} ريال\n\n"
                    f"اختر الكابتن المفضل لديك لبدء التواصل:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            context.user_data['state'] = None # إنهاء الحالة
        except ValueError:
            await update.message.reply_text("⚠️ يرجى إدخال السعر كأرقام فقط (مثال: 35).")
        return

    

    # 2. أوامر القائمة الرئيسية
    if text == "🚖 طلب رحلة":
        await order_ride_options(update, context)
        return

    if text == "📍 تحديث موقعي":
        msg = await update.message.reply_text("📍 أرسل موقعك الحالي (Location) من المشبك 📎")
        return

    if text == "💰 محفظتي":
        user = USER_CACHE.get(user_id)
        bal = user.get('balance', 0) if user else 0
        await update.message.reply_text(f"💳 رصيدك الحالي: {bal} ريال")
        return

    if text == "📝 تحديث الأحياء":
        await update.message.reply_text("✍️ أرسل أسماء الأحياء التي تعمل بها مفصولة بفواصل:")
        context.user_data['state'] = 'WAIT_DISTRICTS'
        return

    if text == "ℹ️ حالة اشتراكي":
        user = USER_CACHE.get(user_id)
        if user and user.get('subscription_expiry'):
             expiry = user['subscription_expiry'].strftime('%Y-%m-%d')
             await update.message.reply_text(f"📅 اشتراكك ينتهي في: {expiry}")
        else:
             await update.message.reply_text("❌ ليس لديك اشتراك فعال.")
        return

    # 3. معالجة حالات الطلب والبحث
    if state == 'WAIT_DISTRICTS':
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET districts = %s WHERE user_id = %s", (text, user_id))
            conn.commit()
        await sync_all_users()
        await update.message.reply_text("✅ تم تحديث الأحياء.")
        context.user_data['state'] = None
        return

    if state == 'WAIT_ELITE_DISTRICT':
        # بحث نصي في الأحياء
        found = []
        for d in CACHED_DRIVERS:
            if d.get('districts') and text in d['districts']:
                found.append(d)

        if not found:
            await update.message.reply_text("❌ لا يوجد كابتن في هذا الحي حالياً.")
        else:
            for d in found:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("📞 طلب", url=f"tg://user?id={d['user_id']}") ]])
                await update.message.reply_text(f"👤 الكابتن: {d['name']}\n🚗 {d['car_info']}", reply_markup=kb)
        context.user_data['state'] = None
        return

    if state == 'WAIT_GENERAL_DISTRICT':
        context.user_data['search_district'] = text
        await update.message.reply_text("💰 **كم السعر المعروض؟** (أرقام فقط)")
        context.user_data['state'] = 'WAIT_GENERAL_PRICE'
        return

    if state == 'WAIT_GENERAL_PRICE':
        try:
            context.user_data['order_price'] = float(text)
            kb = ReplyKeyboardMarkup([[KeyboardButton("📍 مشاركة موقعي", request_location=True)]], one_time_keyboard=True, resize_keyboard=True)
            await update.message.reply_text("📍 الآن شارك موقعك لإرسال الطلب:", reply_markup=kb)
            context.user_data['state'] = 'WAIT_LOCATION_FOR_ORDER'
        except:
            await update.message.reply_text("⚠️ أرقام فقط لو سمحت.")
        return

# --- معالجة المواقع (Location) ---

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lat = update.message.location.latitude
    lon = update.message.location.longitude
    state = context.user_data.get('state')

    # تحديث الموقع في كل الحالات
    context.user_data['lat'] = lat
    context.user_data['lon'] = lon

    # تحديث في قاعدة البيانات (يمكن جعله غير متزامن لتخفيف الضغط)
    threading.Thread(target=update_db_location, args=(user_id, lat, lon)).start()

    # إذا كان الغرض هو طلب رحلة
    if state == 'WAIT_LOCATION_FOR_ORDER':
        await broadcast_general_order(update, context)
        context.user_data['state'] = None
        # إعادة الكيبورد الأصلي
        await update.message.reply_text("✅ تم الإرسال.", reply_markup=get_main_kb("rider", True))
    else:
        await update.message.reply_text("✅ تم تحديث إحداثياتك بنجاح.")

def update_db_location(uid, lat, lon):
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET lat=%s, lon=%s WHERE user_id=%s", (lat, lon, uid))
                conn.commit()
        finally:
            conn.close()
# دالة لحذف الرسالة بعد وقت محدد
async def delete_message_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    try:
        await context.bot.delete_message(chat_id=job.chat_id, message_id=job.data)
    except Exception as e:
        print(f"Error deleting message: {e}")


# --- معالجة الأزرار (Callbacks) ---
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id
    
    # تفادي أخطاء الضغط المتكرر
    try:
        await query.answer()
    except:
        pass

    # ---------------------------------------------------------
    # 1. اختيار المدينة
    # ---------------------------------------------------------
    if data == "order_by_district":
        keyboard = []
        for city in CITIES_DISTRICTS.keys():
            keyboard.append([InlineKeyboardButton(city, callback_data=f"city_{city}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("📍 اختر المدينة:", reply_markup=reply_markup)

    # ---------------------------------------------------------
    # 2. اختيار الحي (بعد اختيار المدينة)
    # ---------------------------------------------------------
    elif data.startswith("city_"):
        city_name = data.split("_")[1]
        districts = CITIES_DISTRICTS.get(city_name, [])
        keyboard = []
        for i in range(0, len(districts), 2):
            row = [InlineKeyboardButton(districts[i], callback_data=f"sel_dist_{districts[i]}")]
            if i + 1 < len(districts):
                # داخل قسم
        row.append(InlineKeyboardButton(districts[i], callback_data=f"sel_dist_{districts[i]}"))

            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("⬅️ رجوع", callback_data="order_by_district")])
        
        await query.edit_message_text(f"🏙️ أحياء {city_name}:\nاختر الحي الذي تتواجد فيه:", reply_markup=InlineKeyboardMarkup(keyboard))

    # ---------------------------------------------------------
    # 3. تم اختيار الحي -> طلب السعر من الراكب
    # ---------------------------------------------------------
    elif data.startswith("search_dist_"):
        selected_dist = data.split("_")[2]
        await sync_all_users()
        
        matched_drivers = []
        for d in CACHED_DRIVERS:
            if d.get('districts'):
                d_dists = [x.strip().replace("ة", "ه") for x in d['districts'].replace("،", ",").split(",")]
                if selected_dist.replace("ة", "ه") in d_dists:
                    matched_drivers.append(d)

        if not matched_drivers:
            await query.edit_message_text(f"📍 حي {selected_dist}:\n\nلا يوجد كباتن حالياً.")
        else:
            keyboard = []
            for d in matched_drivers[:8]:
                # التغيير هنا: نرسل callback_data بدلاً من url
                # التنسيق: book_ID_DISTRICT
                keyboard.append([InlineKeyboardButton(
                    f"🚖 طلب الكابتن {d['name']}", 
                    callback_data=f"book_{d['user_id']}_{selected_dist}"
                )])
            
            await query.edit_message_text(
                f"✅ **كباتن متوفرين في حي {selected_dist}:**\nاضغط على اسم الكابتن لطلب مشوار عبر البوت:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )


    # ---------------------------------------------------------
    # 4. اختيار كابتن محدد (بعد أن أدخل الراكب السعر وظهرت القائمة)
    # ---------------------------------------------------------
    elif data.startswith("req_driver_"):
        parts = data.split("_")
        driver_id, price = int(parts[2]), float(parts[3])
        rider_id = user_id
        
        # جلب التفاصيل المحفوظة
        details = context.user_data.get('trip_details_text', 'لا يوجد تفاصيل')
        rider_name = update.effective_user.first_name

        kb_accept = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ قبول ودفع العمولة", callback_data=f"accept_ride_{rider_id}_{price}"),
             InlineKeyboardButton("❌ رفض", callback_data=f"reject_ride_{rider_id}")]
        ])
        
        await context.bot.send_message(
            chat_id=driver_id,
            text=(f"🔔 **طلب مشوار خاص جديد!**\n\n"
                  f"👤 من: {rider_name}\n"
                  f"📋 **التفاصيل:**\n{details}\n\n"
                  f"💰 **العرض:** {price} ريال\n"
                  f"📉 **العمولة:** {price * 0.10} ريال"),
            reply_markup=kb_accept
        )
        await query.edit_message_text("⏳ تم إرسال طلبك والتفاصيل للكابتن.. بانتظار رده.")


        # إرسال العرض للكابتن
        kb_accept = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ قبول ودفع العمولة", callback_data=f"accept_ride_{rider_id}_{price}"),
                InlineKeyboardButton("❌ رفض", callback_data=f"reject_ride_{rider_id}")
            ]
        ])
        
        # حساب العمولة للعرض
        commission = price * 0.10
        
        try:
            await context.bot.send_message(
                chat_id=driver_id,
                text=(
                    f"🔔 **طلب خاص جديد!**\n\n"
                    f"👤 العميل: {rider_name}\n"
                    f"💰 العرض: {price} ريال\n"
                    f"📉 العمولة المستحقة: {commission} ريال\n\n"
                    f"هل تقبل المشوار؟ (سيتم خصم العمولة فور القبول)"
                ),
                reply_markup=kb_accept,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            await query.edit_message_text("⚠️ تعذر الوصول للكابتن (ربما قام بحظر البوت).")

    # ---------------------------------------------------------
    # 5. قبول السائق للطلب (سواء طلب عام أو خاص) + خصم الرصيد
    # ---------------------------------------------------------
    elif data.startswith("accept_ride_") or data.startswith("accept_gen_"):
        parts = data.split("_")
        rider_id = int(parts[2])
        price = float(parts[3])
        driver_id = user_id
        commission = price * 0.10 # عمولة 10%

        # أ) التحقق من رصيد السائق في قاعدة البيانات
        conn = get_db_connection()
        can_accept = False
        current_balance = 0.0
        
        if conn:
            with conn.cursor() as cur:
                cur.execute("SELECT balance, name, car_info FROM users WHERE user_id = %s", (driver_id,))
                res = cur.fetchone()
                if res:
                    current_balance = res[0]
                    driver_name = res[1]
                    driver_car = res[2]
                    # الشرط: يجب أن يكون الرصيد أكبر من -10 (أو 0 حسب رغبتك)
                    if current_balance >= 0: 
                        can_accept = True
            conn.close()

        # ب) إذا الرصيد غير كافٍ
        if not can_accept:
            await query.answer("⚠️ رصيدك غير كافٍ لقبول الطلبات! يرجى الشحن.", show_alert=True)
            return

        # ج) إرسال استئذان للراكب (كما طلبت سابقاً)
        # ملاحظة: الخصم يتم بعد موافقة الراكب النهائية لضمان العدالة، 
        # أو يمكن الخصم هنا "حجز مبدئي". سأقوم بالخصم عند بدء الدردشة الفعلي في الخطوة التالية.
        
        kb_permission = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ موافقة وفتح الدردشة", callback_data=f"final_start_{driver_id}_{price}"),
                InlineKeyboardButton("❌ رفض", callback_data=f"reject_ride_{driver_id}")
            ]
        ])

        await query.edit_message_text("⏳ تم قبول العرض مبدئياً.. بانتظار موافقة العميل النهائية.")
        
        await context.bot.send_message(
            chat_id=rider_id,
            text=(f"🎉 **وافق الكابتن {driver_name}!**\n"
                  f"🚗 السيارة: {driver_car}\n"
                  f"💰 السعر: {price} ريال\n\n"
                  f"هل تريد فتح المحادثة الآن؟"),
            reply_markup=kb_permission,
            parse_mode=ParseMode.MARKDOWN
        )

    # ---------------------------------------------------------
    # 6. الموافقة النهائية وبدء الدردشة + خصم العمولة فعلياً
    # ---------------------------------------------------------
    elif data.startswith("final_start_"):
        parts = data.split("_")
        driver_id = int(parts[2])
        price = float(parts[3])
        rider_id = user_id
        commission = price * 0.10

        # تنفيذ الخصم من السائق
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET balance = balance - %s WHERE user_id = %s", (commission, driver_id))
                conn.commit()
            conn.close()

        # بدء الجلسة
        start_chat_session(driver_id, rider_id)
        
        # إشعار الأدمن
        rider_info = USER_CACHE.get(rider_id, {"name": "غير معروف"})
        driver_info = USER_CACHE.get(driver_id, {"name": "غير معروف"})
        
        admin_alert = (
            f"💰 **عملية جديدة (تم خصم العمولة)**\n"
            f"📉 العمولة: {commission} ريال\n"
            f"👤 الراكب: `{rider_id}` ({rider_info.get('name')})\n"
            f"🚖 الكابتن: `{driver_id}` ({driver_info.get('name')})\n"
            f"📜 السجل: `/logs {rider_id} {driver_id}`"
        )
        for aid in ADMIN_IDS:
            try: await context.bot.send_message(chat_id=aid, text=admin_alert, parse_mode=ParseMode.MARKDOWN)
            except: pass

        # رسائل البدء
        kb_end = ReplyKeyboardMarkup([[KeyboardButton("❌ إنهاء المحادثة")]], resize_keyboard=True)
        await query.edit_message_text("✅ تم بدء الرحلة.")
        await context.bot.send_message(chat_id=rider_id, text="✅ بدأت المحادثة مع الكابتن.", reply_markup=kb_end)
        await context.bot.send_message(chat_id=driver_id, text=f"✅ تم خصم {commission} ريال عمولة.\nالعميل معك الآن في الدردشة.", reply_markup=kb_end)

        # إنشاء لوحة الأزرار المحدثة
        kb_chat = ReplyKeyboardMarkup([
            [KeyboardButton("📍 مشاركة موقعي الحالي", request_location=True)],
            [KeyboardButton("❌ إنهاء المحادثة")]
        ], resize_keyboard=True)

        await query.edit_message_text("✅ تم فتح الدردشة ومشاركة الأزرار.")
        
        # إرسال الأزرار للطرفين
        await context.bot.send_message(chat_id=rider_id, text="بدأت المحادثة.. يمكنك الآن إرسال موقعك أو رسائل نصية.", reply_markup=kb_chat)
        await context.bot.send_message(chat_id=driver_id, text="بدأت المحادثة.. يمكنك الآن إرسال موقعك أو رسائل نصية.", reply_markup=kb_chat)


    # ---------------------------------------------------------
    # 7. الرفض
    # ---------------------------------------------------------
    elif data.startswith("reject_ride_"):
        target_id = int(data.split("_")[2])
        await query.edit_message_text("❌ تم رفض الطلب.")
        try:
            await context.bot.send_message(chat_id=target_id, text="❌ تم إلغاء/رفض الطلب.")
        except: pass

    # ---------------------------------------------------------
    # 8. الطلب العام (Order General)
    # ---------------------------------------------------------
    elif data == "order_general":
        await query.edit_message_text("✍️ في أي حي تتواجد الآن؟")
        context.user_data['state'] = 'WAIT_GENERAL_DISTRICT'

    # ---------------------------------------------------------
    # 9. التوثيق (Verification)
    # ---------------------------------------------------------
    elif data.startswith("verify_"):
        action, uid = data.split("_")[1], int(data.split("_")[2])
        is_v = (action == "ok")
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET is_verified = %s WHERE user_id = %s", (is_v, uid))
            conn.commit()
        conn.close()
        await query.edit_message_text(f"⚙️ تم تحديث الحالة للمستخدم {uid}")


    elif data.startswith("book_"):
        parts = data.split("_")
        driver_id = parts[1]
        dist = parts[2]
        
        # تحويل الراكب للخاص لبدء إدخال التفاصيل
        bot_username = (await context.bot.get_me()).username
        start_link = f"https://t.me/{bot_username}?start=order_{driver_id}_{dist}"
        
        await query.answer("سيتم نقلك لخاص البوت لإتمام الطلب...", show_alert=True)
        # نرسل له زر يحوله للخاص لأن تليجرام لا يسمح بفتح الخاص تلقائياً
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("إرسال تفاصيل المشوار 💬", url=start_link)]])
        await query.edit_message_text(f"لطلب الكابتن، يرجى الضغط على الزر أدناه وإرسال التفاصيل في الخاص:", reply_markup=kb)


    # ===============================================================
    # 10. التوثيق من قبل الأدمن
    # ===============================================================
        # ---------------------------------------------------------
    # 10. معالجة اختيار الحي من القروب (عرض الكباتن)
    # ---------------------------------------------------------
    elif data.startswith("search_dist_"):
        selected_dist = data.split("_")[2]
        await sync_all_users()
        
        matched_drivers = []
        for d in CACHED_DRIVERS:
            if d.get('districts'):
                # تنظيف ومقارنة الأحياء (تأكد من مطابقة الهاء والتاء المربوطة)
                d_dists = [x.strip().replace("ة", "ه") for x in d['districts'].replace("،", ",").split(",")]
                clean_search = selected_dist.replace("ة", "ه")
                
                if clean_search in d_dists:
                    matched_drivers.append(d)

        if not matched_drivers:
            await query.edit_message_text(f"📍 حي {selected_dist}:\n\nللأسف لا يوجد كباتن مسجلين في هذا الحي حالياً.")
        else:
            keyboard = []
            for d in matched_drivers[:8]: # عرض أول 8 كباتن
                # الرابط يحول المستخدم لخاص البوت ليبدأ الطلب بشكل رسمي أو لخاص الكابتن
                keyboard.append([InlineKeyboardButton(f"🚖 الكابتن {d['name']} ({d['car_info']})", url=f"tg://user?id={d['user_id']}")])
            
            await query.edit_message_text(
                f"✅ **كباتن متوفرين في حي {selected_dist}:**\nاضغط على اسم الكابتن للتواصل معه مباشرة:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )


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
    if not update.message or not update.message.text: 
        return

    # استخراج البيانات الأساسية
    user = update.effective_user
    chat = update.effective_chat
    text = update.message.text.lower()
    # تنظيف النص لتوحيد البحث
    msg_clean = text.replace("ة", "ه").replace("أ", "ا").replace("إ", "ا")

    # 1️⃣ فحص الكلمات الممنوعة (الطلبات الشهرية)
    FORBIDDEN_KEYWORDS = ["شهري", "عقد", "استئجار"]

    if any(k in msg_clean for k in FORBIDDEN_KEYWORDS):
        try:
            await update.message.delete()
        except Exception as e:
            print(f"خطأ في حذف الرسالة: {e}")

        await context.bot.send_message(
            chat_id=chat.id,
            text=f"عذراً {user.first_name}، العروض الشهرية تُرسل للإدارة للمراجعة."
        )

        # إرسال للآدمنز (لاحظ الإزاحة هنا: يجب أن تكون داخل الـ if)
        for admin in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin, 
                    text=f"⚠️ **طلب مشوار شهري جديد:**\n\n👤 من: {user.first_name}\n📝 النص: {update.message.text}\n📍 المصدر: {chat.title}",
                    parse_mode=ParseMode.MARKDOWN
                )
            except: pass
        return  # يتوقف البوت هنا فقط إذا كانت الرسالة "شهرية"
    # --- داخل دالة group_order_scanner ---
    districts = CITIES_DISTRICTS.get("المدينة المنورة", [])

    keyboard = []
    for i in range(0, len(districts), 2):
        row = [InlineKeyboardButton(districts[i], callback_data=f"search_dist_{districts[i]}")]
        if i + 1 < len(districts):
            row.append(InlineKeyboardButton(districts[i+1], callback_data=f"search_dist_{districts[i+1]}"))
        keyboard.append(row)

    # نرسل الرسالة ونخزنها لكي يعرف البوت أي رسالة يحذف لاحقاً
    await update.message.reply_text(
        f"يا هلا بك يا {user.first_name} ✨\nحدد الحي المطلوب للبحث عن كباتن متوفرين:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


    # 2️⃣ فحص كلمات البحث العادية (مشوار، توصيل...)
    KEYWORDS = ["توصيل", "مشوار", "مطلوب", "سواق", "كابتن"]
    if not any(k in msg_clean for k in KEYWORDS):
        return

    # 3️⃣ البحث عن الأحياء ومطابقتها مع الكباتن
    await sync_all_users() 

    matched_drivers = []
    found_district = ""

    for d in CACHED_DRIVERS:
        if not d.get('districts'): continue

        # تنظيف قائمة أحياء الكابتن للمقارنة
        districts_list = d['districts'].replace("،", ",").split(",")
        for dist in districts_list:
            clean_dist = dist.strip().replace("ة", "ه").replace("أ", "ا").replace("إ", "ا")

            if len(clean_dist) > 2 and clean_dist in msg_clean:
                if d not in matched_drivers:
                    matched_drivers.append(d)
                found_district = dist.strip()

    # 4️⃣ إرسال التنبيهات والرد في المجموعة
    if matched_drivers:
        # أ: تنبيه الكباتن في الخاص
        for d in matched_drivers:
            try:
                await context.bot.send_message(
                    chat_id=d['user_id'],
                    text=f"🔔 **تنبيه:** يوجد طلب في حي ({found_district}) الآن بالقروب."
                )
            except: pass

        # ب: الرد في المجموعة (أزرار التواصل)
        keyboard = []
        for d in matched_drivers[:5]:
            keyboard.append([
                InlineKeyboardButton(f"🚖 اطلب {d['name']}", url=f"tg://user?id={d['user_id']}")
            ])

        await update.message.reply_text(
            f"✅ **تم العثور على كباتن في حي {found_district}:**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
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
    
    # 1. التأكد أن الرسالة ليست أمراً
    if not update.message or (update.message.text and update.message.text.startswith("/")):
        return

    # 2. جلب الطرف الآخر
    partner_id = get_chat_partner(user_id)
    if not partner_id:
        return 

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
    threading.Thread(target=run_flask, daemon=True).start()
    init_db()
    
    # زيادة المهلة لضمان استقرار الاتصال على Render
    request_config = HTTPXRequest(connect_timeout=30, read_timeout=30)
    application = ApplicationBuilder().token(BOT_TOKEN).request(request_config).build()

    # 1. الأوامر الأساسية (لها الأولوية القصوى)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("sub", admin_add_days))
    application.add_handler(CommandHandler("cash", admin_cash))
    application.add_handler(CommandHandler("broadcast", admin_broadcast))
    application.add_handler(CommandHandler("logs", admin_get_logs))
    application.add_handler(MessageHandler(filters.Regex("^❌ إنهاء المحادثة$"), end_chat_command))

    # 2. معالجة حالات التسجيل والطلبات (Global Handler) 
    # يجب أن يكون قبل الـ Relay لكي يستطيع المستخدم التسجيل
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, global_handler), group=1)

    # 3. الدردشة الوسيطة (Relay)
    # تعمل فقط إذا كان المستخدم "في محادثة نشطة" فعلياً
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.ALL & ~filters.COMMAND & ~filters.Regex("^❌ إنهاء المحادثة$"),
        chat_relay_handler
    ), group=2)

    # 4. المعالجات الأخرى
    application.add_handler(CallbackQueryHandler(handle_callbacks))
    application.add_handler(MessageHandler(filters.LOCATION, location_handler))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT, group_order_scanner))
    
    # تنظيف الرسائل القديمة عند التشغيل
    application.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    main()