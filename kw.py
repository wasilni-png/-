#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import asyncio
import uuid
import sqlite3
from datetime import datetime
from enum import Enum
import math
import aiosqlite

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
BOT_TOKEN = "8123276127:AAHmLO2UXVY_HSQA7AMljHLlkfE8A-WEWgw"  # 👈 ضع التوكين هنا
ADMIN_IDS = [8563113166, 7996171713]                # 👈 ضع الآيدي الخاص بك
DB_NAME = "/data/taxi_master_v6.db"      # تم تغيير الاسم لإنشاء قاعدة جديدة

# ثوابت العمل
COMMISSION_RATE = 0.15
DEBT_LIMIT = 50.0
SEARCH_RADIUS = 20
MAX_DRIVERS_NOTIFY = 15
def is_admin(user_id: int) -> bool:
    """التحقق من وجود المستخدم في قائمة الإدارة"""
    return user_id in ADMIN_IDS
# ==================== 🗄️ قاعدة البيانات ====================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                chat_id INTEGER,
                role TEXT,
                name TEXT,
                phone TEXT,
                car_info TEXT,
                lat REAL DEFAULT 0.0,
                lon REAL DEFAULT 0.0,
                debt REAL DEFAULT 0.0,
                is_blocked INTEGER DEFAULT 0,
                is_verified INTEGER DEFAULT 0,  -- 🆕 للتوثيق
                photo_license TEXT,             -- 🆕 صورة الرخصة
                photo_car TEXT,                 -- 🆕 صورة السيارة
                photo_id_card TEXT,             -- 🆕 صورة الهوية
                total_trips INTEGER DEFAULT 0,
                rating REAL DEFAULT 5.0,
                current_trip_id TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS trips (
                trip_id TEXT PRIMARY KEY,
                rider_id INTEGER,
                driver_id INTEGER,
                pickup_lat REAL,
                pickup_lon REAL,
                dest_desc TEXT,
                price REAL DEFAULT 0.0,
                status TEXT,
                created_at TIMESTAMP,
                completed_at TIMESTAMP
            )
        ''')
        await db.commit()
    print("✅ Database V6.0 (Verified) Ready.")

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

def get_main_kb(role, is_verified=1):
    if role == UserRole.DRIVER:
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
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cursor:
            user = await cursor.fetchone()
    
    if user:
        if user['is_blocked']:
            await update.message.reply_text("⛔ حسابك محظور.")
            return
        # التحقق من التوثيق للسائق
        verified = user['is_verified'] if user['role'] == 'driver' else 1
        await update.message.reply_text(f"👋 أهلاً {user['name']}", reply_markup=get_main_kb(user['role'], verified))
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 أنا راكب", callback_data="reg_rider")],
            [InlineKeyboardButton("🚗 أنا سائق", callback_data="reg_driver")]
        ])
        await update.message.reply_text("👋 مرحباً بك.\nاختر نوع الحساب:", reply_markup=kb)

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
            await finalize_registration(update, context) # الراكب لا يحتاج توثيق
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
        # بدء مرحلة الصور للسائق
        await update.message.reply_text("📸 **مطلوب التوثيق**\nالرجاء إرسال **صورة رخصة القيادة** الآن:")
        context.user_data['state'] = 'WAIT_PHOTO_LICENSE'
        return

    # --- 2. التسجيل (صور) ---
    elif state in ['WAIT_PHOTO_LICENSE', 'WAIT_PHOTO_CAR', 'WAIT_PHOTO_ID']:
        if not update.message.photo:
            await update.message.reply_text("⚠️ الرجاء إرسال صورة فقط.")
            return
        
        photo_id = update.message.photo[-1].file_id # جلب أعلى جودة
        
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
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM trips WHERE status='accepted' AND (rider_id=? OR driver_id=?)", (user_id, user_id)) as cursor:
            active_trip = await cursor.fetchone()

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
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT OR REPLACE INTO users (user_id, chat_id, role, name, is_verified)
            VALUES (?, ?, 'rider', ?, 1)
        """, (uid, update.effective_chat.id, name))
        await db.commit()
    context.user_data.clear()
    await update.message.reply_text("✅ تم التسجيل.", reply_markup=get_main_kb(UserRole.RIDER))

async def finalize_registration_driver(update, context): # للسائقين
    uid = update.effective_user.id
    d = context.user_data
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT OR REPLACE INTO users (user_id, chat_id, role, name, phone, car_info, photo_license, photo_car, photo_id_card, is_verified)
            VALUES (?, ?, 'driver', ?, ?, ?, ?, ?, ?, 0)
        """, (uid, update.effective_chat.id, d['reg_name'], d['reg_phone'], d['reg_car'], 
              d['photo_license'], d['photo_car'], d['photo_id_card']))
        await db.commit()
    
    # إشعار الأدمن بالتوثيق
    msg = (
        f"🚨 **طلب توثيق سائق جديد**\n"
        f"👤 الاسم: {d['reg_name']}\n"
        f"📱 الجوال: {d['reg_phone']}\n"
        f"🚘 السيارة: {d['reg_car']}\n"
        f"🆔 UserID: `{uid}`"
    )
    
    # إرسال الصور كألبوم
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
            # 1. إرسال مجموعة الصور للأدمن الحالي
            await context.bot.send_media_group(chat_id=admin_id, media=media)
            
            # 2. إرسال الرسالة النصية مع الأزرار للأدمن الحالي
            await context.bot.send_message(
                chat_id=admin_id, 
                text=msg, 
                reply_markup=kb, 
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            # إذا فشل الإرسال لأدمن واحد (مثلاً حظر البوت)، يطبع الخطأ ويكمل للباقين
            print(f"⚠️ تعذر الإرسال إلى {admin_id}: {e}")

    context.user_data.clear()

# ==================== 👮 أدمن: معالجة التوثيق ====================

async def admin_verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action, target_id = query.data.split("_")[1], int(query.data.split("_")[2])
    
    async with aiosqlite.connect(DB_NAME) as db:
        if action == "ok":
            await db.execute("UPDATE users SET is_verified=1, is_blocked=0 WHERE user_id=?", (target_id,))
            await db.commit()
            await query.edit_message_text(f"✅ تم تفعيل السائق {target_id}")
            # إشعار السائق
            async with db.execute("SELECT chat_id FROM users WHERE user_id=?", (target_id,)) as c:
                row = await c.fetchone()
                if row: 
                    await context.bot.send_message(row[0], "🎉 **مبروك!** تم توثيق حسابك بنجاح.\nيمكنك الآن استقبال الطلبات.", reply_markup=get_main_kb(UserRole.DRIVER, 1))
        else:
            await db.execute("UPDATE users SET is_verified=0, is_blocked=1 WHERE user_id=?", (target_id,))
            await db.commit()
            await query.edit_message_text(f"❌ تم رفض وحظر السائق {target_id}")
            async with db.execute("SELECT chat_id FROM users WHERE user_id=?", (target_id,)) as c:
                row = await c.fetchone()
                if row: await context.bot.send_message(row[0], "❌ نأسف، تم رفض طلب انضمامك لعدم استيفاء الشروط.")

# ==================== 📍 المنطق (مع التحقق) ====================

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lat, lon = update.message.location.latitude, update.message.location.longitude
    
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("UPDATE users SET lat=?, lon=? WHERE user_id=?", (lat, lon, user_id))
        await db.commit()
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cursor:
            user = await cursor.fetchone()

    if context.user_data.get('expect_location') == 'pickup':
        context.user_data['pickup_coords'] = (lat, lon)
        context.user_data['state'] = 'WAIT_DESTINATION'
        context.user_data['expect_location'] = None
        await update.message.reply_text("📝 إلى أين؟", reply_markup=ReplyKeyboardRemove())
        return

    if user['role'] == UserRole.DRIVER:
        # 🛡️ تحقق من التوثيق
        if user['is_verified'] == 0:
            await update.message.reply_text("⏳ حسابك قيد المراجعة، يرجى انتظار موافقة الإدارة.")
            return
        if user['is_blocked'] or user['debt'] >= DEBT_LIMIT:
            await update.message.reply_text("❌ حسابك موقوف (ديون أو حظر).")
            return
        
        if user['current_trip_id']: return 

        # البحث عن طلبات
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM trips WHERE status=?", (TripStatus.PENDING,)) as cursor:
                pending = await cursor.fetchall()
        
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
    # ... (نفس الكود السابق للطلب)
    rider_id = update.effective_user.id
    pickup = context.user_data['pickup_coords']
    dest = context.user_data['dest_desc']
    trip_id = str(uuid.uuid4())[:8]
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO trips (trip_id, rider_id, pickup_lat, pickup_lon, dest_desc, price, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (trip_id, rider_id, pickup[0], pickup[1], dest, price, TripStatus.PENDING, datetime.now()))
        await db.commit()
    
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
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        # 🛡️ البحث فقط عن السائقين الموثقين
        async with db.execute("""
            SELECT * FROM users 
            WHERE role=? AND is_blocked=0 AND is_verified=1 AND debt < ? 
            AND (current_trip_id IS NULL OR current_trip_id = '')
        """, (UserRole.DRIVER, DEBT_LIMIT)) as cursor:
            drivers = await cursor.fetchall()
            
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
    
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        # 🛡️ تحقق إضافي من التوثيق
        async with db.execute("SELECT is_verified FROM users WHERE user_id=?", (driver_id,)) as c:
            u = await c.fetchone()
            if not u or u['is_verified'] == 0:
                await query.answer("❌ حسابك غير موثق.", show_alert=True)
                return

        # بقية كود القبول (كما هو)
        async with db.execute("SELECT * FROM trips WHERE trip_id=?", (trip_id,)) as cursor:
            trip = await cursor.fetchone()
        
        if not trip or trip['status'] != TripStatus.PENDING:
            await query.answer("❌ راحت عليك!", show_alert=True)
            await query.edit_message_text("❌ انتهى العرض.")
            return

        await db.execute("UPDATE trips SET driver_id=?, status=? WHERE trip_id=?", (driver_id, TripStatus.ACCEPTED, trip_id))
        await db.execute("UPDATE users SET current_trip_id=? WHERE user_id IN (?, ?)", (trip_id, driver_id, trip['rider_id']))
        await db.commit()
        
        async with db.execute("SELECT * FROM users WHERE user_id=?", (trip['rider_id'],)) as c: rider = await c.fetchone()
        async with db.execute("SELECT * FROM users WHERE user_id=?", (driver_id,)) as c: driver = await c.fetchone()

    await query.answer()
    kb_d = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 إنهاء", callback_data=f"end_{trip_id}")]])
    await context.bot.send_message(driver['chat_id'], f"✅ قبلت الرحلة.\nالراكب: {rider['name']}\nالوجهة: {trip['dest_desc']}", reply_markup=kb_d)
    
    kb_r = InlineKeyboardMarkup([[InlineKeyboardButton("👋 إنهاء", callback_data=f"end_{trip_id}")]])
    await context.bot.send_message(rider['chat_id'], f"🚗 السائق قادم!\nالكابتن: {driver['name']}\nالسيارة: {driver['car_info']}", reply_markup=kb_r)

# --- بقية الدوال المساعدة (إنهاء، أدمن، إلخ) ---
# يتم نسخها كما هي من الكود السابق V5.0 مع التأكد من وجود notify_admin و manual_complete_trip
async def end_trip_callback(update, context): 
    await perform_trip_completion(context, update.callback_query.data.split("_")[1])
    await update.callback_query.answer()

async def manual_complete_trip(update, context):
    user_id = update.effective_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT trip_id FROM trips WHERE status='accepted' AND (driver_id=? OR rider_id=?)", (user_id, user_id)) as cursor:
            row = await cursor.fetchone()
            if row: await perform_trip_completion(context, row['trip_id'])

async def perform_trip_completion(context, trip_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM trips WHERE trip_id=?", (trip_id,)) as cursor:
            trip = await cursor.fetchone()
        if not trip: return
        
        commission = trip['price'] * COMMISSION_RATE
        await db.execute("UPDATE trips SET status=?, completed_at=? WHERE trip_id=?", (TripStatus.COMPLETED, datetime.now(), trip_id))
        await db.execute("UPDATE users SET current_trip_id=NULL WHERE user_id IN (?, ?)", (trip['driver_id'], trip['rider_id']))
        await db.execute("UPDATE users SET debt = debt + ?, total_trips = total_trips + 1 WHERE user_id=?", (commission, trip['driver_id']))
        await db.commit()
        
        async with db.execute("SELECT user_id, chat_id FROM users WHERE user_id IN (?, ?)", (trip['driver_id'], trip['rider_id'])) as c:
            users = await c.fetchall()
            
    await notify_admin(context, f"✅ رحلة انتهت: {trip_id}\n💰 عمولة: {commission:.2f}")
    for u in users:
        try:
            msg = f"🏁 شكراً لك.\nالسعر: {trip['price']}"
            if u['user_id'] == trip['driver_id']: msg += f"\nالعمولة المخصومة: {commission:.2f}"
            role = UserRole.DRIVER if u['user_id'] == trip['driver_id'] else UserRole.RIDER
            await context.bot.send_message(u['chat_id'], msg, reply_markup=get_main_kb(role, 1))
        except: pass

async def relay_chat_message(update, context, trip):
    # نفس الكود السابق
    sender_id = update.effective_user.id
    receiver_id = trip['rider_id'] if sender_id == trip['driver_id'] else trip['driver_id']
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT chat_id FROM users WHERE user_id=?", (receiver_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                try:
                    role = "🚖 الكابتن" if sender_id == trip['driver_id'] else "👤 الراكب"
                    if update.message.text: await context.bot.send_message(row[0], f"💬 {role}: {update.message.text}")
                    elif update.message.location: await context.bot.send_location(row[0], update.message.location.latitude, update.message.location.longitude)
                except: pass

async def show_balance(update, context):
    user_id = update.effective_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT debt FROM users WHERE user_id=?", (user_id,)) as c:
            d = await c.fetchone()
    if d: await update.message.reply_text(f"💰 المحفظة:\nعليك: {d['debt']:.2f} ريال\nالحد: {DEBT_LIMIT}")

async def notify_admin(context, msg):
    try: await context.bot.send_message(ADMIN_IDS, msg)
    except: pass

async def admin_help(update, context):
    if not is_admin(update.effective_user.id): return
    await update.message.reply_text("👮 /debts, /block [id], /unblock [id], /reset [id], /bc [msg]")

async def admin_debts_list(update, context): # نفس V5.0
    if not is_admin(update.effective_user.id): return
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT name, debt, phone FROM users WHERE role='driver' AND debt>0") as c:
            drivers = await c.fetchall()
    msg = "📊 الديون:\n" + "\n".join([f"{d['name']} ({d['phone']}): {d['debt']}" for d in drivers])
    await update.message.reply_text(msg if drivers else "لا يوجد ديون")

async def admin_actions(update, context): # نفس V5.0
    if not is_admin(update.effective_user.id): return
    cmd = update.message.text.split()[0]
    if not context.args: return await update.message.reply_text("Id required")
    tid = int(context.args[0])
    async with aiosqlite.connect(DB_NAME) as db:
        if "/reset" in cmd: await db.execute("UPDATE users SET debt=0 WHERE user_id=?", (tid,))
        elif "/block" in cmd: await db.execute("UPDATE users SET is_blocked=1 WHERE user_id=?", (tid,))
        elif "/unblock" in cmd: await db.execute("UPDATE users SET is_blocked=0 WHERE user_id=?", (tid,))
        await db.commit()
    await update.message.reply_text("✅ Done")

async def admin_broadcast(update, context): # نفس V5.0
    if not is_admin(update.effective_user.id): return
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT chat_id FROM users") as c: ids = await c.fetchall()
    for i in ids: 
        try: await context.bot.send_message(i[0], "📢 " + " ".join(context.args))
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
    app.add_handler(CallbackQueryHandler(admin_verify_callback, pattern="^verify_")) # 🆕 معالج التوثيق
    app.add_handler(CallbackQueryHandler(accept_trip_callback, pattern="^accept_"))
    app.add_handler(CallbackQueryHandler(end_trip_callback, pattern="^end_"))

    print("🚀 Taxi Bot V6.0 (Secure & Verified) Running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()

# Hammod
