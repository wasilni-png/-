import re
import psycopg2

# ضع هنا بيانات قاعدة البيانات الخاصة بك
DB_URL = "postgresql://postgres.nmteaqxrtcegxmgvsbzr:mohammedfahdypb@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"
BOT_TOKEN = "8498451295:AAGt1R7THllSjYtEe5hvIEPnPhRkS_iBcnU"

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

def get_db_connection():
    try:
        conn = psycopg2.connect(DB_URL)
        return conn
    except Exception as e:
        print(f"❌ فشل الاتصال بقاعدة البيانات: {e}")
        return None


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