#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import asyncio
import uuid
import os
import asyncpg  # 👈 المكتبة الجديدة لـ Supabase
import math
from datetime import datetime
from enum import Enum

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InputMediaPhoto
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ApplicationBuilder
)
from telegram.constants import ParseMode

# ==================== ⚙️ الإعدادات ====================
BOT_TOKEN = "8588537913:AAH8FAoHAOEru1P8JqFh0khJ-WVDMoS32o8"  # 👈 توكن البوت

# 🛑 هام جداً: ضع رابط Supabase هنا
# يبدو الرابط مثل: postgresql://postgres:PASSWORD@db.xyz.supabase.co:5432/postgres
DB_URL = "postgresql://postgres:/dentmishwar123@db.sdbtyanzweljiaqjnqxd.supabase.co:5432/postgres" 

ADMIN_IDS = [8563113166, 7996171713]

# ثوابت العمل
COMMISSION_RATE = 0.15
DEBT_LIMIT = 50.0
SEARCH_RADIUS = 20
MAX_DRIVERS_NOTIFY = 15

def is_admin(user_id: int) -> bool:
    """التحقق من وجود المستخدم في قائمة الإدارة"""
    return user_id in ADMIN_IDS

# ==================== 🗄️ قاعدة البيانات (PostgreSQL) ====================
async def init_db():
    # إنشاء اتصال بقاعدة البيانات
    conn = await asyncpg.connect(DB_URL)
    try:
        # جدول المستخدمين
        # تم تغيير أنواع البيانات لتناسب PostgreSQL (BIGINT, DOUBLE PRECISION, BOOLEAN)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                chat_id BIGINT,
                role TEXT,
                name TEXT,
                phone TEXT,
                car_info TEXT,
                lat DOUBLE PRECISION DEFAULT 0.0,
                lon DOUBLE PRECISION DEFAULT 0.0,
                debt DOUBLE PRECISION DEFAULT 0.0,
                is_blocked BOOLEAN DEFAULT FALSE,
                is_verified BOOLEAN DEFAULT FALSE,
                photo_license TEXT,
                photo_car TEXT,
                photo_id_card TEXT,
                total_trips INTEGER DEFAULT 0,
                rating DOUBLE PRECISION DEFAULT 5.0,
                current_trip_id TEXT
            )
        ''')
        
        # جدول الرحلات
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS trips (
                trip_id TEXT PRIMARY KEY,
                rider_id BIGINT,
                driver_id BIGINT,
                pickup_lat DOUBLE PRECISION,
                pickup_lon DOUBLE PRECISION,
                dest_desc TEXT,
                price DOUBLE PRECISION DEFAULT 0.0,
                status TEXT,
                created_at TIMESTAMP,
                completed_at TIMESTAMP
            )
        ''')
        print("✅ Database Connected (Supabase PostgreSQL) Ready.")
    except Exception as e:
        print(f"❌ خطأ في الاتصال بقاعدة البيانات: {e}")
    finally:
        await conn.close()

# ==================== 🛠️ مساعدات ====================
class UserRole(str, Enum):
    RIDER = "rider"
    DRIVER = "driver"

class TripStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

def haversine(lat1, lon1, lat2, lon2):
    if not lat1 or not lat2: return 9999
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) * math.sin(dlat / 2) +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) * math.sin(dlon / 2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def get_main_kb(role, is_verified=True):
    if role == UserRole.DRIVER:
        # ملاحظة: في بايثون True هو 1، لذا الشرط يعمل
        if not is_verified:
            return ReplyKeyboardMarkup([[KeyboardButton("ℹ️ حالة الحساب: قيد المراجعة")]], resize_keyboard=True)
        return ReplyKeyboardMarkup([
            [KeyboardButton("📍 تحديث موقعي (بحث)"), KeyboardButton("💰 محفظتي")],
            [KeyboardButton("🛑 حالة العمل: متاح"), KeyboardButton("ℹ️ مساعدة")]
        ], resize_keyboard=True)
    else:
        return ReplyKeyboardMarkup([
            [KeyboardButton("🚖 طلب رحلة"), KeyboardButton("📍 موقعي")],
            [KeyboardButton("📜 سجل الرحلات"), KeyboardButton("ℹ️ مساعدة")]
        ], resize_keyboard=True)

# ==================== 🚀 المنطق الرئيسي ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = await asyncpg.connect(DB_URL)
    try:
        # استخدام $1 بدلاً من ?
        user = await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
        
        if user:
            if user['is_blocked']:
                await update.message.reply_text("⛔ حسابك محظور.")
                return
            
            verified = user['is_verified'] if user['role'] == 'driver' else True
            await update.message.reply_text(f"👋 أهلاً {user['name']}", reply_markup=get_main_kb(user['role'], verified))
        else:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("👤 أنا راكب", callback_data="reg_rider")],
                [InlineKeyboardButton("🚗 أنا سائق", callback_data="reg_driver")]
            ])
            await update.message.reply_text("👋 مرحباً بك.\nاختر نوع الحساب:", reply_markup=kb)
    finally:
        await conn.close()

async def register_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    role = UserRole.RIDER if query.data == "reg_rider" else UserRole.DRIVER
    context.user_data['reg_role'] = role
    context.user_data['state'] = 'WAIT_NAME'
    await query.edit_message_text(f"📝 تسجيل {'راكب' if role == 'rider' else 'سائق'}.\nالاسم الثلاثي:")

# --- معالج التسجيل والرسائل ---
async def global_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    state = context.user_data.get('state')

    # --- 1. التسجيل (نصي) ---
    if state == 'WAIT_NAME':
        context.user_data['reg_name'] = text
        if context.user_data['reg_role'] == UserRole.RIDER:
            await finalize_registration(update, context) 
        else:
            await update.message.reply_text("📱 رقم الهاتف للتواصل:")
            context.user_data['state'] = 'WAIT_PHONE'
        return

    elif state == 'WAIT_PHONE':
        context.user_data['reg_phone'] = text
        await update.message.reply_text("🚘 نوع وموديل ولون السيارة:")
        context.user_data['state'] = 'WAIT_CAR'
        return

    elif state == 'WAIT_CAR':
        context.user_data['reg_car'] = text
        await update.message.reply_text("📸 **مطلوب التوثيق**\nالرجاء إرسال **صورة رخصة القيادة** الآن:")
        context.user_data['state'] = 'WAIT_PHOTO_LICENSE'
        return

    # --- 2. التسجيل (صور) ---
    elif state in ['WAIT_PHOTO_LICENSE', 'WAIT_PHOTO_CAR', 'WAIT_PHOTO_ID']:
        if not update.message.photo:
            await update.message.reply_text("⚠️ الرجاء إرسال صورة فقط.")
            return
        
        photo_id = update.message.photo[-1].file_id 
        
        if state == 'WAIT_PHOTO_LICENSE':
            context.user_data['photo_license'] = photo_id
            await update.message.reply_text("📸 الآن أرسل **صورة السيارة** من الخارج:")
            context.user_data['state'] = 'WAIT_PHOTO_CAR'
            
        elif state == 'WAIT_PHOTO_CAR':
            context.user_data['photo_car'] = photo_id
            await update.message.reply_text("📸 أخيراً، أرسل **صورة الهوية الشخصية**:")
            context.user_data['state'] = 'WAIT_PHOTO_ID'
            
        elif state == 'WAIT_PHOTO_ID':
            context.user_data['photo_id_card'] = photo_id
            await update.message.reply_text("⏳ **تم استلام طلبك!**\nجاري مراجعة البيانات من قبل الإدارة. سيتم إشعارك عند التفعيل.")
            await finalize_registration_driver(update, context)
        return

    # --- 3. بقية العمليات ---
    elif state == 'WAIT_DESTINATION':
        context.user_data['dest_desc'] = text
        await update.message.reply_text("💰 **السعر المقترح (ريال)؟**")
        context.user_data['state'] = 'WAIT_PRICE'
        return
    elif state == 'WAIT_PRICE':
        try:
            price = float(text)
            if price < 5: return await update.message.reply_text("⚠️ السعر قليل.")
            await process_trip_request(update, context, price)
        except ValueError:
            await update.message.reply_text("❌ أرقام فقط.")
        return

    # الدردشة والقوائم
    conn = await asyncpg.connect(DB_URL)
    try:
        active_trip = await conn.fetchrow(
            "SELECT * FROM trips WHERE status='accepted' AND (rider_id=$1 OR driver_id=$2)", 
            user_id, user_id
        )
    finally:
        await conn.close()

    if active_trip:
        if text in ["/end", "انهاء", "تم"]: await manual_complete_trip(update, context)
        else: await relay_chat_message(update, context, active_trip)
        return

    if text == "🚖 طلب رحلة":
        await update.message.reply_text("📍 شارك موقعك:", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("📍 إرسال الموقع", request_location=True)]], resize_keyboard=True, one_time_keyboard=True))
        context.user_data['expect_location'] = 'pickup'
    elif text and "تحديث موقعي" in text:
        await update.message.reply_text("📍 تحديث الموقع:", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("📍 تحديث", request_location=True)]], resize_keyboard=True, one_time_keyboard=True))
        context.user_data['expect_location'] = 'update'
    elif text == "💰 محفظتي":
        await show_balance(update, context)

# --- إنهاء التسجيل ---
async def finalize_registration(update, context): # للركاب
    uid = update.effective_user.id
    name = context.user_data['reg_name']
    
    conn = await asyncpg.connect(DB_URL)
    try:
        # استخدام ON CONFLICT بدلاً من OR REPLACE
        await conn.execute("""
            INSERT INTO users (user_id, chat_id, role, name, is_verified)
            VALUES ($1, $2, 'rider', $3, TRUE)
            ON CONFLICT (user_id) DO UPDATE 
            SET name = EXCLUDED.name, chat_id = EXCLUDED.chat_id
        """, uid, update.effective_chat.id, name)
    finally:
        await conn.close()
        
    context.user_data.clear()
    await update.message.reply_text("✅ تم التسجيل.", reply_markup=get_main_kb(UserRole.RIDER))

async def finalize_registration_driver(update, context): # للسائقين
    uid = update.effective_user.id
    d = context.user_data
    
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute("""
            INSERT INTO users (user_id, chat_id, role, name, phone, car_info, photo_license, photo_car, photo_id_card, is_verified)
            VALUES ($1, $2, 'driver', $3, $4, $5, $6, $7, $8, FALSE)
            ON CONFLICT (user_id) DO UPDATE 
            SET name = EXCLUDED.name, phone = EXCLUDED.phone, car_info = EXCLUDED.car_info
        """, uid, update.effective_chat.id, d['reg_name'], d['reg_phone'], d['reg_car'], 
              d['photo_license'], d['photo_car'], d['photo_id_card'])
    finally:
        await conn.close()
    
    msg = f"🚨 **طلب توثيق سائق جديد**\n👤 الاسم: {d['reg_name']}\n🆔 UserID: `{uid}`"
    media = [
        InputMediaPhoto(d['photo_license'], caption="الرخصة"),
        InputMediaPhoto(d['photo_car'], caption="السيارة"),
        InputMediaPhoto(d['photo_id_card'], caption="الهوية")
    ]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ قبول وتفعيل", callback_data=f"verify_ok_{uid}")],
        [InlineKeyboardButton("❌ رفض وحظر", callback_data=f"verify_no_{uid}")]
    ])

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_media_group(chat_id=admin_id, media=media)
            await context.bot.send_message(chat_id=admin_id, text=msg, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            print(f"⚠️ فشل الإرسال للأدمن {admin_id}: {e}")

    context.user_data.clear()

# ==================== 👮 أدمن: معالجة التوثيق ====================

async def admin_verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action, target_id = query.data.split("_")[1], int(query.data.split("_")[2])
    
    conn = await asyncpg.connect(DB_URL)
    try:
        if action == "ok":
            await conn.execute("UPDATE users SET is_verified=TRUE, is_blocked=FALSE WHERE user_id=$1", target_id)
            await query.edit_message_text(f"✅ تم تفعيل السائق {target_id}")
            
            row = await conn.fetchrow("SELECT chat_id FROM users WHERE user_id=$1", target_id)
            if row: 
                await context.bot.send_message(row['chat_id'], "🎉 **مبروك!** تم توثيق حسابك بنجاح.", reply_markup=get_main_kb(UserRole.DRIVER, True))
        else:
            await conn.execute("UPDATE users SET is_verified=FALSE, is_blocked=TRUE WHERE user_id=$1", target_id)
            await query.edit_message_text(f"❌ تم رفض وحظر السائق {target_id}")
            
            row = await conn.fetchrow("SELECT chat_id FROM users WHERE user_id=$1", target_id)
            if row: await context.bot.send_message(row['chat_id'], "❌ نأسف، تم رفض طلبك.")
    finally:
        await conn.close()

# ==================== 📍 المنطق (مع التحقق) ====================

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lat, lon = update.message.location.latitude, update.message.location.longitude
    
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute("UPDATE users SET lat=$1, lon=$2 WHERE user_id=$3", lat, lon, user_id)
        user = await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
    finally:
        await conn.close()

    if context.user_data.get('expect_location') == 'pickup':
        context.user_data['pickup_coords'] = (lat, lon)
        context.user_data['state'] = 'WAIT_DESTINATION'
        context.user_data['expect_location'] = None
        await update.message.reply_text("📝 إلى أين؟", reply_markup=ReplyKeyboardRemove())
        return

    if user['role'] == UserRole.DRIVER:
        if not user['is_verified']:
            await update.message.reply_text("⏳ حسابك قيد المراجعة.")
            return
        if user['is_blocked'] or user['debt'] >= DEBT_LIMIT:
            await update.message.reply_text("❌ حسابك موقوف (ديون أو حظر).")
            return
        if user['current_trip_id']: return 

        # البحث عن طلبات
        conn = await asyncpg.connect(DB_URL)
        try:
            pending = await conn.fetch("SELECT * FROM trips WHERE status=$1", TripStatus.PENDING)
        finally:
            await conn.close()
        
        found = 0
        for trip in pending:
            dist = haversine(lat, lon, trip['pickup_lat'], trip['pickup_lon'])
            if dist <= SEARCH_RADIUS:
                found += 1
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"✅ قبول ({trip['price']} ريال)", callback_data=f"accept_{trip['trip_id']}")]])
                msg = f"🔔 **طلب!**\n📍 {trip['dest_desc']}\n💰 {trip['price']} ريال\n📏 {dist:.1f} كم"
                await update.message.reply_text(msg, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
        
        if found == 0: await update.message.reply_text("✅ تم التحديث. لا توجد طلبات قريبة.")
        context.user_data['expect_location'] = None

async def process_trip_request(update, context, price):
    rider_id = update.effective_user.id
    pickup = context.user_data['pickup_coords']
    dest = context.user_data['dest_desc']
    trip_id = str(uuid.uuid4())[:8]
    
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute("""
            INSERT INTO trips (trip_id, rider_id, pickup_lat, pickup_lon, dest_desc, price, status, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """, trip_id, rider_id, pickup[0], pickup[1], dest, price, TripStatus.PENDING, datetime.now())
    finally:
        await conn.close()
    
    admin_msg = f"🆕 طلب رحلة جديد:\n💰 السعر: {price} ريال\n📍 الوجهة: {dest}\n🆔 آيدي الراكب: `{rider_id}`"
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, admin_msg)
        except:
            continue
    context.user_data.clear()
    await update.message.reply_text("✅ تم النشر. جاري البحث عن كابتن...", reply_markup=get_main_kb(UserRole.RIDER))
    await broadcast_trip_to_drivers(context, trip_id, pickup, dest, price)

async def broadcast_trip_to_drivers(context, trip_id, pickup, dest, price):
    conn = await asyncpg.connect(DB_URL)
    try:
        drivers = await conn.fetch("""
            SELECT * FROM users 
            WHERE role=$1 AND is_blocked=FALSE AND is_verified=TRUE AND debt < $2 
            AND (current_trip_id IS NULL OR current_trip_id = '')
        """, UserRole.DRIVER, DEBT_LIMIT)
    finally:
        await conn.close()
            
    for driver in drivers:
        dist = haversine(pickup[0], pickup[1], driver['lat'], driver['lon'])
        if dist <= SEARCH_RADIUS:
            try:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"✅ قبول ({price})", callback_data=f"accept_{trip_id}")]])
                await context.bot.send_message(driver['chat_id'], f"🔔 **طلب!**\n📍 {dest}\n💰 {price}", reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
            except: pass

async def accept_trip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    trip_id = query.data.split("_")[1]
    driver_id = query.from_user.id
    
    conn = await asyncpg.connect(DB_URL)
    try:
        u = await conn.fetchrow("SELECT is_verified FROM users WHERE user_id=$1", driver_id)
        if not u or not u['is_verified']:
            await query.answer("❌ حسابك غير موثق.", show_alert=True)
            return

        trip = await conn.fetchrow("SELECT * FROM trips WHERE trip_id=$1", trip_id)
        if not trip or trip['status'] != TripStatus.PENDING:
            await query.answer("❌ راحت عليك!", show_alert=True)
            await query.edit_message_text("❌ انتهى العرض.")
            return

        await conn.execute("UPDATE trips SET driver_id=$1, status=$2 WHERE trip_id=$3", driver_id, TripStatus.ACCEPTED, trip_id)
        await conn.execute("UPDATE users SET current_trip_id=$1 WHERE user_id IN ($2, $3)", trip_id, driver_id, trip['rider_id'])
        
        rider = await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", trip['rider_id'])
        driver = await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", driver_id)
    finally:
        await conn.close()

    await query.answer()
    kb_d = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 إنهاء", callback_data=f"end_{trip_id}")]])
    await context.bot.send_message(driver['chat_id'], f"✅ قبلت الرحلة.\nالراكب: {rider['name']}\nالوجهة: {trip['dest_desc']}", reply_markup=kb_d)
    
    kb_r = InlineKeyboardMarkup([[InlineKeyboardButton("👋 إنهاء", callback_data=f"end_{trip_id}")]])
    await context.bot.send_message(rider['chat_id'], f"🚗 السائق قادم!\nالكابتن: {driver['name']}\nالسيارة: {driver['car_info']}", reply_markup=kb_r)

async def end_trip_callback(update, context): 
    await perform_trip_completion(context, update.callback_query.data.split("_")[1])
    await update.callback_query.answer()

async def manual_complete_trip(update, context):
    user_id = update.effective_user.id
    conn = await asyncpg.connect(DB_URL)
    try:
        row = await conn.fetchrow("SELECT trip_id FROM trips WHERE status='accepted' AND (driver_id=$1 OR rider_id=$2)", user_id, user_id)
        if row: await perform_trip_completion(context, row['trip_id'])
    finally:
        await conn.close()

async def perform_trip_completion(context, trip_id):
    conn = await asyncpg.connect(DB_URL)
    try:
        trip = await conn.fetchrow("SELECT * FROM trips WHERE trip_id=$1", trip_id)
        if not trip: return
        
        commission = trip['price'] * COMMISSION_RATE
        await conn.execute("UPDATE trips SET status=$1, completed_at=$2 WHERE trip_id=$3", TripStatus.COMPLETED, datetime.now(), trip_id)
        await conn.execute("UPDATE users SET current_trip_id=NULL WHERE user_id IN ($1, $2)", trip['driver_id'], trip['rider_id'])
        await conn.execute("UPDATE users SET debt = debt + $1, total_trips = total_trips + 1 WHERE user_id=$2", commission, trip['driver_id'])
        
        users = await conn.fetch("SELECT user_id, chat_id FROM users WHERE user_id IN ($1, $2)", trip['driver_id'], trip['rider_id'])
    finally:
        await conn.close()
            
    await notify_admin(context, f"✅ رحلة انتهت: {trip_id}\n💰 عمولة: {commission:.2f}")
    for u in users:
        try:
            msg = f"🏁 شكراً لك.\nالسعر: {trip['price']}"
            if u['user_id'] == trip['driver_id']: msg += f"\nالعمولة المخصومة: {commission:.2f}"
            role = UserRole.DRIVER if u['user_id'] == trip['driver_id'] else UserRole.RIDER
            await context.bot.send_message(u['chat_id'], msg, reply_markup=get_main_kb(role, True))
        except: pass

async def relay_chat_message(update, context, trip):
    sender_id = update.effective_user.id
    receiver_id = trip['rider_id'] if sender_id == trip['driver_id'] else trip['driver_id']
    conn = await asyncpg.connect(DB_URL)
    try:
        row = await conn.fetchrow("SELECT chat_id FROM users WHERE user_id=$1", receiver_id)
        if row:
            try:
                role = "🚖 الكابتن" if sender_id == trip['driver_id'] else "👤 الراكب"
                if update.message.text: await context.bot.send_message(row['chat_id'], f"💬 {role}: {update.message.text}")
                elif update.message.location: await context.bot.send_location(row['chat_id'], update.message.location.latitude, update.message.location.longitude)
            except: pass
    finally:
        await conn.close()

async def show_balance(update, context):
    user_id = update.effective_user.id
    conn = await asyncpg.connect(DB_URL)
    try:
        d = await conn.fetchrow("SELECT debt FROM users WHERE user_id=$1", user_id)
    finally:
        await conn.close()
    if d: await update.message.reply_text(f"💰 المحفظة:\nعليك: {d['debt']:.2f} ريال\nالحد: {DEBT_LIMIT}")

async def notify_admin(context, msg):
    for admin_id in ADMIN_IDS:
        try: await context.bot.send_message(admin_id, msg)
        except: pass

async def admin_help(update, context):
    if not is_admin(update.effective_user.id): return
    await update.message.reply_text("👮 /debts, /block [id], /unblock [id], /reset [id], /bc [msg]")

async def admin_debts_list(update, context):
    if not is_admin(update.effective_user.id): return
    conn = await asyncpg.connect(DB_URL)
    try:
        drivers = await conn.fetch("SELECT name, debt, phone FROM users WHERE role='driver' AND debt>0")
    finally:
        await conn.close()
    msg = "📊 الديون:\n" + "\n".join([f"{d['name']} ({d['phone']}): {d['debt']}" for d in drivers])
    await update.message.reply_text(msg if drivers else "لا يوجد ديون")

async def admin_actions(update, context):
    if not is_admin(update.effective_user.id): return
    cmd = update.message.text.split()[0]
    if not context.args: return await update.message.reply_text("Id required")
    tid = int(context.args[0])
    
    conn = await asyncpg.connect(DB_URL)
    try:
        if "/reset" in cmd: await conn.execute("UPDATE users SET debt=0 WHERE user_id=$1", tid)
        elif "/block" in cmd: await conn.execute("UPDATE users SET is_blocked=TRUE WHERE user_id=$1", tid)
        elif "/unblock" in cmd: await conn.execute("UPDATE users SET is_blocked=FALSE WHERE user_id=$1", tid)
    finally:
        await conn.close()
    await update.message.reply_text("✅ Done")

async def admin_broadcast(update, context):
    if not is_admin(update.effective_user.id): return
    conn = await asyncpg.connect(DB_URL)
    try:
        ids = await conn.fetch("SELECT chat_id FROM users")
    finally:
        await conn.close()
    for i in ids: 
        try: await context.bot.send_message(i['chat_id'], "📢 " + " ".join(context.args))
        except: pass
    await update.message.reply_text("✅ Sent")

# ==================== 🏁 التشغيل ====================
async def post_init(application: Application):
    await init_db()

def main():
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .connect_timeout(60).read_timeout(60).write_timeout(60)
        .build()
    )

    app.add_handler(CommandHandler("start", start_command))
    
    # أوامر الأدمن
    app.add_handler(CommandHandler("admin", admin_help))
    app.add_handler(CommandHandler("debts", admin_debts_list))
    app.add_handler(CommandHandler("bc", admin_broadcast))
    app.add_handler(CommandHandler(["block", "unblock", "reset"], admin_actions))
    
    # معالجة الصور والنصوص (مدمجة)
    app.add_handler(MessageHandler(filters.LOCATION, location_handler))
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, global_message_handler))
    
    # الكول باك (أزرار)
    app.add_handler(CallbackQueryHandler(register_callback, pattern="^reg_"))
    app.add_handler(CallbackQueryHandler(admin_verify_callback, pattern="^verify_"))
    app.add_handler(CallbackQueryHandler(accept_trip_callback, pattern="^accept_"))
    app.add_handler(CallbackQueryHandler(end_trip_callback, pattern="^end_"))

    print("🚀 Taxi Bot V6.0 (PostgreSQL/Supabase) Running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
