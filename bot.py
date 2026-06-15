import os
import logging
import aiohttp
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from database import init_db, upsert_client, save_order, update_order_status, get_client_orders, get_stats, get_next_order_num, get_all_prices, get_price, set_price, add_staff, remove_staff, get_staff_by_role, get_client_lang, set_client_lang

logging.basicConfig(level=logging.INFO)

BOT_TOKEN   = os.getenv("BOT_TOKEN", "8871514482:AAGEqOUDPoAeCyyu8gvGa0ZkKRgqV28Yo5A")
ADMIN_ID    = int(os.getenv("ADMIN_ID") or "624826036")       # ваш личный ID (для сообщений от оператора)
GROUP_ID    = int(os.getenv("GROUP_ID") or "-5211502458")      # группа сотрудников (заявки)
GROUP_SMS_ID = int(os.getenv("GROUP_SMS_ID") or "-5303335722")  # группа сообщений от клиентов
SHEETS_URL  = os.getenv("SHEETS_URL", "https://script.google.com/macros/s/AKfycbyU5a3pMuTFme3dBNEgu46qzA1sN1Ekw-Q7p39F1Pg872lnnXZEFhJPjuc4TzZNHlpObQ/exec")

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

# ── Часовой пояс ──
TASHKENT_TZ = ZoneInfo("Asia/Tashkent")

def now_local():
    return datetime.now(TASHKENT_TZ)

def md_escape(text):
    """Экранирует символы, которые ломают Telegram Markdown-разметку"""
    if not text:
        return ""
    text = str(text)
    for ch in ['_', '*', '[', ']', '`']:
        text = text.replace(ch, f"\\{ch}")
    return text

# ══════════════════════════════════════
#  ПЕРЕВОДЫ
# ══════════════════════════════════════
T = {
    "ru": {
        "choose_lang":    "👋 Добро пожаловать в ARTEZ!\n\nВыберите язык:",
        "lang_set":       "🇷🇺 Выбран русский язык",
        "menu_title":     "🏠 Главное меню\n\nООО «ARTEZ» — профессиональная чистка ковров\n📍 Зарафшан и Навои\n\n☎️ Короткий номер: `1221`\n📞 Оператор: `+998 79 222 12 21`\n\n*г. Зарафшан*\n📱 `+998 88 200 12 21`\n📱 `+998 94 738 04 44`\n\n*г. Навои*\n📱 `+998 99 750 00 20`\n📱 `+998 99 112 48 48`",
        "btn_order":      "📋 Оставить заявку",
        "btn_calc":       "🧮 Калькулятор",
        "btn_prices":     "💰 Цены",
        "btn_branches":   "📍 Филиалы",
        "btn_promo":      "🎁 Акции",
        "btn_status":     "📦 Статус заказа",
        "btn_operator":   "👨‍💼 Оператор",
        "btn_info":       "ℹ️ О компании",
        "btn_help":       "🆘 Помощь",
        "btn_settings":   "⚙️ Настройки",
        "btn_change_lang": "🌐 Сменить язык",
        "settings_text":  "⚙️ *Настройки*\n\nЗдесь вы можете изменить язык или открыть справку.",
        "choose_lang_text": "🌐 Выберите язык:",
        "btn_back":       "◀️ Назад",
        "btn_menu":       "🏠 Меню",
        "btn_zarafshan":  "📍 Зарафшан",
        "btn_navoi":      "📍 Навои",
        "ask_name":       "📋 *Оформление заявки*\n\nШаг 1 из 6\n👤 Введите ваше имя:",
        "ask_phone":      "Шаг 2 из 7\n📞 Поделитесь номером или введите вручную:\n\nФормат: +998XXXXXXXXX",
        "btn_share_phone":"📱 Поделиться номером",
        "btn_enter_phone":"⌨️ Ввести другой номер",
        "ask_phone_manual":"✏️ Введите номер в формате:\n+998XXXXXXXXX\n\nПример: +998901234567",
        "phone_invalid":  "⚠️ Неверный формат!\n\nВведите номер строго в формате:\n*+998XXXXXXXXX*\n\nПример: +998901234567",
        "ask_address":    "Шаг 5 из 7\n🏠 Введите адрес вывоза ковра:",
        "ask_location":   "Шаг 6 из 7\n📍 Отправьте локацию места вывоза\n\n_(необязательно — нажмите «Пропустить» если не нужно)_",
        "btn_send_loc":   "📍 Отправить локацию",
        "btn_skip_loc":   "⏭ Пропустить",
        "ask_service":    "Шаг 7 из 7\n🧺 Выберите услугу:",
        "ask_branch":     "Шаг 3 из 6\n🏢 Выберите филиал:",
        "ask_city":       "Шаг 4 из 6\n📍 Выберите город или район:",
        "ask_address":    "Шаг 5 из 6\n🏠 Введите адрес вывоза ковра:",
        "ask_service":    "Шаг 6 из 6\n🧺 Выберите услугу:",
        "ask_date":       "📅 Выберите дату вывоза:",
        "btn_today":      "📅 Сегодня",
        "btn_tomorrow":   "📅 Завтра",
        "btn_pick_date":  "🗓 Указать дату",
        "ask_date_manual":"✏️ Введите дату в формате ДД.ММ.ГГГГ\n\nПример: 20.06.2026",
        "date_invalid":   "⚠️ Неверный формат даты!\n\nВведите в формате ДД.ММ.ГГГГ\nПример: 20.06.2026",
        "ask_time":       "🕐 Выберите удобное время:",
        "btn_morning":    "🌅 До обеда (08:00-13:00)",
        "btn_evening":    "🌆 После обеда (13:00-20:00)",
        "btn_custom_time":"⏰ Указать период",
        "ask_time_from":  "⏰ Введите время *С* (например: 10:00)",
        "ask_time_to":    "Введите время *ДО* (например: 14:00)",
        "order_done":     "✅ *Заявка принята!*\n\nМы перезвоним вам в течение 30 минут.\n\nНомер заявки: *#{num}*\n\nВам позвонят с номеров:\n📞 +998 79 222-12-21\n📞 +998 88 200-12-21\n📞 +998 94 738-04-44",
        "order_rejected": "❌ К сожалению, заявка *{num}* не может быть выполнена.\n\nПозвоните нам:\n📞 +998 94 738-04-44\n📞 +998 88 200-12-21",
        "order_summary":  "📋 *Новая заявка #{num}* (бот)\n━━━━━━━━━━━━━━━\n👤 {name}\n📞 {phone}\n🏢 {branch}\n📍 {city}\n🏠 {address}\n🗺 {location}\n🧺 {service}\n📅 {date}\n🕐 {time}\n━━━━━━━━━━━━━━━\n🕒 {dt}",
        "prices_text":    "💰 *Прайс-лист ARTEZ*\n\n🧺 Стандартная чистка — 12 000 сум/м²\n✨ Глубокая химчистка — 16 000 сум/м²\n🛋 Бытовая техника/Понка — от 16 000 сум/шт\n🌿 Сухая чистка — 14 000 сум/м²\n\n📦 Минимальный заказ — 10 м²\n🚚 Вывоз и доставка — *бесплатно*",
        "calc_selected_header": "🧮 *Калькулятор стоимости*\n\n🧺 Услуга: {svc}",
        "calc_ask_w":     "Введите ширину в сантиметрах:\n\nПример: 200 (= 2 метра)",
        "calc_ask_l":     "Теперь введите длину в сантиметрах:\n\nПример: 300 (= 3 метра)",
        "calc_ask_svc":   "🧮 *Калькулятор стоимости*\n\nВыберите услугу:",
        "calc_result":    "🧮 *Расчёт стоимости*\n\n📐 Размер: {w} × {l} см = *{sqm} м²*\n🧺 Услуга: {svc}\n💰 Цена: {price} сум/м²\n\n💵 *Итого: {total} сум*\n\n_(Минимальный заказ 10 м²)_",
        "calc_result_no_min": "🧮 *Расчёт стоимости*\n\n📐 Размер: {w} × {l} см = *{sqm} м²*\n🧺 Услуга: {svc}\n💰 Цена: {price} сум/м²\n\n💵 *Итого: {total} сум*",
        "branches_text":  "📍 *Наши филиалы*\n\n🏢 *Филиал Зарафшан*\nОбслуживает: Зарафшан, Учкудук, Тамдинский район\n📞 1221\n📱 +998 79 222-12-21\n📱 +998 88 200-12-21\n📱 +998 94 738-04-44\n\n🏢 *Филиал Навои*\nОбслуживает: Навои и все остальные районы области\n📞 1221\n📱 +998 79 222-12-21\n📱 +998 99 750-00-20\n📱 +998 99 112-48-48",
        "promo_text":     "🎁 *Акции и скидки*\n\n🔥 При заказе от 3 ковров — скидка до 20%\n🚚 На все заказы — бесплатная доставка и забор\n🚗 Если у вас свой автомобиль — скидка до 20% на страховой полис ОСАГО\n📢 Подписчикам нашей Telegram-группы и Instagram — скидка до 30%\n\nПодпишитесь и получите скидку 👇",
        "btn_promo_telegram": "📢 Telegram-группа",
        "btn_promo_instagram": "📸 Instagram",
        "info_text":      "ℹ️ *О компании ARTEZ*\n\nООО «ARTEZ» — профессиональная чистка ковров в Навоийской области.\n\n🏢 Два филиала: Зарафшан и Навои\n🚚 Бесплатный вывоз и доставка\n⚡ Срок чистки от 24 часов\n🛡 Бережное отношение к коврам\n\n🌐 artez.uz\n📢 Telegram-группа: @artez_gilam_yuvish\n📸 Instagram: [@ziyoboboev](https://www.instagram.com/ziyoboboev/)\n\n☎️ Короткий номер: 1221\n📞 Оператор: +998 79 222 12 21\n\n*г. Зарафшан*\n📱 +998 88 200 12 21\n📱 +998 94 738 04 44\n\n*г. Навои*\n📱 +998 99 750 00 20\n📱 +998 99 112 48 48",
        "help_text":      "🆘 *Помощь*\n\n/start — Главное меню\n/order — Оставить заявку\n/calc — Калькулятор\n/prices — Цены\n/branches — Филиалы\n\nПо всем вопросам: 📞 1221",
        "status_text":    "📦 *Статус заказа*\n\nДля проверки статуса заказа позвоните нам:\n📞 1221\n📱 +998 79 222-12-21\n\nИли напишите оператору 👇",
        "status_menu_title": "📦 *Статус заказа*\n\nВыберите категорию:",
        "status_btn_new":       "🆕 Новые",
        "status_btn_progress":  "🔄 В работе",
        "status_btn_done":      "✅ Выполнено",
        "status_btn_cancelled": "❌ Отказано",
        "status_empty":   "📦 *Статус заказа*\n\nУ вас пока нет заявок.\n\nОформить заявку: /order",
        "status_group_empty": "В этой категории заявок нет.",
        "status_order_line":  "📋 *{num}*\n🧺 {service}\n📅 {date}\n📍 Статус: {status}",
        "btn_back_to_status": "◀️ К категориям",
        "operator_text":  "👨‍💼 Соединяю с оператором...\n\nНапишите ваш вопрос — оператор ответит в ближайшее время.",
        "operator_msg":   "💬 *Сообщение клиенту*\n\n👤 {name}\n💬 {msg}\n🆔 Chat: {cid}",
        "cancel":         "❌ Заявка отменена. Возвращаемся в меню.",
        "btn_cancel":     "❌ Отмена",
        "btn_svc_carpet":      "🧺 Чистка ковра",
        "btn_svc_carpet_home": "🏠 Чистка ковра на дому",
        "btn_svc_sofa":        "🛋 Чистка диван, кресло",
        "btn_svc_mattress":    "🛏 Чистка матрас, одеяло",
        "btn_svc_curtains":    "🪟 Чистка штор",
        "ask_service_type":    "Тип услуги:",
        "btn_type_standard":   "🧺 Стандартный",
        "btn_type_express":    "⚡ Быстрый",
        "invalid_num":    "⚠️ Пожалуйста, введите число. Например: 200",
        "operator_fwd":   "✅ Ваше сообщение передано оператору. Ожидайте ответа.",
    },
    "uz": {
        "choose_lang":    "👋 ARTEZ ga xush kelibsiz!\n\nTilni tanlang:",
        "lang_set":       "🇺🇿 O'zbek tili tanlandi",
        "menu_title":     "🏠 Asosiy menyu\n\nARTEZ MChJ — professional gilam tozalash\n📍 Zarafshon va Navoiy\n\n☎️ Qisqa raqam: `1221`\n📞 Operator: `+998 79 222 12 21`\n\n*Zarafshon shahri*\n📱 `+998 88 200 12 21`\n📱 `+998 94 738 04 44`\n\n*Navoiy shahri*\n📱 `+998 99 750 00 20`\n📱 `+998 99 112 48 48`",
        "btn_order":      "📋 Ariza qoldirish",
        "btn_calc":       "🧮 Kalkulyator",
        "btn_prices":     "💰 Narxlar",
        "btn_branches":   "📍 Filiallar",
        "btn_promo":      "🎁 Aksiyalar",
        "btn_status":     "📦 Buyurtma holati",
        "btn_operator":   "👨‍💼 Operator",
        "btn_info":       "ℹ️ Kompaniya haqida",
        "btn_help":       "🆘 Yordam",
        "btn_settings":   "⚙️ Sozlamalar",
        "btn_change_lang": "🌐 Tilni o'zgartirish",
        "settings_text":  "⚙️ *Sozlamalar*\n\nBu yerda tilni o'zgartirishingiz yoki yordam bo'limini ochishingiz mumkin.",
        "choose_lang_text": "🌐 Tilni tanlang:",
        "btn_back":       "◀️ Orqaga",
        "btn_menu":       "🏠 Menyu",
        "btn_zarafshan":  "📍 Zarafshon",
        "btn_navoi":      "📍 Navoiy",
        "ask_name":       "📋 *Ariza rasmiylashtirish*\n\n1-qadam (6 dan)\n👤 Ismingizni kiriting:",
        "ask_phone":      "2-qadam (7 dan)\n📞 Raqamingizni ulashing yoki qo'lda kiriting:\n\nFormat: +998XXXXXXXXX",
        "btn_share_phone":"📱 Raqamni ulashish",
        "btn_enter_phone":"⌨️ Boshqa raqam kiritish",
        "ask_phone_manual":"✏️ Raqamni quyidagi formatda kiriting:\n+998XXXXXXXXX\n\nMisol: +998901234567",
        "phone_invalid":  "⚠️ Noto'g'ri format!\n\nRaqamni qat'iy formatda kiriting:\n*+998XXXXXXXXX*\n\nMisol: +998901234567",
        "ask_address":    "5-qadam (7 dan)\n🏠 Gilamni olib ketish manzilini kiriting:",
        "ask_location":   "6-qadam (7 dan)\n📍 Olib ketish joylashuvini yuboring\n\n_(ixtiyoriy — kerak bo'lmasa «O'tkazib yuborish» tugmasini bosing)_",
        "btn_send_loc":   "📍 Joylashuvni yuborish",
        "btn_skip_loc":   "⏭ O'tkazib yuborish",
        "ask_service":    "7-qadam (7 dan)\n🧺 Xizmatni tanlang:",
        "ask_branch":     "3-qadam (6 dan)\n🏢 Filialni tanlang:",
        "ask_city":       "4-qadam (6 dan)\n📍 Shahar yoki tumanni tanlang:",
        "ask_address":    "5-qadam (6 dan)\n🏠 Gilamni olib ketish manzilini kiriting:",
        "ask_service":    "6-qadam (6 dan)\n🧺 Xizmatni tanlang:",
        "ask_date":       "📅 Olib ketish sanasini tanlang:",
        "btn_today":      "📅 Bugun",
        "btn_tomorrow":   "📅 Ertaga",
        "btn_pick_date":  "🗓 Sanani kiritish",
        "ask_date_manual":"✏️ Sanani KK.OO.YYYY formatida kiriting\n\nMisol: 20.06.2026",
        "date_invalid":   "⚠️ Sana formati noto'g'ri!\n\nKK.OO.YYYY formatida kiriting\nMisol: 20.06.2026",
        "ask_time":       "🕐 Qulay vaqtni tanlang:",
        "btn_morning":    "🌅 Tushgacha (08:00-13:00)",
        "btn_evening":    "🌆 Tushdan keyin (13:00-20:00)",
        "btn_custom_time":"⏰ Vaqt oralig'ini ko'rsatish",
        "ask_time_from":  "⏰ *Dan* vaqtini kiriting (masalan: 10:00)",
        "ask_time_to":    "*Gacha* vaqtini kiriting (masalan: 14:00)",
        "order_done":     "✅ *Ariza qabul qilindi!*\n\n30 daqiqa ichida qayta qo'ng'iroq qilamiz.\n\nAriza raqami: *#{num}*\n\nSizga quyidagi raqamlardan qo'ng'iroq qilishadi:\n📞 +998 79 222-12-21\n📞 +998 88 200-12-21\n📞 +998 94 738-04-44",
        "order_rejected": "❌ Afsuski, *{num}* arizasi bajarilishi mumkin emas.\n\nBizga qo'ng'iroq qiling:\n📞 +998 94 738-04-44\n📞 +998 88 200-12-21",
        "order_summary":  "📋 *Yangi ariza #{num}* (bot)\n━━━━━━━━━━━━━━━\n👤 {name}\n📞 {phone}\n🏢 {branch}\n📍 {city}\n🏠 {address}\n🗺 {location}\n🧺 {service}\n📅 {date}\n🕐 {time}\n━━━━━━━━━━━━━━━\n🕒 {dt}",
        "prices_text":    "💰 *ARTEZ narx-navo*\n\n🧺 Standart tozalash — 12 000 so'm/m²\n✨ Chuqur kimyoviy — 16 000 so'm/m²\n🛋 Maishiy texnika/Ponka — 16 000 so'mdan/dona\n🌿 Quruq tozalash — 14 000 so'm/m²\n\n📦 Minimal buyurtma — 10 m²\n🚚 Olib ketish va yetkazish — *bepul*",
        "calc_selected_header": "🧮 *Narx kalkulyatori*\n\n🧺 Xizmat: {svc}",
        "calc_ask_w":     "Enini santimetrda kiriting:\n\nMisol: 200 (= 2 metr)",
        "calc_ask_l":     "Endi bo'yini santimetrda kiriting:\n\nMisol: 300 (= 3 metr)",
        "calc_ask_svc":   "🧮 *Narx kalkulyatori*\n\nXizmatni tanlang:",
        "calc_result":    "🧮 *Narx hisobi*\n\n📐 O'lcham: {w} × {l} sm = *{sqm} m²*\n🧺 Xizmat: {svc}\n💰 Narx: {price} so'm/m²\n\n💵 *Jami: {total} so'm*\n\n_(Minimal buyurtma 10 m²)_",
        "calc_result_no_min": "🧮 *Narx hisobi*\n\n📐 O'lcham: {w} × {l} sm = *{sqm} m²*\n🧺 Xizmat: {svc}\n💰 Narx: {price} so'm/m²\n\n💵 *Jami: {total} so'm*",
        "branches_text":  "📍 *Filiallarimiz*\n\n🏢 *Zarafshon filiali*\nXizmat ko'rsatadi: Zarafshon, Uchquduq, Tomdi tumani\n📞 1221\n📱 +998 79 222-12-21\n📱 +998 88 200-12-21\n📱 +998 94 738-04-44\n\n🏢 *Navoiy filiali*\nXizmat ko'rsatadi: Navoiy va viloyatning boshqa tumanlari\n📞 1221\n📱 +998 79 222-12-21\n📱 +998 99 750-00-20\n📱 +998 99 112-48-48",
        "promo_text":     "🎁 *Aksiyalar va chegirmalar*\n\n🔥 3 ta va undan ko'p gilam buyurtma qilsangiz — 20% gacha chegirma\n🚚 Barcha buyurtmalar uchun — bepul olib ketish va yetkazish\n🚗 Agar shaxsiy avtomobilingiz bo'lsa — OSAGO sug'urta polisiga 20% gacha chegirma\n📢 Telegram-guruhimiz va Instagram'ga obuna bo'lganlar uchun — 30% gacha chegirma\n\nObuna bo'ling va chegirma oling 👇",
        "btn_promo_telegram": "📢 Telegram-guruh",
        "btn_promo_instagram": "📸 Instagram",
        "info_text":      "ℹ️ *ARTEZ haqida*\n\nARTEZ MChJ — Navoiy viloyatida professional gilam tozalash.\n\n🏢 Ikki filial: Zarafshon va Navoiy\n🚚 Bepul olib ketish va yetkazish\n⚡ Tozalash muddati 24 soatdan\n🛡 Gilamlarga ehtiyotkorona munosabat\n\n🌐 artez.uz\n📢 Telegram-guruh: @artez_gilam_yuvish\n📸 Instagram: [@ziyoboboev](https://www.instagram.com/ziyoboboev/)\n\n☎️ Qisqa raqam: 1221\n📞 Operator: +998 79 222 12 21\n\n*Zarafshon shahri*\n📱 +998 88 200 12 21\n📱 +998 94 738 04 44\n\n*Navoiy shahri*\n📱 +998 99 750 00 20\n📱 +998 99 112 48 48",
        "help_text":      "🆘 *Yordam*\n\n/start — Asosiy menyu\n/order — Ariza qoldirish\n/calc — Kalkulyator\n/prices — Narxlar\n/branches — Filiallar\n\nBarcha savollar uchun: 📞 1221",
        "status_text":    "📦 *Buyurtma holati*\n\nBuyurtma holatini tekshirish uchun qo'ng'iroq qiling:\n📞 1221\n📱 +998 79 222-12-21\n\nYoki operatorga yozing 👇",
        "status_menu_title": "📦 *Buyurtma holati*\n\nKategoriyani tanlang:",
        "status_btn_new":       "🆕 Yangi",
        "status_btn_progress":  "🔄 Bajarilmoqda",
        "status_btn_done":      "✅ Bajarildi",
        "status_btn_cancelled": "❌ Bekor qilindi",
        "status_empty":   "📦 *Buyurtma holati*\n\nSizda hali buyurtmalar yo'q.\n\nBuyurtma berish: /order",
        "status_group_empty": "Bu kategoriyada buyurtmalar yo'q.",
        "status_order_line":  "📋 *{num}*\n🧺 {service}\n📅 {date}\n📍 Holat: {status}",
        "btn_back_to_status": "◀️ Kategoriyalarga",
        "operator_text":  "👨‍💼 Operator bilan bog'lanmoqda...\n\nSavolingizni yozing — operator tez orada javob beradi.",
        "operator_msg":   "💬 *Mijozdan xabar*\n\n👤 {name}\n💬 {msg}\n🆔 Chat: {cid}",
        "cancel":         "❌ Ariza bekor qilindi. Menyuga qaytamiz.",
        "btn_cancel":     "❌ Bekor qilish",
        "btn_svc_carpet":      "🧺 Gilam tozalash",
        "btn_svc_carpet_home": "🏠 Gilamni uyda tozalash",
        "btn_svc_sofa":        "🛋 Divan, kreslo tozalash",
        "btn_svc_mattress":    "🛏 Matras, ko'rpa tozalash",
        "btn_svc_curtains":    "🪟 Parda tozalash",
        "ask_service_type":    "Xizmat turi:",
        "btn_type_standard":   "🧺 Standart",
        "btn_type_express":    "⚡ Tezkor",
        "invalid_num":    "⚠️ Iltimos, son kiriting. Masalan: 200",
        "operator_fwd":   "✅ Xabaringiz operatorga yuborildi. Javob kuting.",
    }
}

CITIES = {
    "zarafshan": {
        "ru": ["г. Зарафшан","г. Учкудук","Тамдинский район"],
        "uz": ["Zarafshon sh.","Uchquduq sh.","Tomdi tumani"]
    },
    "navoi": {
        "ru": ["г. Навои","Кармана","Навбахор","Хатирчи","Нурата","Конимех","Зафаробод"],
        "uz": ["Navoiy sh.","Karmana","Navbahor","Xatirchi","Nurata","Konimex","Zafarobod"]
    }
}

# Кэш цен из БД: {service_key: {type_key: {"price":.., "unit":..}}}
PRICE_CACHE = {}

# Дефолты на случай, если БД недоступна или таблица prices пуста
DEFAULT_PRICES = {
    "carpet":      {"standard": {"price": 12000, "unit": "sum/m2"}, "express": {"price": 16000, "unit": "sum/m2"}},
    "carpet_home": {"standard": {"price": 14000, "unit": "sum/m2"}, "express": {"price": 18000, "unit": "sum/m2"}},
    "sofa":        {"standard": {"price": 16000, "unit": "sum/m2"}, "express": {"price": 20000, "unit": "sum/m2"}},
    "mattress":    {"standard": {"price": 16000, "unit": "sum/m2"}, "express": {"price": 20000, "unit": "sum/m2"}},
    "curtains":    {"standard": {"price": 14000, "unit": "sum/m2"}, "express": {"price": 18000, "unit": "sum/m2"}},
}

async def load_prices():
    """Загружает цены из БД в PRICE_CACHE. При ошибке/пустой БД использует дефолты."""
    global PRICE_CACHE
    try:
        data = await get_all_prices()
    except Exception as e:
        logging.warning(f"load_prices error: {e}")
        data = {}
    if not data:
        data = DEFAULT_PRICES
    PRICE_CACHE = data

def get_cached_price(service_key: str, type_key: str):
    entry = PRICE_CACHE.get(service_key, {}).get(type_key)
    if entry:
        return entry["price"]
    fallback = DEFAULT_PRICES.get(service_key, {}).get(type_key)
    return fallback["price"] if fallback else 12000

SVC_KEY_MAP  = {
    "carpet":      "btn_svc_carpet",
    "carpet_home": "btn_svc_carpet_home",
    "sofa":        "btn_svc_sofa",
    "mattress":    "btn_svc_mattress",
    "curtains":    "btn_svc_curtains",
}
TYPE_KEY_MAP = {"standard": "btn_type_standard", "express": "btn_type_express"}

def svc_display_name(uid, svc, svctype):
    svc_name  = t(uid, SVC_KEY_MAP.get(svc, "btn_svc_carpet"))
    type_name = t(uid, TYPE_KEY_MAP.get(svctype, "btn_type_standard"))
    return f"{svc_name} ({type_name})"

# Услуги, для которых действует минимальный заказ 10 м²
MIN_ORDER_SERVICES = {"carpet", "carpet_home"}

# Группы статусов заказа для раздела «Статус заказа»
STATUS_GROUPS = {
    "new":       ["new", "confirmed"],
    "progress":  ["pickup", "received", "washing", "packing", "ready", "delivery"],
    "done":      ["delivered"],
    "cancelled": ["cancelled"],
}

ORDER_STATUS_NAMES_RU = {
    "new": "🆕 Новый", "confirmed": "✅ Подтверждён",
    "pickup": "🚗 Вывоз", "received": "📥 Принят в мастерскую", "washing": "🧼 В чистке",
    "packing": "📦 Упаковка", "ready": "✅ Готов", "delivery": "🚚 Доставка",
    "delivered": "✅ Доставлен", "cancelled": "❌ Отменён",
}
ORDER_STATUS_NAMES_UZ = {
    "new": "🆕 Yangi", "confirmed": "✅ Tasdiqlangan",
    "pickup": "🚗 Olib ketish", "received": "📥 Ustaxonaga qabul qilindi", "washing": "🧼 Tozalanmoqda",
    "packing": "📦 Qadoqlash", "ready": "✅ Tayyor", "delivery": "🚚 Yetkazish",
    "delivered": "✅ Yetkazildi", "cancelled": "❌ Bekor qilindi",
}

def order_status_name(uid, status):
    names = ORDER_STATUS_NAMES_UZ if lang(uid) == "uz" else ORDER_STATUS_NAMES_RU
    return names.get(status, status)


# Человекочитаемые названия услуг/типов для команд админа
SERVICE_KEYS = ["carpet", "carpet_home", "sofa", "mattress", "curtains"]
TYPE_KEYS    = ["standard", "express"]
SERVICE_NAMES_RU = {
    "carpet":      "Чистка ковра",
    "carpet_home": "Чистка ковра на дому",
    "sofa":        "Чистка диван/кресло",
    "mattress":    "Чистка матрас/одеяло",
    "curtains":    "Чистка штор",
}
TYPE_NAMES_RU = {"standard": "Стандартный", "express": "Быстрый"}

SERVICE_NAMES_UZ = {
    "carpet":      "Gilam tozalash",
    "carpet_home": "Gilamni uyda tozalash",
    "sofa":        "Divan/kreslo tozalash",
    "mattress":    "Matras/ko'rpa tozalash",
    "curtains":    "Parda tozalash",
}
TYPE_NAMES_UZ = {"standard": "Standart", "express": "Tezkor"}

def build_prices_text(uid):
    is_uz = lang(uid) == "uz"
    names = SERVICE_NAMES_UZ if is_uz else SERVICE_NAMES_RU
    types = TYPE_NAMES_UZ if is_uz else TYPE_NAMES_RU
    title = "💰 *ARTEZ narx-navo*" if is_uz else "💰 *Прайс-лист ARTEZ*"
    lines = [title, ""]
    for svc in SERVICE_KEYS:
        svc_name = names.get(svc, svc)
        prices = PRICE_CACHE.get(svc, DEFAULT_PRICES.get(svc, {}))
        parts = []
        for tk in TYPE_KEYS:
            entry = prices.get(tk)
            if entry:
                unit_raw = entry["unit"]
                unit = "сум/м²" if (not is_uz and unit_raw == "sum/m2") else \
                       ("so'm/m²" if (is_uz and unit_raw == "sum/m2") else unit_raw)
                price_str = f"{entry['price']:,}".replace(",", " ")
                parts.append(f"{types.get(tk, tk)}: {price_str} {unit}")
        lines.append(f"🧺 *{svc_name}*\n   " + "\n   ".join(parts))
    lines.append("")
    if is_uz:
        lines.append("📦 Minimal buyurtma — 10 m²")
        lines.append("🚚 Olib ketish va yetkazish — *bepul*")
    else:
        lines.append("📦 Минимальный заказ — 10 м²")
        lines.append("🚚 Вывоз и доставка — *бесплатно*")
    return "\n".join(lines)


# ── Хранилище языков и данных ──
user_lang    = {}
user_data_db = {}

def lang(uid): return user_lang.get(uid, "ru")
def t(uid, key): return T[lang(uid)].get(key, key)

# ══════════════════════════════════════
#  FSM STATES
# ══════════════════════════════════════
class OrderForm(StatesGroup):
    name        = State()
    phone       = State()
    branch      = State()
    city        = State()
    address     = State()
    location    = State()
    service     = State()
    service_type = State()
    date        = State()
    time        = State()
    time_from   = State()   # ввод периода «с»
    time_to     = State()   # ввод периода «до»

class CalcForm(StatesGroup):
    width   = State()
    length  = State()
    service = State()
    service_type = State()

class OperatorForm(StatesGroup):
    message = State()

class AdminReply(StatesGroup):
    waiting_reply = State()   # оператор пишет ответ клиенту

# ══════════════════════════════════════
#  КЛАВИАТУРЫ
# ══════════════════════════════════════
def lang_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇷🇺 Русский язык", callback_data="lang_ru"),
        InlineKeyboardButton(text="🇺🇿 O'zbek tili",  callback_data="lang_uz"),
    ]])

def menu_kb(uid):
    l = lang(uid)
    rows = [
        [InlineKeyboardButton(text=t(uid,"btn_order"),    callback_data="menu_order"),
         InlineKeyboardButton(text=t(uid,"btn_calc"),     callback_data="menu_calc")],
        [InlineKeyboardButton(text=t(uid,"btn_prices"),   callback_data="menu_prices"),
         InlineKeyboardButton(text=t(uid,"btn_settings"), callback_data="menu_settings")],
        [InlineKeyboardButton(text=t(uid,"btn_promo"),    callback_data="menu_promo"),
         InlineKeyboardButton(text=t(uid,"btn_status"),   callback_data="menu_status")],
        [InlineKeyboardButton(text=t(uid,"btn_operator"), callback_data="menu_operator"),
         InlineKeyboardButton(text=t(uid,"btn_info"),     callback_data="menu_info")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def settings_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid,"btn_change_lang"), callback_data="settings_lang")],
        [InlineKeyboardButton(text=t(uid,"btn_help"),        callback_data="menu_help")],
        [InlineKeyboardButton(text=t(uid,"btn_menu"),        callback_data="go_menu")],
    ])

def back_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(uid,"btn_menu"), callback_data="go_menu")
    ]])

def phone_kb(uid):
    """ReplyKeyboard с кнопкой Поделиться номером"""
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text=t(uid,"btn_share_phone"), request_contact=True),
            KeyboardButton(text=t(uid,"btn_enter_phone")),
        ]],
        resize_keyboard=True, one_time_keyboard=True
    )

def location_kb(uid):
    """ReplyKeyboard с кнопками Отправить локацию и Пропустить"""
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text=t(uid,"btn_send_loc"), request_location=True),
            KeyboardButton(text=t(uid,"btn_skip_loc")),
        ]],
        resize_keyboard=True, one_time_keyboard=True
    )

def branch_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(uid,"btn_zarafshan"), callback_data="branch_zarafshan"),
        InlineKeyboardButton(text=t(uid,"btn_navoi"),     callback_data="branch_navoi"),
    ],[
        InlineKeyboardButton(text=t(uid,"btn_cancel"), callback_data="cancel_order"),
    ]])

def city_kb(uid, branch):
    cities = CITIES[branch][lang(uid)]
    rows = [[InlineKeyboardButton(text=c, callback_data=f"city_{i}")] for i,c in enumerate(cities)]
    rows.append([InlineKeyboardButton(text=t(uid,"btn_cancel"), callback_data="cancel_order")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def service_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid,"btn_svc_carpet"),      callback_data="svc_carpet")],
        [InlineKeyboardButton(text=t(uid,"btn_svc_carpet_home"), callback_data="svc_carpet_home")],
        [InlineKeyboardButton(text=t(uid,"btn_svc_sofa"),        callback_data="svc_sofa")],
        [InlineKeyboardButton(text=t(uid,"btn_svc_mattress"),    callback_data="svc_mattress")],
        [InlineKeyboardButton(text=t(uid,"btn_svc_curtains"),    callback_data="svc_curtains")],
        [InlineKeyboardButton(text=t(uid,"btn_cancel"),          callback_data="cancel_order")],
    ])

def service_type_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid,"btn_type_standard"), callback_data="svctype_standard")],
        [InlineKeyboardButton(text=t(uid,"btn_type_express"),  callback_data="svctype_express")],
        [InlineKeyboardButton(text=t(uid,"btn_cancel"),        callback_data="cancel_order")],
    ])

def date_kb(uid):
    from datetime import date, timedelta
    today    = date.today().strftime("%d.%m.%Y")
    tomorrow = (date.today() + timedelta(days=1)).strftime("%d.%m.%Y")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid,"btn_today")    + f" ({today})",    callback_data=f"date_{today}")],
        [InlineKeyboardButton(text=t(uid,"btn_tomorrow") + f" ({tomorrow})", callback_data=f"date_{tomorrow}")],
        [InlineKeyboardButton(text=t(uid,"btn_pick_date"), callback_data="date_pick")],
        [InlineKeyboardButton(text=t(uid,"btn_cancel"),    callback_data="cancel_order")],
    ])

def time_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid,"btn_morning"),     callback_data="time_morning")],
        [InlineKeyboardButton(text=t(uid,"btn_evening"),     callback_data="time_evening")],
        [InlineKeyboardButton(text=t(uid,"btn_custom_time"), callback_data="time_custom")],
        [InlineKeyboardButton(text=t(uid,"btn_cancel"),      callback_data="cancel_order")],
    ])

def cancel_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(uid,"btn_cancel"), callback_data="cancel_order")
    ]])

# ══════════════════════════════════════
#  ОТПРАВКА ДАННЫХ
# ══════════════════════════════════════
async def send_to_sheets(data: dict):
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(SHEETS_URL, json=data, timeout=aiohttp.ClientTimeout(total=10))
    except Exception as e:
        logging.warning(f"Sheets error: {e}")

async def notify_group(text: str, order_num: int = None, client_id: int = None, phone: str = None, username: str = None):
    """Отправляет заявку в группу сотрудников с кнопками действий"""
    kb = None
    if order_num and client_id:
        if username:
            msg_button = InlineKeyboardButton(text="✉️ Написать", url=f"https://t.me/{username}")
        else:
            msg_button = InlineKeyboardButton(text="✉️ Написать", url=f"tg://user?id={client_id}")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Принять заказ",  callback_data=f"accept_{order_num}_{client_id}"),
                msg_button,
            ],
            [
                InlineKeyboardButton(text="🚗 Назначить водителя", callback_data=f"driver_{order_num}_{client_id}"),
                InlineKeyboardButton(text="❌ Отклонить",          callback_data=f"reject_{order_num}_{client_id}"),
            ],
        ])
    try:
        await bot.send_message(GROUP_ID, text, reply_markup=kb)
    except Exception as e:
        logging.warning(f"Group notify error: {e}")
        # Если не получилось в группу — отправляем лично
        try:
            await bot.send_message(ADMIN_ID, text, reply_markup=kb)
        except Exception as e2:
            logging.warning(f"Admin notify error: {e2}")

async def notify_admin(text: str):
    """Личные сообщения администратору (от оператора)"""
    try:
        await bot.send_message(ADMIN_ID, text, parse_mode="Markdown")
    except Exception as e:
        logging.warning(f"Admin notify error: {e}")

# ══════════════════════════════════════
#  HANDLERS
# ══════════════════════════════════════
@dp.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    uid = msg.from_user.id

    # Если язык ещё не известен в этой сессии — пробуем подгрузить из БД
    if uid not in user_lang:
        try:
            saved_lang = await get_client_lang(uid)
        except Exception as e:
            logging.warning(f"get_client_lang error: {e}")
            saved_lang = None
        if saved_lang in ("ru", "uz"):
            user_lang[uid] = saved_lang

    # Сохраняем/обновляем клиента в БД
    await upsert_client(
        tg_id=uid,
        username=msg.from_user.username,
        first_name=msg.from_user.first_name,
        last_name=msg.from_user.last_name,
        lang=user_lang.get(uid,"ru")
    )

    if uid in user_lang:
        await msg.answer(t(uid,"menu_title"), reply_markup=menu_kb(uid), parse_mode="Markdown")
    else:
        await msg.answer("👋", reply_markup=lang_kb())

@dp.callback_query(F.data.in_({"lang_ru","lang_uz"}))
async def set_language(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    user_lang[uid] = "ru" if cb.data == "lang_ru" else "uz"
    try:
        await set_client_lang(uid, user_lang[uid])
    except Exception as e:
        logging.warning(f"set_client_lang error: {e}")
    await cb.message.edit_text(t(uid,"lang_set"))
    await cb.message.answer(t(uid,"menu_title"), reply_markup=menu_kb(uid), parse_mode="Markdown")

@dp.callback_query(F.data == "go_menu")
async def go_menu(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    await state.clear()
    if uid not in user_lang:
        try:
            saved_lang = await get_client_lang(uid)
        except Exception as e:
            logging.warning(f"get_client_lang error: {e}")
            saved_lang = None
        if saved_lang in ("ru", "uz"):
            user_lang[uid] = saved_lang
        else:
            await cb.message.answer("👋", reply_markup=lang_kb())
            return
    await cb.message.answer(t(uid,"menu_title"), reply_markup=menu_kb(uid), parse_mode="Markdown")

# ── МЕНЮ ПУНКТЫ ──
@dp.callback_query(F.data == "menu_prices")
async def menu_prices(cb: CallbackQuery):
    uid = cb.from_user.id
    await cb.message.answer(build_prices_text(uid), reply_markup=back_kb(uid), parse_mode="Markdown")

@dp.callback_query(F.data == "menu_branches")
async def menu_branches(cb: CallbackQuery):
    uid = cb.from_user.id
    await cb.message.answer(t(uid,"branches_text"), reply_markup=back_kb(uid), parse_mode="Markdown")

def promo_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid,"btn_promo_telegram"),  url="https://t.me/artez_gilam_yuvish")],
        [InlineKeyboardButton(text=t(uid,"btn_promo_instagram"), url="https://www.instagram.com/ziyoboboev/")],
        [InlineKeyboardButton(text=t(uid,"btn_menu"), callback_data="go_menu")],
    ])

@dp.callback_query(F.data == "menu_promo")
async def menu_promo(cb: CallbackQuery):
    uid = cb.from_user.id
    await cb.message.answer(t(uid,"promo_text"), reply_markup=promo_kb(uid), parse_mode="Markdown")

@dp.callback_query(F.data == "menu_info")
async def menu_info(cb: CallbackQuery):
    uid = cb.from_user.id
    await cb.message.answer(t(uid,"info_text"), reply_markup=back_kb(uid), parse_mode="Markdown")

@dp.callback_query(F.data == "menu_help")
async def menu_help(cb: CallbackQuery):
    uid = cb.from_user.id
    await cb.message.answer(t(uid,"help_text"), reply_markup=back_kb(uid), parse_mode="Markdown")

@dp.callback_query(F.data == "menu_settings")
async def menu_settings(cb: CallbackQuery):
    uid = cb.from_user.id
    await cb.message.answer(t(uid,"settings_text"), reply_markup=settings_kb(uid), parse_mode="Markdown")

@dp.callback_query(F.data == "settings_lang")
async def settings_lang(cb: CallbackQuery):
    uid = cb.from_user.id
    await cb.message.answer(t(uid,"choose_lang_text"), reply_markup=lang_kb())

def status_menu_kb(uid, counts):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{t(uid,'status_btn_new')} ({counts['new']})",       callback_data="status_new"),
         InlineKeyboardButton(text=f"{t(uid,'status_btn_progress')} ({counts['progress']})", callback_data="status_progress")],
        [InlineKeyboardButton(text=f"{t(uid,'status_btn_done')} ({counts['done']})",     callback_data="status_done"),
         InlineKeyboardButton(text=f"{t(uid,'status_btn_cancelled')} ({counts['cancelled']})", callback_data="status_cancelled")],
        [InlineKeyboardButton(text=t(uid,"btn_menu"), callback_data="go_menu")],
    ])

@dp.callback_query(F.data == "menu_status")
async def menu_status(cb: CallbackQuery):
    uid = cb.from_user.id
    try:
        orders = await get_client_orders(uid)
    except Exception as e:
        logging.warning(f"get_client_orders error: {e}")
        orders = []

    counts = {"new": 0, "progress": 0, "done": 0, "cancelled": 0}
    for o in orders:
        for group, statuses in STATUS_GROUPS.items():
            if o["status"] in statuses:
                counts[group] += 1
                break

    if not orders:
        await cb.message.answer(t(uid,"status_empty"), reply_markup=back_kb(uid), parse_mode="Markdown")
        return

    await cb.message.answer(t(uid,"status_menu_title"), reply_markup=status_menu_kb(uid, counts), parse_mode="Markdown")

def back_to_status_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid,"btn_back_to_status"), callback_data="menu_status")],
        [InlineKeyboardButton(text=t(uid,"btn_menu"), callback_data="go_menu")],
    ])

@dp.callback_query(F.data.in_({"status_new","status_progress","status_done","status_cancelled"}))
async def show_status_group(cb: CallbackQuery):
    uid   = cb.from_user.id
    group = cb.data.replace("status_","")
    statuses = STATUS_GROUPS.get(group, [])

    try:
        orders = await get_client_orders(uid)
    except Exception as e:
        logging.warning(f"get_client_orders error: {e}")
        orders = []

    filtered = [o for o in orders if o["status"] in statuses]

    group_titles = {
        "new": "status_btn_new", "progress": "status_btn_progress",
        "done": "status_btn_done", "cancelled": "status_btn_cancelled",
    }
    title = t(uid, group_titles.get(group, "status_btn_new"))

    if not filtered:
        text = f"{title}\n\n" + t(uid,"status_group_empty")
    else:
        lines = [f"{title}\n"]
        for o in filtered:
            lines.append(
                t(uid,"status_order_line").format(
                    num=o["order_num"],
                    service=o["service"] or "",
                    date=o["pickup_date"] or "",
                    status=order_status_name(uid, o["status"]),
                )
            )
        text = "\n\n".join(lines)

    await cb.message.answer(text, reply_markup=back_to_status_kb(uid), parse_mode="Markdown")


# ── ОПЕРАТОР ──
@dp.callback_query(F.data == "menu_operator")
async def menu_operator(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    await state.set_state(OperatorForm.message)
    await cb.message.answer(t(uid,"operator_text"), reply_markup=cancel_kb(uid), parse_mode="Markdown")

@dp.message(OperatorForm.message)
async def operator_message(msg: Message, state: FSMContext):
    uid      = msg.from_user.id
    username = msg.from_user.username or ""
    fname    = msg.from_user.first_name or ""
    lname    = msg.from_user.last_name  or ""
    fullname = f"{fname} {lname}".strip()

    # Формируем сообщение для оператора с кнопкой «Ответить»
    tg_link = f"tg://user?id={uid}"
    text = (
        f"💬 *Сообщение от клиента*\n"
        f"━━━━━━━━━━\n"
        f"👤 {md_escape(fullname)}" + (f" | @{md_escape(username)}" if username else "") + "\n"
        f"🆔 `{uid}`\n"
        f"━━━━━━━━━━\n"
        f"📝 {md_escape(msg.text)}\n"
        f"━━━━━━━━━━"
    )
    reply_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="↩️ Ответить клиенту",
            callback_data=f"reply_to_{uid}"
        )],
        [InlineKeyboardButton(
            text="📱 Открыть чат",
            url=tg_link
        )],
    ])
    # Отправляем в группу сообщений от клиентов
    try:
        await bot.send_message(GROUP_SMS_ID, text, parse_mode="Markdown", reply_markup=reply_kb)
    except Exception as e:
        logging.warning(f"Group SMS notify error (operator msg): {e}")
        await bot.send_message(ADMIN_ID, text, parse_mode="Markdown", reply_markup=reply_kb)
    # Подтверждение клиенту
    await msg.answer(t(uid,"operator_fwd"), reply_markup=back_kb(uid))
    await state.clear()

# ── ОПЕРАТОР НАЖАЛ «ОТВЕТИТЬ» ──
@dp.callback_query(F.data.startswith("reply_to_"))
async def admin_reply_start(cb: CallbackQuery, state: FSMContext):
    client_id = int(cb.data.replace("reply_to_",""))
    await state.set_state(AdminReply.waiting_reply)
    await state.update_data(reply_to_client=client_id)
    await cb.message.answer(
        f"✏️ Напишите ответ клиенту `{client_id}`:\n_(следующее сообщение будет отправлено ему)_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_admin_reply")
        ]])
    )
    await cb.answer()

@dp.callback_query(F.data == "cancel_admin_reply")
async def admin_reply_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Отменено.")
    await cb.answer()

@dp.message(AdminReply.waiting_reply)
async def admin_reply_send(msg: Message, state: FSMContext):
    data      = await state.get_data()
    client_id = data.get("reply_to_client")
    sender    = msg.from_user
    sname     = f"{sender.first_name or ''} {sender.last_name or ''}".strip()

    try:
        await bot.send_message(
            client_id,
            f"📩 *Сообщение от оператора ARTEZ*\n\n{md_escape(msg.text)}",
            parse_mode="Markdown"
        )
        await msg.answer(
            f"✅ Ответ отправлен клиенту `{client_id}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await msg.answer(f"⚠️ Не удалось отправить: {e}")

    await state.clear()

# ── ЗАЯВКА ──
@dp.callback_query(F.data == "menu_order")
async def menu_order(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    user_data_db[uid] = {}
    await state.set_state(OrderForm.name)
    await cb.message.answer(t(uid,"ask_name"), reply_markup=cancel_kb(uid), parse_mode="Markdown")

@dp.message(OrderForm.name)
async def order_name(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    user_data_db[uid]["name"] = msg.text
    await state.set_state(OrderForm.phone)
    await msg.answer(
        t(uid,"ask_phone"),
        reply_markup=phone_kb(uid),
        parse_mode="Markdown"
    )

# Клиент нажал «Поделиться номером» — Telegram прислал contact
@dp.message(OrderForm.phone, F.contact)
async def order_phone_contact(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    phone = msg.contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone
    user_data_db[uid]["phone"] = phone
    await state.set_state(OrderForm.branch)
    # Убираем ReplyKeyboard
    await msg.answer("✅", reply_markup=ReplyKeyboardRemove())
    await msg.answer(t(uid,"ask_branch"), reply_markup=branch_kb(uid))

# Клиент нажал «Ввести другой номер»
@dp.message(OrderForm.phone, F.text == "⌨️ Ввести другой номер")
@dp.message(OrderForm.phone, F.text == "⌨️ Boshqa raqam kiritish")
async def order_phone_manual_prompt(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    await msg.answer(
        t(uid,"ask_phone_manual"),
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )

# Клиент ввёл номер вручную — валидация
import re
PHONE_RE = re.compile(r"^\+998\d{9}$")

@dp.message(OrderForm.phone, F.text)
async def order_phone_text(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    raw = msg.text.strip().replace(" ","").replace("-","").replace("(","").replace(")","")
    if raw.startswith("998") and not raw.startswith("+"):
        raw = "+" + raw
    if not PHONE_RE.match(raw):
        await msg.answer(t(uid,"phone_invalid"), parse_mode="Markdown")
        return
    user_data_db[uid]["phone"] = raw
    await state.set_state(OrderForm.branch)
    await msg.answer("✅", reply_markup=ReplyKeyboardRemove())
    await msg.answer(t(uid,"ask_branch"), reply_markup=branch_kb(uid))

@dp.callback_query(F.data.in_({"branch_zarafshan","branch_navoi"}))
async def order_branch(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    branch = cb.data.replace("branch_","")
    user_data_db[uid]["branch"] = branch
    user_data_db[uid]["branch_name"] = t(uid,"btn_zarafshan") if branch=="zarafshan" else t(uid,"btn_navoi")
    await state.set_state(OrderForm.city)
    await cb.message.answer(t(uid,"ask_city"), reply_markup=city_kb(uid, branch))

@dp.callback_query(F.data.startswith("city_"))
async def order_city(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    idx = int(cb.data.replace("city_",""))
    branch = user_data_db[uid].get("branch","zarafshan")
    city = CITIES[branch][lang(uid)][idx]
    user_data_db[uid]["city"] = city
    await state.set_state(OrderForm.address)
    await cb.message.answer(t(uid,"ask_address"), reply_markup=cancel_kb(uid))

@dp.message(OrderForm.address)
async def order_address(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    user_data_db[uid]["address"] = msg.text
    await state.set_state(OrderForm.location)
    await msg.answer(
        t(uid,"ask_location"),
        reply_markup=location_kb(uid),
        parse_mode="Markdown"
    )

# Клиент отправил локацию
@dp.message(OrderForm.location, F.location)
async def order_location_geo(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    lat = msg.location.latitude
    lon = msg.location.longitude
    user_data_db[uid]["location"] = f"{lat:.5f}, {lon:.5f}"
    await state.set_state(OrderForm.service)
    await msg.answer("📍 ✅", reply_markup=ReplyKeyboardRemove())
    await msg.answer(t(uid,"ask_service"), reply_markup=service_kb(uid))

# Клиент нажал «Пропустить»
@dp.message(OrderForm.location, F.text)
async def order_location_skip(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    user_data_db[uid]["location"] = ""
    await state.set_state(OrderForm.service)
    await msg.answer("⏭", reply_markup=ReplyKeyboardRemove())
    await msg.answer(t(uid,"ask_service"), reply_markup=service_kb(uid))

@dp.callback_query(OrderForm.service, F.data.startswith("svc_"))
async def order_service(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    svc = cb.data.replace("svc_","")
    svc_map = {
        "carpet":       t(uid,"btn_svc_carpet"),
        "carpet_home":  t(uid,"btn_svc_carpet_home"),
        "sofa":         t(uid,"btn_svc_sofa"),
        "mattress":     t(uid,"btn_svc_mattress"),
        "curtains":     t(uid,"btn_svc_curtains"),
    }
    user_data_db[uid]["service"] = svc_map.get(svc, svc)
    await state.set_state(OrderForm.service_type)
    await cb.message.answer(t(uid,"ask_service_type"), reply_markup=service_type_kb(uid))

@dp.callback_query(OrderForm.service_type, F.data.startswith("svctype_"))
async def order_service_type(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    svctype = cb.data.replace("svctype_","")
    type_map = {
        "standard": t(uid,"btn_type_standard"),
        "express":  t(uid,"btn_type_express"),
    }
    user_data_db[uid]["service_type"] = type_map.get(svctype, svctype)
    await state.set_state(OrderForm.date)
    await cb.message.answer(t(uid,"ask_date"), reply_markup=date_kb(uid))

# ── ДАТА — кнопки Сегодня/Завтра ──
@dp.callback_query(F.data.startswith("date_") & (F.data != "date_pick"))
async def order_date_btn(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    if cb.data == "date_pick":
        return await order_date_pick(cb, state)
    date_val = cb.data.replace("date_","")
    user_data_db[uid]["date"] = date_val
    await state.set_state(OrderForm.time)
    await cb.message.answer(t(uid,"ask_time"), reply_markup=time_kb(uid))

# ── ДАТА — кнопка «Указать дату» (ручной ввод) ──
@dp.callback_query(F.data == "date_pick")
async def order_date_pick(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    await state.set_state(OrderForm.date)
    await cb.message.answer(t(uid,"ask_date_manual"), reply_markup=cancel_kb(uid), parse_mode="Markdown")

@dp.message(OrderForm.date)
async def order_date_manual(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    text = (msg.text or "").strip()
    m = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", text)
    valid = False
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            from datetime import date as dt_date
            d = dt_date(year, month, day)
            if d >= dt_date.today():
                valid = True
        except ValueError:
            valid = False
    if not valid:
        await msg.answer(t(uid,"date_invalid"), reply_markup=cancel_kb(uid), parse_mode="Markdown")
        return
    user_data_db[uid]["date"] = text
    await state.set_state(OrderForm.time)
    await msg.answer(t(uid,"ask_time"), reply_markup=time_kb(uid))


@dp.callback_query(F.data.in_({"time_morning","time_evening","time_custom"}))
async def order_time(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    if cb.data == "time_custom":
        await state.set_state(OrderForm.time_from)
        await cb.message.answer(t(uid,"ask_time_from"), parse_mode="Markdown",
                                reply_markup=cancel_kb(uid))
        return
    time_txt = t(uid,"btn_morning") if cb.data=="time_morning" else t(uid,"btn_evening")
    await finish_order(cb.message, uid, time_txt, state, user_from=cb.from_user)

@dp.message(OrderForm.time_from)
async def order_time_from(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    user_data_db[uid]["time_from"] = msg.text
    await state.set_state(OrderForm.time_to)
    await msg.answer(t(uid,"ask_time_to"), parse_mode="Markdown", reply_markup=cancel_kb(uid))

@dp.message(OrderForm.time_to)
async def order_time_to(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    time_from = user_data_db[uid].get("time_from","")
    time_to   = msg.text
    time_txt  = f"{time_from} — {time_to}"
    await finish_order(msg, uid, time_txt, state, user_from=msg.from_user)

async def finish_order(msg_or_cb, uid: int, time_txt: str, state: FSMContext, user_from=None):
    d = user_data_db.get(uid, {})
    order_num = await get_next_order_num()
    dt = now_local().strftime("%d.%m.%Y %H:%M")
    answer_fn = msg_or_cb.answer

    # Данные клиента из Telegram
    user_obj = user_from or getattr(msg_or_cb, 'from_user', None)
    first_name = getattr(user_obj, 'first_name', '') or ''
    last_name  = getattr(user_obj, 'last_name',  '') or ''
    username   = getattr(user_obj, 'username',   '') or ''
    tg_name    = f"{first_name} {last_name}".strip() or f"@{username}"

    # Сохраняем в PostgreSQL
    await save_order({
        "order_num":          order_num,
        "source":             "bot",
        "client_tg_id":       uid,
        "client_tg_username": username,
        "client_first_name":  first_name,
        "client_last_name":   last_name,
        "phone":              d.get("phone",""),
        "branch":             d.get("branch",""),
        "city":               d.get("city",""),
        "address":            d.get("address",""),
        "location":           d.get("location",""),
        "service":            d.get("service",""),
        "pickup_date":        d.get("date",""),
        "pickup_time":        time_txt,
        "note":               f"Тип услуги: {d.get('service_type','')}",
    })

    # Обновляем клиента в БД
    await upsert_client(
        tg_id=uid, username=username,
        first_name=first_name, last_name=last_name,
        phone=d.get("phone",""), lang=lang(uid)
    )

    # Уведомление клиенту
    await answer_fn(
        t(uid,"order_done").format(num=order_num),
        reply_markup=back_kb(uid), parse_mode="Markdown"
    )

    # Уведомление в группу
    loc = d.get("location","") or "—"
    summary = (
        f"📋 Новая заявка {order_num} (бот)\n"
        f"━━━━━━━━━━\n"
        f"👤 {md_escape(d.get('name',''))}\n"
        f"🆔 {uid}\n"
        f"📞 {md_escape(d.get('phone',''))}\n"
        f"🏢 {md_escape(d.get('branch_name',''))}\n"
        f"📍 {md_escape(d.get('city',''))}\n"
        f"🏠 {md_escape(d.get('address',''))}\n"
        f"🗺 {md_escape(loc)}\n"
        f"🧺 {md_escape(d.get('service',''))}\n"
        f"⚙️ {md_escape(d.get('service_type',''))}\n"
        f"📅 {md_escape(d.get('date',''))}\n"
        f"🕐 {md_escape(time_txt)}\n"
        f"━━━━━━━━━━\n"
        f"🕒 {dt}"
    )
    raw_phone = (d.get("phone","") or "").strip()
    client_phone = re.sub(r"[\s\-]", "", raw_phone)
    await notify_group(summary, order_num=order_num, client_id=uid, phone=client_phone, username=username)

    # В Google Таблицу
    await send_to_sheets({
        "name":        d.get("name",""),
        "tg_id":       str(uid),
        "tg_username": f"@{username}" if username else "",
        "tg_name":     tg_name,
        "phone":       d.get("phone",""),
        "branch":      d.get("branch_name",""),
        "city":        d.get("city",""),
        "address":     d.get("address",""),
        "location":    d.get("location",""),
        "service":     d.get("service",""),
        "service_type": d.get("service_type",""),
        "date":        d.get("date",""),
        "time":        time_txt,
        "note":        f"Telegram (бот) {order_num}",
        "status":      "Новый",
    })
    await state.clear()

# ── ОТМЕНА ──
@dp.callback_query(F.data == "cancel_order")
async def cancel_order(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    await state.clear()
    await cb.message.answer(t(uid,"cancel"), reply_markup=back_kb(uid))

# ── КАЛЬКУЛЯТОР ──
@dp.callback_query(F.data == "menu_calc")
async def menu_calc(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    user_data_db[uid] = {}
    await state.set_state(CalcForm.service)
    await cb.message.answer(t(uid,"calc_ask_svc"), reply_markup=service_kb(uid), parse_mode="Markdown")
    await cb.answer()

@dp.callback_query(CalcForm.service, F.data.startswith("svc_"))
async def calc_service(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    svc = cb.data.replace("svc_","")
    user_data_db[uid]["calc_svc"] = svc
    await state.set_state(CalcForm.service_type)
    await cb.message.answer(t(uid,"ask_service_type"), reply_markup=service_type_kb(uid))

@dp.callback_query(CalcForm.service_type, F.data.startswith("svctype_"))
async def calc_service_type(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    svctype = cb.data.replace("svctype_","")
    user_data_db[uid]["calc_svctype"] = svctype
    svc = user_data_db[uid].get("calc_svc","carpet")
    await state.set_state(CalcForm.width)
    header = t(uid,"calc_selected_header").format(svc=svc_display_name(uid, svc, svctype))
    await cb.message.answer(header + "\n\n" + t(uid,"calc_ask_w"), reply_markup=cancel_kb(uid), parse_mode="Markdown")

@dp.message(CalcForm.width)
async def calc_width(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    try:
        w = float(msg.text.replace(",","."))
        user_data_db[uid]["calc_w"] = w
        await state.set_state(CalcForm.length)
        d       = user_data_db.get(uid,{})
        svc     = d.get("calc_svc","carpet")
        svctype = d.get("calc_svctype","standard")
        header  = t(uid,"calc_selected_header").format(svc=svc_display_name(uid, svc, svctype))
        await msg.answer(header + "\n\n" + t(uid,"calc_ask_l"), reply_markup=cancel_kb(uid), parse_mode="Markdown")
    except:
        await msg.answer(t(uid,"invalid_num"))

@dp.message(CalcForm.length)
async def calc_length(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    try:
        l = float(msg.text.replace(",","."))
        user_data_db[uid]["calc_l"] = l
    except:
        await msg.answer(t(uid,"invalid_num"))
        return

    d   = user_data_db.get(uid,{})
    svc     = d.get("calc_svc","carpet")
    svctype = d.get("calc_svctype","standard")
    w       = d.get("calc_w",200)
    sqm_real = (w/100) * (l/100)
    if svc in MIN_ORDER_SERVICES:
        sqm_bill = max(sqm_real, 10)
    else:
        sqm_bill = sqm_real
    price    = get_cached_price(svc, svctype)
    total    = int(sqm_bill * price)

    if svc in MIN_ORDER_SERVICES:
        result = t(uid,"calc_result").format(
            w=int(w), l=int(l), sqm=round(sqm_real,2),
            svc=svc_display_name(uid, svc, svctype), price=f"{price:,}".replace(","," "),
            total=f"{total:,}".replace(","," ")
        )
    else:
        result = t(uid,"calc_result_no_min").format(
            w=int(w), l=int(l), sqm=round(sqm_real,2),
            svc=svc_display_name(uid, svc, svctype), price=f"{price:,}".replace(","," "),
            total=f"{total:,}".replace(","," ")
        )
    await msg.answer(result, reply_markup=back_kb(uid), parse_mode="Markdown")
    await state.clear()

# ── КНОПКИ В ГРУППЕ ──
@dp.callback_query(F.data.startswith("accept_"))
async def group_accept(cb: CallbackQuery):
    parts     = cb.data.split("_")
    order_num = parts[1]
    client_id = int(parts[2])
    w = cb.from_user
    wname = f"{w.first_name or ''} {w.last_name or ''}".strip()
    await update_order_status(
        order_num=order_num, new_status="confirmed",
        by_tg_id=w.id, by_name=wname,
        note=f"Принял оператор {wname}",
        extra={
            "operator_tg_id": w.id,
            "operator_username": w.username or "",
            "operator_first_name": w.first_name or "",
            "operator_last_name": w.last_name or "",
            "accepted_at": now_local().replace(tzinfo=None),
        }
    )
    await cb.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"✅ Принял: {wname}" + (f" @{w.username}" if w.username else ""),
            callback_data="done"
        )],
        [InlineKeyboardButton(text="🚗 Назначить водителя", callback_data=f"driver_{order_num}_{client_id}")]
    ]))
    try:
        await bot.send_message(client_id,
            f"✅ Ваша заявка *{order_num}* принята!\nМенеджер свяжется с вами в ближайшее время.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.warning(f"Client notify error: {e}")
    await cb.answer(f"Вы приняли заказ {order_num}")

@dp.callback_query(F.data.startswith("driver_"))
async def group_driver(cb: CallbackQuery):
    parts     = cb.data.split("_")
    order_num = parts[1]
    client_id = parts[2]

    drivers = await get_staff_by_role("driver")
    if not drivers:
        await cb.answer("⚠️ Список водителей пуст. Добавьте их командой /add_driver", show_alert=True)
        return

    rows = list(cb.message.reply_markup.inline_keyboard) if cb.message.reply_markup else []
    # Убираем строку с кнопкой "Назначить водителя" / "Отклонить", оставляем остальное (например "Принял")
    rows = [r for r in rows if not any(
        (btn.callback_data or "").startswith(("driver_", "reject_")) for btn in r
    )]
    for d in drivers:
        fname = f"{d['first_name'] or ''} {d['last_name'] or ''}".strip() or f"id{d['tg_id']}"
        rows.append([InlineKeyboardButton(
            text=f"🚗 {fname}",
            callback_data=f"setdriver_{order_num}_{client_id}_{d['tg_id']}"
        )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"backdriver_{order_num}_{client_id}")])

    await cb.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cb.answer()

@dp.callback_query(F.data.startswith("backdriver_"))
async def group_driver_back(cb: CallbackQuery):
    parts     = cb.data.split("_")
    order_num = parts[1]
    client_id = parts[2]

    rows = list(cb.message.reply_markup.inline_keyboard) if cb.message.reply_markup else []
    # Убираем строки с выбором водителя и "Назад"
    rows = [r for r in rows if not any(
        (btn.callback_data or "").startswith(("setdriver_", "backdriver_")) for btn in r
    )]
    already_accepted = any(
        (btn.callback_data or "") == "done" and "Принял" in (btn.text or "")
        for r in rows for btn in r
    )
    if already_accepted:
        rows.append([InlineKeyboardButton(text="🚗 Назначить водителя", callback_data=f"driver_{order_num}_{client_id}")])
    else:
        rows.append([
            InlineKeyboardButton(text="🚗 Назначить водителя", callback_data=f"driver_{order_num}_{client_id}"),
            InlineKeyboardButton(text="❌ Отклонить",          callback_data=f"reject_{order_num}_{client_id}"),
        ])
    await cb.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cb.answer()

@dp.callback_query(F.data.startswith("setdriver_"))
async def group_set_driver(cb: CallbackQuery):
    parts        = cb.data.split("_")
    order_num    = parts[1]
    client_id    = parts[2]
    driver_tg_id = int(parts[3])

    drivers = await get_staff_by_role("driver")
    driver  = next((d for d in drivers if d["tg_id"] == driver_tg_id), None)
    if not driver:
        await cb.answer("⚠️ Водитель не найден", show_alert=True)
        return

    dname = f"{driver['first_name'] or ''} {driver['last_name'] or ''}".strip() or f"id{driver_tg_id}"
    chooser = cb.from_user
    chooser_name = f"{chooser.first_name or ''} {chooser.last_name or ''}".strip()

    await update_order_status(
        order_num=order_num, new_status="pickup",
        by_tg_id=chooser.id, by_name=chooser_name,
        note=f"{chooser_name} назначил водителем: {dname}",
        extra={
            "driver_pickup_tg_id": driver["tg_id"],
            "driver_pickup_username": driver["tg_username"] or "",
            "driver_pickup_first_name": driver["first_name"] or "",
            "driver_pickup_last_name": driver["last_name"] or "",
            "pickup_at": now_local().replace(tzinfo=None),
        }
    )

    rows = list(cb.message.reply_markup.inline_keyboard) if cb.message.reply_markup else []
    rows = [r for r in rows if not any(
        (btn.callback_data or "").startswith(("setdriver_", "backdriver_")) for btn in r
    )]
    rows.append([InlineKeyboardButton(
        text=f"🚗 Водитель: {dname}" + (f" @{driver['tg_username']}" if driver["tg_username"] else ""),
        callback_data="done"
    )])
    await cb.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    try:
        await bot.send_message(driver["tg_id"],
            f"🚗 Вам назначен заказ *{order_num}* на вывоз/доставку.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.warning(f"Driver notify error: {e}")

    await cb.answer(f"Водитель {dname} назначен на заказ {order_num}", show_alert=True)


@dp.callback_query(F.data.startswith("reject_"))
async def group_reject(cb: CallbackQuery):
    parts     = cb.data.split("_")
    order_num = parts[1]
    client_id = int(parts[2])
    w = cb.from_user
    wname = f"{w.first_name or ''} {w.last_name or ''}".strip()
    await update_order_status(
        order_num=order_num, new_status="cancelled",
        by_tg_id=w.id, by_name=wname,
        note=f"Отклонил {wname}"
    )
    await cb.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"❌ Отклонил: {wname}", callback_data="done")]
    ]))
    try:
        await bot.send_message(client_id,
            t(client_id, "order_rejected").format(num=order_num),
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.warning(f"Client notify error: {e}")
    await cb.answer(f"Заказ {order_num} отклонён")

# ── КОМАНДЫ ──
@dp.message(Command("order"))
async def cmd_order(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    if uid not in user_lang:
        await msg.answer("👋", reply_markup=lang_kb()); return
    user_data_db[uid] = {}
    await state.set_state(OrderForm.name)
    await msg.answer(t(uid,"ask_name"), reply_markup=cancel_kb(uid), parse_mode="Markdown")

@dp.message(Command("calc"))
async def cmd_calc(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    if uid not in user_lang:
        await msg.answer("👋", reply_markup=lang_kb()); return
    user_data_db[uid] = {}
    await state.set_state(CalcForm.service)
    await msg.answer(t(uid,"calc_ask_svc"), reply_markup=service_kb(uid), parse_mode="Markdown")

@dp.message(Command("prices"))
async def cmd_prices(msg: Message):
    uid = msg.from_user.id
    if uid not in user_lang:
        await msg.answer("👋", reply_markup=lang_kb()); return
    await msg.answer(build_prices_text(uid), reply_markup=back_kb(uid), parse_mode="Markdown")

@dp.message(Command("branches"))
async def cmd_branches(msg: Message):
    uid = msg.from_user.id
    if uid not in user_lang:
        await msg.answer("👋", reply_markup=lang_kb()); return
    await msg.answer(t(uid,"branches_text"), reply_markup=back_kb(uid), parse_mode="Markdown")

# ── АДМИН: ЦЕНЫ ──
@dp.message(Command("prices_admin"))
async def cmd_prices_admin(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return
    lines = ["💰 *Текущие цены* (ключ для /setprice)", ""]
    for svc in SERVICE_KEYS:
        prices = PRICE_CACHE.get(svc, DEFAULT_PRICES.get(svc, {}))
        lines.append(f"*{SERVICE_NAMES_RU.get(svc, svc)}* (`{svc}`)")
        for tk in TYPE_KEYS:
            entry = prices.get(tk)
            if entry:
                lines.append(f"   {TYPE_NAMES_RU.get(tk, tk)} (`{tk}`): {entry['price']:,}".replace(",", " ") + " сум")
        lines.append("")
    lines.append("Изменить: `/setprice <услуга> <тип> <цена>`")
    lines.append("Пример: `/setprice carpet standard 13000`")
    await msg.answer("\n".join(lines), parse_mode="Markdown")

@dp.message(Command("setprice"))
async def cmd_setprice(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return
    args = (msg.text or "").split()[1:]
    if len(args) != 3:
        await msg.answer(
            "⚠️ Формат: `/setprice <услуга> <тип> <цена>`\n"
            f"Услуги: {', '.join(SERVICE_KEYS)}\n"
            f"Типы: {', '.join(TYPE_KEYS)}\n"
            "Пример: `/setprice carpet standard 13000`",
            parse_mode="Markdown"
        )
        return
    svc, tk, price_str = args
    if svc not in SERVICE_KEYS:
        await msg.answer(f"⚠️ Неизвестная услуга `{svc}`. Доступны: {', '.join(SERVICE_KEYS)}", parse_mode="Markdown")
        return
    if tk not in TYPE_KEYS:
        await msg.answer(f"⚠️ Неизвестный тип `{tk}`. Доступны: {', '.join(TYPE_KEYS)}", parse_mode="Markdown")
        return
    try:
        price = int(price_str)
        if price <= 0:
            raise ValueError
    except ValueError:
        await msg.answer("⚠️ Цена должна быть положительным целым числом.")
        return
    ok = await set_price(svc, tk, price)
    if ok:
        await load_prices()
        await msg.answer(
            f"✅ Цена обновлена: {SERVICE_NAMES_RU.get(svc, svc)} / {TYPE_NAMES_RU.get(tk, tk)} = "
            f"{price:,}".replace(",", " ") + " сум"
        )
    else:
        await msg.answer("⚠️ Не удалось обновить цену (БД недоступна).")

# ── АДМИН: ВОДИТЕЛИ ──
@dp.message(Command("add_driver"))
async def cmd_add_driver(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return
    args = (msg.text or "").split(maxsplit=2)[1:]
    if len(args) < 2:
        await msg.answer(
            "⚠️ Формат: `/add_driver <tg_id> <Имя> [Фамилия]`\n"
            "Пример: `/add_driver 624826036 Ботир Каримов`",
            parse_mode="Markdown"
        )
        return
    try:
        tg_id = int(args[0])
    except ValueError:
        await msg.answer("⚠️ tg_id должен быть числом.")
        return
    name_parts = args[1].split(maxsplit=1)
    first_name = name_parts[0]
    last_name  = name_parts[1] if len(name_parts) > 1 else ""
    ok = await add_staff(tg_id=tg_id, first_name=first_name, last_name=last_name, role="driver")
    if ok:
        await msg.answer(f"✅ Водитель добавлен: {first_name} {last_name} (id {tg_id})")
    else:
        await msg.answer("⚠️ Не удалось добавить водителя (БД недоступна).")

@dp.message(Command("del_driver"))
async def cmd_del_driver(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return
    args = (msg.text or "").split()[1:]
    if len(args) != 1:
        await msg.answer("⚠️ Формат: `/del_driver <tg_id>`", parse_mode="Markdown")
        return
    try:
        tg_id = int(args[0])
    except ValueError:
        await msg.answer("⚠️ tg_id должен быть числом.")
        return
    ok = await remove_staff(tg_id)
    if ok:
        await msg.answer(f"✅ Водитель (id {tg_id}) удалён из списка.")
    else:
        await msg.answer("⚠️ Водитель с таким id не найден.")

@dp.message(Command("drivers"))
async def cmd_drivers(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return
    drivers = await get_staff_by_role("driver")
    if not drivers:
        await msg.answer(
            "📋 Список водителей пуст.\n\n"
            "Добавить: `/add_driver <tg_id> <Имя> [Фамилия]`",
            parse_mode="Markdown"
        )
        return
    lines = ["🚗 *Водители:*", ""]
    for d in drivers:
        uname = f" @{d['tg_username']}" if d["tg_username"] else ""
        lines.append(f"• {d['first_name']} {d['last_name'] or ''} (id `{d['tg_id']}`){uname}".replace("  ", " "))
    lines.append("")
    lines.append("Удалить: `/del_driver <tg_id>`")
    await msg.answer("\n".join(lines), parse_mode="Markdown")


# ── ЗАПУСК ──
async def main():
    logging.info("🚀 ARTEZ Bot starting...")
    await init_db()
    await load_prices()
    logging.info("✅ Bot started, polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
