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
BOT_TOKEN = "7963641334:AAFGrBWHA9shQiulMW_CliIwa5xWi1mHq8I"
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
    await query.answer()

    # 1. قائمة المدن
    if data == "order_by_district":
        keyboard = []
        for city in CITIES_DISTRICTS.keys():
            keyboard.append([InlineKeyboardButton(city, callback_data=f"city_{city}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("📍 اختر المدينة للبحث عن كابتن:", reply_markup=reply_markup)

    # 2. قائمة الأحياء
    elif data.startswith("city_"):
        city_name = data.split("_")[1]
        districts = CITIES_DISTRICTS.get(city_name, [])
        keyboard = []
        for i in range(0, len(districts), 2):
            row = [InlineKeyboardButton(districts[i], callback_data=f"search_dist_{districts[i]}")]
            if i + 1 < len(districts):
                row.append(InlineKeyboardButton(districts[i+1], callback_data=f"search_dist_{districts[i+1]}"))
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("⬅️ رجوع", callback_data="order_by_district")])
        await query.edit_message_text(f"🏙️ أحياء {city_name}:\nاختر الحي المطلوب:", reply_markup=InlineKeyboardMarkup(keyboard))

    # 3. عرض الكباتن (الميزة المطلوبة: رسالة واحدة بجميع الأزرار)
    elif data.startswith("search_dist_"):
        selected_dist = data.split("_")[2]
        
        # حذف قائمة الأحياء فوراً لتنظيف القروب
        try:
            await query.message.delete()
        except:
            pass

        await sync_all_users() 
        found = []
        for d in CACHED_DRIVERS:
            if d.get('districts'):
                d_districts = d['districts'].replace("،", ",").split(",")
                if any(selected_dist.strip() in item.strip() for item in d_districts):
                    found.append(d)

        if not found:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"❌ نعتذر، لا يوجد كابتن متوفر حالياً في حي ({selected_dist})."
            )
else:
            # بناء قائمة الأزرار في رسالة واحدة
            keyboard = []
            for d in found[:8]: # عرض أول 8 كباتن فقط
                btn_label = f"🚖 {d['name']} - ({d['car_info']})"
                keyboard.append([InlineKeyboardButton(btn_label, url=f"tg://user?id={d['user_id']}")])

            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"✅ **كباتن حي {selected_dist} المتاحين:**\nاضغط على الكابتن المناسب لبدء التفاوض:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )

    # 4. طلب عام (بحث بالموقع)
    elif data == "order_general":
        await query.edit_message_text("✍️ في أي حي تتواجد الآن؟")
        context.user_data['state'] = 'WAIT_GENERAL_DISTRICT'

    # 5. قبول الرحلة وخصم العمولة
    elif data.startswith("accept_gen_"):
        parts = data.split("_")
        rider_id, price = int(parts[2]), float(parts[3])
        commission = price * 0.10
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET balance = balance - %s WHERE user_id = %s", (commission, user_id))
            conn.commit()
        conn.close()

                else:
            # بناء قائمة الأزرار
            keyboard = []
            for d in found[:8]:
                btn_label = f"🚖 {d['name']} - ({d['car_info']})"
                keyboard.append([InlineKeyboardButton(btn_label, url=f"tg://user?id={d['user_id']}")])

            # 1️⃣ إرسال الرسالة وتخزينها في متغير
            sent_msg = await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"✅ **كباتن حي {selected_dist} المتاحين:**\n(تختفي هذه الرسالة تلقائياً بعد 5 دقائق)",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )

            # 2️⃣ جدولة حذف الرسالة بعد 300 ثانية (5 دقائق)
            context.job_queue.run_once(
                delete_message_job, 
                when=300, 
                data=sent_msg.message_id, 
                chat_id=query.message.chat_id
            )

        await query.edit_message_text(f"✅ قبلت الرحلة. خصم عمولة: {commission} ريال.")

    # 6. توثيق السائقين (للآدمن)
    elif data.startswith("verify_"):
        action, uid = data.split("_")[1], int(data.split("_")[2])
        is_v = True if action == "ok" else False
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET is_verified = %s, is_blocked = %s WHERE user_id = %s", (is_v, not is_v, uid))
            conn.commit()
        conn.close()
        await query.edit_message_text(f"⚙️ تم {action} المستخدم {uid}")



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
async def add_fake_drivers():
    # بيانات وهمية لكباتن في أحياء مختلفة بالرياض (مثلاً)
    fake_data = [
        (111111, 'أبو فهد', '0501111111', 'كامري 2023', 'الصحافة, المروج, الياسمين', 'active'),
        (222222, 'كابتن خالد', '0502222222', 'تويوتا 2022', 'العليا, السليمانية, الورود', 'active'),
        (333333, 'أبو سارة', '0503333333', 'هيونداي 2021', 'الشفا, بدر, نمار', 'active'),
        (444444, 'كابتن محمد', '0504444444', 'لكزس 2020', 'الروضة, الريان, الربوة', 'active'),
        (555555, 'أبو نايف', '0505555555', 'فورد 2022', 'النرجس, العارض, القيروان', 'active')
    ]

    async with db_pool.acquire() as conn:
        for d in fake_data:
            await conn.execute("""
                INSERT INTO drivers (user_id, name, phone, car_info, districts, status)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (user_id) DO NOTHING
            """, d[0], d[1], d[2], d[3], d[4], d[5])
        
    print("✅ تم إضافة 5 كباتن وهميين بنجاح لتجربة النظام!")

# ==================== 🌐 5. خادم Flask (للبقاء نشطاً) ====================

app = Flask('')
@app.route('/')
def home(): return "Bot is Running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# ==================== 🏁 6. التشغيل الرئيسي ====================

def main():
    # 1. تشغيل السيرفر (Flask) لضمان بقاء البوت حياً على Render
    threading.Thread(target=run_flask, daemon=True).start()

    # 2. تهيئة قاعدة البيانات
    init_db()

    # 3. إعداد طلبات HTTP بمهلة أطول لتجنب أخطاء الشبكة
    request_config = HTTPXRequest(connect_timeout=20, read_timeout=20)

    # 4. بناء التطبيق
    application = ApplicationBuilder() \
        .token(BOT_TOKEN) \
        .request(request_config) \
        .build()

    # --- تسجيل الـ Handlers (الترتيب مهم جداً!) ---

    # أ- الأوامر النصية (Commands)
    application.add_handler(CommandHandler("start", start_command))

    application.add_handler(CommandHandler("sub", admin_add_days))
    application.add_handler(CommandHandler("cash", admin_cash))
    # أضف هذا السطر مع أوامر sub و cash
    application.add_handler(CommandHandler("broadcast", admin_broadcast))


    # ب- أزرار التحكم (Callbacks)
    application.add_handler(CallbackQueryHandler(register_callback, pattern="^reg_"))
    application.add_handler(CallbackQueryHandler(handle_callbacks))

    # ج- الموقع الجغرافي
    application.add_handler(MessageHandler(filters.LOCATION, location_handler))

    # د- مراقب المجموعات (يجب أن يكون قبل الـ Private)
    # هذا سيتعامل مع "الطلبات الشهرية" و "البحث عن أحياء" في آن واحد
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, group_order_scanner))

    # هـ- المحادثات الخاصة (Private)
    # هذا سيتعامل مع عمليات التسجيل وتحديث البيانات في الخاص
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, global_handler))

    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))

    
    # 5. تشغيل البوت مع تنظيف التحديثات العالقة
    print("🚀 البوت يعمل الآن بكامل طاقته...")
    application.run_polling(drop_pending_updates=True, close_loop=False)

if __name__ == '__main__':
    main()
