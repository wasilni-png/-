#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import threading
import os
import re
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

# إعداد السيرفر لـ Render
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive! 🚀"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# ==================== ⚙️ 1. الإعدادات ====================

# 🔴🔴 هام: ضع هذه البيانات في متغيرات بيئة على ريندر
DB_URL = os.environ.get("DATABASE_URL", "postgresql://postgres.nmteaqxrtcegxmgvsbzr:mohammedfahdypb@aws-1-ap-south-1.pooler.supabase.com:6543/postgres")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8498451295:AAGt1R7THllSjYtEe5hvIEPnPhRkS_iBcnU")

# آيدي المشرفين
ADMIN_IDS = [8563113166, 7996171713, 7580027135, 5027690233]

# --- 1. إعدادات الأحياء الذكية (المدينة المنورة) ---
CITIES_DISTRICTS = {
    "المدينة المنورة": [
        "الإسكان", "البحر", "البدراني", "الفتح", "التلال", "الجرف", "الحزام", "الحمراء", 
        "الخالدية", "الدويخله", "الرانوناء", "الربوة", "الشروق", "الشرق", 
        "العاقول", "العريض", "العزيزية", "العنابس", "القبلتين", "المبعوث", 
        "المطار", "المغيسله", "الملك فهد", "النبلاء", "الهجرة", "باقدو", 
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
        logger.error(f"❌ فشل الاتصال بقاعدة البيانات: {e}")
        return None

def init_db():
    """إنشاء الجداول وتحديث الأعمدة الناقصة"""
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            # جدول المستخدمين
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
            
            # جدول سجلات الدردشة
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
            
            # جدول المحادثات النشطة
            cur.execute("""
                CREATE TABLE IF NOT EXISTS active_chats (
                    user_id BIGINT PRIMARY KEY,
                    partner_id BIGINT,
                    start_time TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            conn.commit()
            logger.info("✅ قاعدة البيانات جاهزة.")
    except Exception as e:
        logger.error(f"❌ خطأ في تهيئة قاعدة البيانات: {e}")
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
        logger.error(f"❌ خطأ في حفظ السجل: {e}")
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
    """تحديث موقع المستخدم في الخلفية"""
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET lat = %s, lon = %s WHERE user_id = %s", (lat, lon, user_id))
            conn.commit()
    except Exception as e:
        logger.error(f"Error updating location for {user_id}: {e}")
    finally:
        conn.close()

def deduct_commission(driver_id, price):
    commission = price * 0.15
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET balance = balance - %s WHERE user_id = %s", (commission, driver_id))
                conn.commit()
            return commission
        except Exception as e:
            logger.error(f"Error deducting commission: {e}")
            return 0
        finally:
            conn.close()
    return 0

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
        logger.error(f"❌ خطأ تحديث الأحياء: {e}")
        return False
    finally:
        conn.close()

async def sync_all_users(force=False):
    """تحديث الذاكرة المؤقتة من قاعدة البيانات"""
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
            cur.execute("SELECT partner_id FROM active_chats WHERE user_id = %s", (user_id,))
            res = cur.fetchone()
            if res:
                partner_id = res[0]

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
            [KeyboardButton("📞 تواصل مع الإدارة")]
        ], resize_keyboard=True)

    # للراكب
    return ReplyKeyboardMarkup([
        [KeyboardButton("🚖 طلب رحلة"), KeyboardButton("📍 موقعي")],
        [KeyboardButton("💰 محفظتي"), KeyboardButton("📞 تواصل مع الإدارة")]
    ], resize_keyboard=True)

# ==================== 🤖 4. المعالجات (Handlers) ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name

    context.user_data.clear()

    if context.args:
        arg_value = context.args[0]

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
                            reply_markup=InlineKeyboardMarkup(kb),
                            parse_mode=ParseMode.MARKDOWN
                        )
                    else:
                        await update.message.reply_text(
                            f"📍 حي {selected_dist} لا يوجد به كباتن حالياً، جرب طلب مشوار عام بالـ GPS.", 
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🌍 طلب GPS", callback_data="order_general")]])
                        )
                return 
            except Exception as e:
                logger.error(f"Error in sd_ deep link: {e}")

        elif arg_value == "reg_rider":
            await auto_register_rider(update) 
            await update.message.reply_text(
                f"🎉 **حياك الله يا {first_name}!**\nتم تسجيل دخولك كراكب بنجاح.",
                reply_markup=get_main_kb('rider', True),
                parse_mode=ParseMode.MARKDOWN
            )
            return

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
                logger.error(f"Error in order_ ID: {e}")

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

async def register_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    data = query.data
    user_id = user.id
    await query.answer()

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

    elif data == "driver_home":
        user_info = USER_CACHE.get(user_id, {})
        saved_dists = user_info.get('districts', "لا توجد أحياء مختارة")
        if not saved_dists: saved_dists = "لا توجد أحياء مختارة"

        confirm_text = (
            "✅ **تم حفظ الأحياء بنجاح!**\n\n"
            f"📍 نطاق عملك الحالي:\n_{saved_dists}_\n\n"
            "يمكنك الآن استقبال الطلبات من الركاب في هذه المناطق."
        )

        await query.edit_message_text(
            text=confirm_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=None
        )

        await context.bot.send_message(
            chat_id=user_id,
            text="الآن، يمكنك العودة لمهامك من القائمة أدناه:",
            reply_markup=get_main_kb('driver', user_info.get('is_verified', True))
        )

    elif data.startswith("final_start_"):
        parts = data.split("_")
        driver_id = int(parts[2])
        price = float(parts[3])
        rider_id = user_id

        await sync_all_users()
        driver_info = USER_CACHE.get(driver_id)
        rider_info = USER_CACHE.get(rider_id)

        commission_amount = deduct_commission(driver_id, price)

        admin_msg = (
            f"🚕 **تقرير رحلة جديدة**\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👤 **الراكب:** {rider_info['name']} (`{rider_id}`)\n"
            f"👨‍✈️ **السائق:** {driver_info['name']} (`{driver_id}`)\n"
            f"🚗 **السيارة:** {driver_info.get('car_info', 'غير مسجلة')}\n"
            f"💰 **سعر الرحلة:** {price} ريال\n"
            f"📉 **العمولة المخصومة (15%):** {commission_amount:.2f} ريال\n"
            f"📅 **الوقت:** {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        try:
            for admin_id in ADMIN_IDS:
                await context.bot.send_message(chat_id=admin_id, text=admin_msg, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Admin notification failed: {e}")

        start_chat_session(driver_id, rider_id)

        chat_kb = ReplyKeyboardMarkup([
            [KeyboardButton("📍 مشاركة الموقع", request_location=True)],
            [KeyboardButton("❌ إنهاء المحادثة")]
        ], resize_keyboard=True)

        await query.edit_message_text(f"✅ تم تأكيد الرحلة وخصم الرسوم.\nيمكنك الآن مراسلة الكابتن {driver_info['name']}.")

        await context.bot.send_message(
            chat_id=driver_id, 
            text=f"✅ الراكب أكد الرحلة!\nتم خصم عمولة {commission_amount:.2f} ريال.\nيمكنك الآن التحدث معه.",
            reply_markup=chat_kb
        )

    elif data == "order_general":
        context.user_data['state'] = "WAITING_DETAILS"
        await query.edit_message_text("📝 يرجى كتابة تفاصيل المشوار:")

    elif data.startswith("accept_gen_") or data.startswith("accept_ride_"):
        parts = data.split("_")
        rider_id = int(parts[2])
        price = float(parts[3])
        await process_accept_ride(update, context, rider_id, price)
        return

    elif data.startswith("searchdist_"):
        target_dist = data.split("_")[1]
        await sync_all_users()

        def clean(t): return t.replace("ة", "ه").replace("أ", "ا").replace("إ", "ا").strip()
        target_clean = clean(target_dist)

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
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "🌍 أقرب كابتن (بحث بالموقع)", 
                        url=f"https://t.me/{context.bot.username}?start=order_general"
                    )
                ]]),
                parse_mode=ParseMode.MARKDOWN
            )

    elif data == "manage_districts":
        districts = CITIES_DISTRICTS.get("المدينة المنورة", [])
        user_info = USER_CACHE.get(user_id, {})
        current_dists = user_info.get('districts', "") or ""

        keyboard = []
        for d in districts:
            status = "✅ " if d in current_dists else "❌ "
            keyboard.append([InlineKeyboardButton(f"{status}{d}", callback_data=f"toggle_{d}")])

        keyboard.append([InlineKeyboardButton("💾 حفظ وإنهاء", callback_data="driver_home")])
        await query.edit_message_text("📝 اختر الأحياء التي تعمل بها (اضغط للتبديل):", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("verify_ok_"):
        target_driver_id = int(data.split("_")[2])

        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET is_verified = True WHERE user_id = %s", (target_driver_id,))
                conn.commit()
            conn.close()

            await sync_all_users(force=True)
            await query.edit_message_text(f"✅ تم تفعيل حساب الكابتن ({target_driver_id}) بنجاح.")

            try:
                await context.bot.send_message(
                    chat_id=target_driver_id,
                    text="🎉 **أبشرك يا كابتن!**\nتم مراجعة حسابك وتفعيله بنجاح. يمكنك الآن استقبال الطلبات وتحديث أحيائك.",
                    reply_markup=get_main_kb('driver', True)
                )
            except: pass

    elif data.startswith("verify_no_"):
        target_driver_id = int(data.split("_")[2])
        await query.edit_message_text(f"❌ تم رفض طلب انضمام الكابتن ({target_driver_id}).")
        try:
            await context.bot.send_message(
                chat_id=target_driver_id,
                text="⚠️ نعتذر منك يا كابتن، تم رفع طلب انضمامك حالياً. يمكنك التواصل مع الإدارة للاستفسار."
            )
        except: pass

    elif data.startswith("toggle_"):
        dist_name = data.split("_")[1]
        user_info = USER_CACHE.get(user_id, {})
        current_str = user_info.get('districts', "") or ""
        current_list = [x.strip() for x in current_str.replace("،", ",").split(",") if x.strip()]

        if dist_name in current_list:
            current_list.remove(dist_name)
            alert_msg = f"❌ تم إزالة {dist_name}"
        else:
            current_list.append(dist_name)
            alert_msg = f"✅ تم إضافة {dist_name}"

        new_districts_str = ",".join(current_list)
        USER_CACHE[user_id]['districts'] = new_districts_str

        districts = CITIES_DISTRICTS.get("المدينة المنورة", [])
        keyboard = []
        for i in range(0, len(districts), 2):
            row = []
            for d in districts[i:i+2]:
                status = "✅ " if d in current_list else "❌ "
                row.append(InlineKeyboardButton(f"{status}{d}", callback_data=f"toggle_{d}"))
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("💾 حفظ وإنهاء", callback_data="driver_home")])

        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        await query.answer(alert_msg)
        update_districts_in_db(user_id, new_districts_str)

    elif data in ["reg_rider", "reg_driver"]:
        role = "rider" if data == "reg_rider" else "driver"
        context.user_data['reg_role'] = role
        if role == "rider":
            await query.edit_message_text(text="⏳ جاري إنشاء حسابك كراكب...")
            await complete_registration(update, context, f"{user.first_name} {user.last_name or ''}".strip())
        else:
            context.user_data['state'] = 'WAIT_NAME'
            await query.edit_message_text(text="📝 يرجى كتابة **اسمك الثلاثي** الآن:", parse_mode=ParseMode.MARKDOWN)

async def complete_registration(update, context, name):
    user = update.effective_user
    user_id = user.id
    chat_id = update.effective_chat.id
    username = f"@{user.username}" if user.username else "لا يوجد معرف"

    role = context.user_data.get('reg_role')
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

        if role == 'driver':
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ **أبشرك تم استلام طلبك يا كابتن {name}**\n\nحسابك الحين تحت المراجعة، وأول ما يتفعل بيجيك إشعار. خلك قريب!",
                reply_markup=get_main_kb('driver', False)
            )

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
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎉 **يا هلا بيك يا {name}**\nتم تفعيل حسابك كراكب بنجاح، تقدر تطلب مشاويرك من الحين!",
                reply_markup=get_main_kb('rider', True)
            )

    except Exception as e:
        logger.error(f"Error registration: {e}")
        try:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ حدث خطأ أثناء التسجيل، جرب مرة ثانية.")
        except: pass
    finally:
        conn.close()

async def process_accept_ride(update: Update, context: ContextTypes.DEFAULT_TYPE, rider_id: int, price: float):
    query = update.callback_query
    driver_id = update.effective_user.id

    await sync_all_users()
    driver_info = USER_CACHE.get(driver_id)

    if not driver_info:
        await query.answer("⚠️ حدث خطأ في جلب بياناتك كابتن.", show_alert=True)
        return

    kb_for_rider = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تأكيد الرحلة وفتح الشات", callback_data=f"final_start_{driver_id}_{price}"),
            InlineKeyboardButton("❌ إلغاء الطلب", callback_data=f"reject_ride_{driver_id}")
        ]
    ])

    try:
        await context.bot.send_message(
            chat_id=rider_id,
            text=(
                f"🎉 **كابتن متاح الآن لمشوارك!**\n\n"
                f"👤 **الكابتن:** {driver_info['name']}\n"
                f"🚗 **السيارة:** {driver_info.get('car_info', 'غير محددة')}\n"
                f"💰 **السعر المعروض:** {price} ريال\n\n"
                f"هل تود اعتماد هذا الكابتن وبدء التواصل معه؟"
            ),
            reply_markup=kb_for_rider,
            parse_mode=ParseMode.MARKDOWN
        )

        await query.edit_message_text(f"⏳ تم إرسال عرضك للراكب بقيمة {price} ريال.\nبانتظار تأكيده لفتح المحادثة.")

    except Exception as e:
        logger.error(f"Error notifying rider: {e}")
        await query.edit_message_text("❌ تعذر إرسال الإشعار للراكب (ربما قام بحظر البوت).")

async def handle_ride_order_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get('state')
    text = update.message.text
    user_id = update.effective_user.id

    if state == "WAITING_DETAILS":
        context.user_data['search_district'] = text
        context.user_data['state'] = "WAITING_PRICE"
        await update.message.reply_text("💰 **الخطوة [2/3]:** كم السعر الذي تعرضه لهذا المشوار؟")

    elif state == "WAITING_PRICE":
        if not text.isdigit():
            await update.message.reply_text("⚠️ يرجى إرسال السعر كأرقام فقط (مثلاً: 40).")
            return

        context.user_data['order_price'] = text
        context.user_data['state'] = "WAITING_LOCATION"

        kb = ReplyKeyboardMarkup([
            [KeyboardButton("📍 إرسال موقعي الآن لبدء البحث", request_location=True)]
        ], resize_keyboard=True, one_time_keyboard=True)

        await update.message.reply_text("📍 **الخطوة [3/3]:** أخيراً، يرجى إرسال موقعك للبحث عن أقرب كابتن:", reply_markup=kb)

async def handle_location_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.location and context.user_data.get('state') == "WAITING_LOCATION":
        context.user_data['lat'] = update.message.location.latitude
        context.user_data['lon'] = update.message.location.longitude

        await update.message.reply_text("🔍 جاري البحث عن كباتن في نطاق 5 كم وإرسال طلبك...")

        drivers_count = await broadcast_general_order(update, context)

        if drivers_count > 0:
            await update.message.reply_text(f"✅ تم إرسال طلبك إلى {drivers_count} كابتن قريب منك. انتظر قبول أحدهم.")
        else:
            await update.message.reply_text("⚠️ عذراً، لم نجد كباتن متاحين حالياً في نطاق 5 كم حول موقعك.")

        context.user_data['state'] = None

async def order_ride_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ كابتن نخبة (بحث بالحي)", callback_data="order_by_district")],
        [InlineKeyboardButton("🌍 أقرب كابتن (بحث بالموقع)", callback_data="order_general")]
    ])
    await update.message.reply_text("🚖 **كيف تود البحث عن الكابتن؟**", reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

async def broadcast_general_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال الطلب للكباتن في نطاق 5 كم فقط"""
    if update.message and update.message.location:
        r_lat = update.message.location.latitude
        r_lon = update.message.location.longitude
    else:
        r_lat = context.user_data.get('lat')
        r_lon = context.user_data.get('lon')

    if r_lat is None or r_lon is None:
        return 0

    price = context.user_data.get('order_price', 0)
    details = context.user_data.get('search_district', "موقع GPS")
    rider_id = update.effective_user.id

    count = 0
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

    context.user_data.clear()

    await sync_all_users()
    user = USER_CACHE.get(user_id)
    role = user['role'] if user else 'rider'
    is_v = user.get('is_verified', True) if user else True

    await update.message.reply_text(
        "🛑 تم إنهاء المحادثة والعودة للقائمة الرئيسية.",
        reply_markup=get_main_kb(role, is_v)
    )

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
            logger.error(f"Error notifying partner: {e}")

async def global_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return

    user = update.effective_user
    user_id = user.id
    state = context.user_data.get('state')
    text = update.message.text if update.message.text else ""

    # ---------------------------------------------------------
    # [الفلتر الأول] المحادثات النشطة (Chat Relay)
    # ---------------------------------------------------------
    if get_chat_partner(user_id):
        return 

    # ---------------------------------------------------------
    # [الفلتر الثاني] معالجة الموقع (Location)
    # ---------------------------------------------------------
    if update.message.location:
        await location_handler(update, context)
        return

    # ---------------------------------------------------------
    # [الفلتر الثالث] معالجة حالات البوت (States)
    # ---------------------------------------------------------
    if state:
        if state == 'WAIT_NAME':
            context.user_data['reg_name'] = text
            context.user_data['state'] = 'WAIT_PHONE'
            await update.message.reply_text("📱 **أبشر، الحين أرسل رقم جوالك:**\n(مثال: 05xxxxxxxx)")
            return

        if state == 'WAIT_PHONE':
            phone_input = text.strip()
            if not re.fullmatch(r'05\d{8}', phone_input):
                await update.message.reply_text("⚠️ **الرقم غير صحيح..**\nلازم يبدأ بـ 05 ويتكون من 10 أرقام.")
                return

            context.user_data['reg_phone'] = phone_input
            await complete_registration(update, context, context.user_data['reg_name'])
            context.user_data['state'] = None
            return

        if state == 'WAIT_TRIP_DETAILS':
            context.user_data['trip_details'] = text 
            context.user_data['state'] = 'WAIT_TRIP_PRICE'
            await update.message.reply_text("💰 **كم السعر المعروض؟** (أرقام فقط):")
            return

        if state == 'WAIT_TRIP_PRICE':
            if not text.isdigit():
                await update.message.reply_text("⚠️ أرقام فقط لو سمحت.")
                return

            price = text
            details = context.user_data.get('trip_details')
            driver_id = context.user_data.get('driver_to_order')

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

        if state == 'WAIT_ADMIN_MESSAGE':
            if text == "❌ إلغاء المراسلة":
                context.user_data['state'] = None
                await update.message.reply_text("تم الإلغاء.", reply_markup=get_main_kb(context.user_data.get('role', 'rider')))
                return
            pass 

    # ---------------------------------------------------------
    # [الفلتر الرابع] أوامر القائمة الرئيسية (Buttons)
    # ---------------------------------------------------------
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
             expiry = user_data['subscription_expiry']
             fmt_date = expiry.strftime('%Y-%m-%d') if hasattr(expiry, 'strftime') else str(expiry)
             await update.message.reply_text(f"📅 اشتراكك ينتهي في: {fmt_date}")
        else:
             await update.message.reply_text("❌ ليس لديك اشتراك فعال.")
        return

    if text == "❌ إلغاء الطلب":
        context.user_data['state'] = None
        await update.message.reply_text("تم الإلغاء.", reply_markup=get_main_kb(context.user_data.get('role', 'rider')))
        return

    # ---------------------------------------------------------
    # [المرحلة النهائية] إرسال الرسائل المجهولة للأدمن
    # ---------------------------------------------------------
    if update.message.chat.type == "private":
        admin_text = (
            f"📩 **رسالة واردة (دعم فني)**\n"
            f"👤 الاسم: {user.full_name}\n"
            f"🆔 ID: `{user_id}`\n"
            f"🔗 المعرف: @{user.username if user.username else 'لا يوجد'}\n"
            f"📝 النص: {text}\n"
            f"─────────────────\n"
            f"💡 للرد عليه، قم بعمل (Reply) على هذه الرسالة."
        )

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🚫 حظر", callback_data=f"admin_block_{user_id}"),
                InlineKeyboardButton("💰 شحن", callback_data=f"admin_quickcash_{user_id}")
            ]
        ])

        for aid in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=aid, text=admin_text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
                await context.bot.copy_message(chat_id=aid, from_chat_id=user_id, message_id=update.message.message_id)
            except: pass

        save_chat_log(user_id, ADMIN_IDS[0], text or "[ملف/موقع]", "support_msg")
        await update.message.reply_text("📨 تم استلام رسالتك وتحويلها لفريق الدعم.")

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    location = update.message.location
    state = context.user_data.get('state')

    partner_id = get_chat_partner(user_id)
    if partner_id:
        try:
            await context.bot.copy_message(
                chat_id=partner_id,
                from_chat_id=user_id,
                message_id=update.message.message_id
            )
            msg_content = f"📍 موقع: {location.latitude}, {location.longitude}"
            conn = get_db_connection()
            if conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO chat_logs (sender_id, receiver_id, message_content, msg_type) VALUES (%s, %s, %s, %s)",
                                (int(user_id), int(partner_id), msg_content, "location"))
                    conn.commit()
                conn.close()
            return
        except Exception as e:
            logger.error(f"❌ فشل تمرير الموقع للمشترك: {e}")

    context.user_data['lat'] = location.latitude
    context.user_data['lon'] = location.longitude
    threading.Thread(target=update_db_location, args=(user_id, location.latitude, location.longitude)).start()

    await sync_all_users() 
    user_data = USER_CACHE.get(user_id, {})
    user_role = user_data.get('role', 'rider')
    is_verified = user_data.get('is_verified', False)

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
        context.user_data['state'] = None
    else:
        await update.message.reply_text(
            "📍 تم تحديث موقعك الجغرافي بنجاح.",
            reply_markup=get_main_kb(user_role, is_verified)
        )

async def show_districts_by_city(update: Update, context: ContextTypes.DEFAULT_TYPE, city_name: str = "المدينة المنورة"):
    query = update.callback_query
    user_id = update.effective_user.id

    try: await query.answer()
    except: pass

    conn = get_db_connection()
    current_districts = []
    if conn:
        with conn.cursor() as cur:
            cur.execute("SELECT districts FROM users WHERE user_id = %s", (user_id,))
            res = cur.fetchone()
            if res and res[0]:
                current_districts = [d.strip() for d in res[0].replace("،", ",").split(",") if d.strip()]
        conn.close()

    all_districts = CITIES_DISTRICTS.get(city_name, [])

    keyboard = []
    for i in range(0, len(all_districts), 2):
        row = []
        for j in range(2):
            if i + j < len(all_districts):
                dist_name = all_districts[i + j]
                status = "✅ " if dist_name in current_districts else "⬜ "
                row.append(InlineKeyboardButton(f"{status}{dist_name}", callback_data=f"toggle_dist_{dist_name}"))
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("🏁 حفظ وإغلاق", callback_data="main_menu")])

    text = (
        f"🏙 **إعدادات العمل في {city_name}:**\n\n"
        "اضغط على الحي لتفعيله أو تعطيله:\n"
        "✅ = ستصلك طلبات هذا الحي\n"
        "⬜ = لن تصلك طلبات هذا الحي"
    )

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error in show_districts: {e}")

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id

    try: await query.answer()
    except: pass

    if data == "districts_settings":
        await show_districts_by_city(update, context, "المدينة المنورة")
        return

    elif data.startswith("toggle_dist_"):
        dist_name = data.replace("toggle_dist_", "")
        city_name = context.user_data.get('current_managing_city')

        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute("SELECT districts FROM users WHERE user_id = %s", (user_id,))
                res = cur.fetchone()
                current_list = []
                if res and res[0]:
                    current_list = [x.strip() for x in res[0].replace("،", ",").split(",") if x.strip()]

                if dist_name in current_list:
                    current_list.remove(dist_name)
                else:
                    current_list.append(dist_name)

                new_districts_str = "، ".join(current_list)
                cur.execute("UPDATE users SET districts = %s WHERE user_id = %s", (new_districts_str, user_id))
                conn.commit()
            conn.close()

            await sync_all_users(force=True)

            if city_name:
                await show_districts_by_city(update, context, city_name)
            else:
                await districts_settings_view(update, context)
        return

    elif data == "save_districts":
        await query.edit_message_text(
            "✅ **تم حفظ مناطق عملك بنجاح!**\nسيصلك إشعار فور طلب أي مشوار في هذه الأحياء.\n\nشكراً لك يا كابتن.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    elif data == "order_by_district":
        districts = CITIES_DISTRICTS.get("المدينة المنورة", [])
        if not districts:
            await query.answer("⚠️ قائمة الأحياء غير متوفرة حالياً.")
            return

        keyboard = []
        for i in range(0, len(districts), 2):
            row = []
            dist1 = districts[i]
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

    elif data.startswith("searchdist_"):
        target_dist = data.replace("searchdist_", "")
        await sync_all_users()

        def clean(t): 
            return t.replace("ة", "ه").replace("أ", "ا").replace("إ", "ا").replace(" ", "").strip()

        target_clean = clean(target_dist)
        matched_drivers = []

        for d in CACHED_DRIVERS:
            if d.get('role') == 'driver' and d.get('districts'):
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

    elif data == "order_general":
        context.user_data['state'] = 'WAIT_GENERAL_DETAILS' 
        await query.edit_message_text(
            "🌍 **البحث عن أقرب كابتن (GPS):**\n\n"
            "📝 يرجى كتابة **تفاصيل مشوارك** الآن (من وين لوين؟):",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    elif data.startswith("accept_ride_") or data.startswith("accept_gen_"):
        parts = data.split("_")
        rider_id = int(parts[2])
        price = float(parts[3])
        driver_id = user_id

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
                    if current_bal >= -5: 
                        can_accept = True
            conn.close()

        if not can_accept:
            await query.answer("⚠️ رصيدك غير كافٍ! يرجى شحن المحفظة.", show_alert=True)
            return

        await query.edit_message_text("⏳ تم إرسال موافقتك للعميل.. بانتظار تأكيده لفتح المحادثة.")

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

    elif data.startswith("final_start_"):
        parts = data.split("_")
        driver_id = int(parts[2])
        price = float(parts[3])
        rider_id = user_id
        commission = price * 0.10

        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET balance = balance - %s WHERE user_id = %s", (commission, driver_id))
                conn.commit()
            conn.close()

        start_chat_session(driver_id, rider_id)

        admin_msg = (
            f"💰 **عملية ناجحة**\n"
            f"👤 راكب: `{rider_id}` | 🚖 كابتن: `{driver_id}`\n"
            f"💵 السعر: {price} | 📉 العمولة: {commission}"
        )
        for aid in ADMIN_IDS:
            try: await context.bot.send_message(chat_id=aid, text=admin_msg, parse_mode=ParseMode.MARKDOWN)
            except: pass

        kb_chat = ReplyKeyboardMarkup([
            [KeyboardButton("📍 مشاركة موقعي الحالي", request_location=True)],
            [KeyboardButton("❌ إنهاء المحادثة")]
        ], resize_keyboard=True)

        await query.edit_message_text("✅ تم بدء الرحلة وفتح الخط مع الكابتن.")
        await context.bot.send_message(
            chat_id=rider_id, 
            text="🟢 **أنت الآن في محادثة مباشرة مع الكابتن.**\nيمكنك إرسال موقعك أو الكتابة له هنا.", 
            reply_markup=kb_chat,
            parse_mode=ParseMode.MARKDOWN
        )

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

    elif data.startswith("book_"):
        parts = data.split("_")
        driver_id = parts[1]
        dist_name = parts[2] if len(parts) > 2 else "المحدد"

        if update.effective_chat.type != "private":
            bot_username = context.bot.username
            url = f"https://t.me/{bot_username}?start=order_{driver_id}"

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
            context.user_data.update({
                'driver_to_order': driver_id,
                'state': 'WAIT_TRIP_DETAILS'
            })
            await query.edit_message_text("📝 **اكتب تفاصيل مشوارك الآن:**")

        return

    elif data.startswith("reject_ride_"):
        target_id = int(data.split("_")[2])
        await query.edit_message_text("❌ تم رفض الطلب.")
        try:
            await context.bot.send_message(chat_id=target_id, text="❌ عذراً، تم رفض/إلغاء الطلب من الطرف الآخر.")
        except: pass
        return

    if data.startswith("admin_block_"):
        target_id = int(data.split("_")[2])
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

    elif data.startswith("verify_"):
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

        msg = "🎉 تهانينا! تم توثيق حسابك ككابتن." if is_verified else "❌ تم رفض طلب توثيق حسابك. تواصل مع الإدارة."
        try:
            markup = get_main_kb('driver', is_verified)
            await context.bot.send_message(chat_id=target_uid, text=msg, reply_markup=markup)
        except: pass

        await sync_all_users(force=True) 
        return

async def districts_settings_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_districts_by_city(update, context, "المدينة المنورة")

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    message_text = " ".join(context.args)
    if not message_text:
        await update.message.reply_text("⚠️ خطأ في الاستخدام!\nاكتب الرسالة بعد الأمر، مثال:\n`/broadcast نعتذر عن توقف الخدمة للصيانة`", parse_mode=ParseMode.MARKDOWN)
        return

    await update.message.reply_text(f"⏳ جاري إرسال الرسالة إلى جميع المشتركين... يرجى عدم إيقاف البوت.")

    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ فشل الاتصال بقاعدة البيانات.")
        return

    users_list = []
    with conn.cursor() as cur:
        cur.execute("SELECT user_id FROM users")
        users_list = [row[0] for row in cur.fetchall()]
    conn.close()

    success_count = 0
    block_count = 0

    for uid in users_list:
        try:
            final_msg = f"📢 **تنبيه هام من الإدارة:**\n\n{message_text}"
            await context.bot.send_message(chat_id=uid, text=final_msg, parse_mode=ParseMode.MARKDOWN)
            success_count += 1
        except Exception:
            block_count += 1

    report = (
        f"✅ **تم انتهاء الإذاعة!**\n"
        f"─────────────────\n"
        f"📩 تم الاستلام: {success_count} عضو\n"
        f"🚫 محظور/فاشل: {block_count} عضو\n"
        f"👥 المجموع الكلي: {len(users_list)}"
    )
    await update.message.reply_text(report, parse_mode=ParseMode.MARKDOWN)

async def admin_add_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    if update.effective_user.id not in ADMIN_IDS: return
    try:
        uid = int(context.args[0])
        amount = float(context.args[1])

        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (amount, uid))
            conn.commit()
        conn.close()

        await sync_all_users(force=True)

        await update.message.reply_text(f"✅ تم إضافة {amount} ريال للعضو {uid}.")

        new_balance = USER_CACHE.get(uid, {}).get('balance', 0)

        await context.bot.send_message(
            chat_id=uid, 
            text=f"💰 **تم شحن رصيدك بنجاح!**\n\nالمبلغ المضاف: {amount} ريال\nرصيدك الحالي الآن: {new_balance} ريال"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: تأكد من الصيغة /cash [ID] [Amount]\n{e}")

async def group_order_scanner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    text = update.message.text
    msg_clean = text.lower().replace("ة", "ه").replace("أ", "ا").replace("إ", "ا")

    FORBIDDEN = ["شهري", "عقد", "راتب", "دوام"]
    if any(k in msg_clean for k in FORBIDDEN):
        contact_url = f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"
        mention = f"@{user.username}" if user.username else "لا يوجد معرف"

        admin_info = (
            f"📋 **طلب شهري محول للأدمن**\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👤 **الاسم:** {user.full_name}\n"
            f"🆔 **المعرف:** {mention}\n"
            f"💬 **الطلب:**\n_{text}_"
        )

        admin_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 مراسلة العضو", url=contact_url)]
        ])

        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_info,
                    reply_markup=admin_kb,
                    parse_mode="Markdown"
                )
            except:
                pass

        try:
            await update.message.reply_text(f"✅ أبشر يا {user.first_name}، تم تحويل طلبك للإدارة وسيتم التواصل معك.")
        except:
            pass

        try:
            await update.message.delete()
        except Exception as e:
            logger.error(f"فشل حذف الرسالة: {e}")
            
        return

    KEYWORDS = [
        "مشوار", "توصيل", "سائق", "سواق", "كابتن", "سيارة", "سياره", "موتر",
        "وينك", "متاح", "مطلوب", "ابي", "بغيت", "محتاج", "احتاج", "أدور", 
        "أدري", "في أحد", "فيه أحد", "يوديني", "يوصلني", "متوفر", "ممكن",
        "الحرم", "النبوي", "قباء", "المطار", "القطار", "الميقات", "سيد الشهداء",
        "حجز", "خاص", "توصيله", "طريق", "فزعة"
    ]

    is_order_request = any(k in msg_clean for k in KEYWORDS)

    found_dist = None
    districts_list = CITIES_DISTRICTS.get("المدينة المنورة", [])
    for dist in districts_list:
        clean_dist = dist.replace("ة", "ه").replace("أ", "ا").replace("إ", "ا")
        if clean_dist in msg_clean:
            found_dist = dist
            break

    if not found_dist:
        if is_order_request:
            keyboard = []
            for i in range(0, len(districts_list), 3):
                row = []
                for j in range(3):
                    if i + j < len(districts_list):
                        d = districts_list[i + j]
                        row.append(InlineKeyboardButton(d, callback_data=f"searchdist_المدينة المنورة_{d}"))
                keyboard.append(row)

            await update.message.reply_text(
                f"يا هلا بك يا {user.first_name} ✨\nحدد **الحي** في المدينة المنورة لإرسال طلبك للكباتن:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            welcome_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚕 التسجيل ككابتن", url=f"https://t.me/{context.bot.username}?start=driver_reg"),
                 InlineKeyboardButton("📱 طلب رحلة", url=f"https://t.me/{context.bot.username}?start=order_general")]
            ])
            await update.message.reply_text(f"مرحباً بك في **مشواري المدينة** 🌴\nلطلب مشوار أو التسجيل استخدم الأزرار:", reply_markup=welcome_kb, parse_mode=ParseMode.MARKDOWN)
        return

    await sync_all_users()
    matched_drivers = [d for d in CACHED_DRIVERS if d.get('districts') and found_dist.replace("ة", "ه") in d['districts'].replace("ة", "ه")]

    if matched_drivers:
        kb = [[InlineKeyboardButton(f"🚖 اطلب {d['name']}", url=f"https://t.me/{context.bot.username}?start=order_{d['user_id']}")] for d in matched_drivers[:5]]
        await update.message.reply_text(f"✅ وجدنا كباتن في حي **{found_dist}**:", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    else:
        search_link = f"https://t.me/{context.bot.username}?start=order_general"
        await update.message.reply_text(f"📍 حي {found_dist}: لا يوجد كباتن مسجلين حالياً، جرب البحث بالـ GPS:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🌍 بحث GPS", url=search_link)]]))

async def admin_send_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    context.user_data['state'] = 'WAIT_ADMIN_MESSAGE'
    await update.message.reply_text(
        "📝 **أرسل رسالتك أو شكواك الآن في رسالة واحدة:**",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ إلغاء المراسلة")]], resize_keyboard=True)
    )

async def admin_get_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

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

    if not partner_id:
        return 
    
    text = update.message.text

    if text and (text.startswith('/') or text == "❌ إنهاء المحادثة"):
        return 

    partner_id = get_chat_partner(user_id)
    if not partner_id: return 

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
            logger.error(f"❌ خطأ في حفظ SQL: {e}")
        finally:
            conn.close()

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
        logger.error(f"❌ فشل النقل: {e}")

    raise ApplicationHandlerStop

async def admin_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    msg_text = update.message.text or "[ملف/صورة]"

    if chat_id in ADMIN_IDS and update.message.reply_to_message:
        original_msg = update.message.reply_to_message.text or update.message.reply_to_message.caption
        if not original_msg: return

        try:
            target_user_id = int(re.search(r"ID:\s*`?(\d+)`?", original_msg).group(1))

            await context.bot.copy_message(
                chat_id=target_user_id,
                from_chat_id=chat_id,
                message_id=update.message.message_id
            )

            save_chat_log(chat_id, target_user_id, msg_text, "admin_reply")
            await update.message.reply_text(f"✅ تم إرسال الرد وحفظه في السجل.")

        except AttributeError:
             await update.message.reply_text("⚠️ لم أتمكن من استخراج ID العضو. تأكد أنك ترد على رسالة البوت التي تحتوي على البيانات.")
        except Exception as e:
            await update.message.reply_text(f"❌ حدث خطأ: {e}")
        return

async def show_districts_to_driver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    districts = CITIES_DISTRICTS.get("المدينة المنورة", [])

    await sync_all_users()
    user_info = USER_CACHE.get(user_id, {})
    current_dists = user_info.get('districts', "") or ""

    keyboard = []
    for i in range(0, len(districts), 2):
        row = []
        for d in districts[i:i+2]:
            status = "✅ " if d in current_dists else "❌ "
            row.append(InlineKeyboardButton(f"{status}{d}", callback_data=f"toggle_{d}"))
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("💾 حفظ وإنهاء", callback_data="driver_home")])

    await update.message.reply_text(
        "📝 **إدارة نطاق العمل:**\nاختر الأحياء التي تعمل بها ليتمكن الركاب من العثور عليك:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def group_districts_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    districts = CITIES_DISTRICTS.get("المدينة المنورة", [])
    if not districts: return

    keyboard = []
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

# ==================== 🏁 6. التشغيل الرئيسي ====================
def main():
    threading.Thread(target=run_flask, daemon=True).start()
    init_db()

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # المجموعة 0: الأوامر والعمليات الفورية
    application.add_handler(CommandHandler("start", start_command), group=0)
    application.add_handler(CommandHandler("cash", admin_cash), group=0)
    application.add_handler(CommandHandler("sub", admin_add_days), group=0)
    application.add_handler(CommandHandler("broadcast", admin_broadcast), group=0)
    application.add_handler(CommandHandler("logs", admin_get_logs), group=0)
    application.add_handler(CommandHandler("send", admin_send_to_user), group=0)

    application.add_handler(CallbackQueryHandler(register_callback), group=0)
    application.add_handler(CallbackQueryHandler(handle_callbacks), group=0)

    application.add_handler(MessageHandler(filters.Regex("^(❌ إنهاء المحادثة|🛑 تم إنهاء المحادثة.)$"), end_chat_command), group=0)
    application.add_handler(MessageHandler(filters.Regex("^❌"), start_command), group=0)
    application.add_handler(MessageHandler(filters.Regex("^📝 تحديث الأحياء$"), show_districts_to_driver), group=0)
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex("^(احياء|الأحياء|الأحياء المتاحة)$"), group_districts_handler), group=0)

    # المجموعة 1: ردود الأدمن والنظام
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.REPLY & filters.User(ADMIN_IDS), 
        admin_reply_handler
    ), group=1)

    # المجموعة 2: إدارة الحالات
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, 
        handle_ride_order_flow
    ), group=2)

    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.LOCATION, 
        handle_location_receipt
    ), group=2)

    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, 
        global_handler
    ), group=2)

    # المجموعة 3: نظام التوجيه
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (filters.TEXT | filters.LOCATION) & ~filters.COMMAND,
        chat_relay_handler
    ), group=3)

    # المجموعة 4: المواقع والمجموعات العامة
    application.add_handler(MessageHandler(filters.LOCATION, location_handler), group=4)
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT, group_order_scanner), group=4)

    print("🚀 البوت يعمل الآن بنظام المجموعات (0 -> 4) بنجاح...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()