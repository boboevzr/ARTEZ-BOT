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
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    WebAppInfo
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from database import init_db, upsert_client, save_order, update_order_status, get_client_orders, get_stats, get_next_order_num, get_all_prices, get_price, add_staff, remove_staff, get_staff_by_role, get_client_lang, set_client_lang, get_all_units, get_unit, add_unit, delete_unit, upsert_crm_client, get_client_by_tg_id, update_client_tg_phone, get_client_tg_phone, get_staff_by_tg_id_for_lead, take_lead, is_client_blocked, get_order_by_id, update_order_status_by_id, get_order_activity_by_id, get_route_delivery_info

logging.basicConfig(level=logging.INFO)

BOT_TOKEN   = os.getenv("BOT_TOKEN", "8871514482:AAGEqOUDPoAeCyyu8gvGa0ZkKRgqV28Yo5A")
ADMIN_ID    = int(os.getenv("ADMIN_ID") or "624826036")       # ваш личный ID (для сообщений от оператора)
GROUP_ID           = int(os.getenv("GROUP_ID") or "-5211502458")      # группа сотрудников (заявки)
GROUP_ID_ZARAFSHAN = int(os.getenv("GROUP_ID_ZARAFSHAN") or "0")        # группа Зарафшан
GROUP_ID_NAVOI     = int(os.getenv("GROUP_ID_NAVOI") or "0")            # группа Навои
GROUP_SMS_ID           = int(os.getenv("GROUP_SMS_ID") or "-5303335722")    # группа сообщений от клиентов
GROUP_NEW_CLIENTS_ID   = int(os.getenv("GROUP_NEW_CLIENTS_ID") or "0")        # группа новых клиентов
SHEETS_URL  = os.getenv("SHEETS_URL", "https://script.google.com/macros/s/AKfycbyU5a3pMuTFme3dBNEgu46qzA1sN1Ekw-Q7p39F1Pg872lnnXZEFhJPjuc4TzZNHlpObQ/exec")
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://artez.uz")
API_URL     = os.getenv("API_URL", "https://artez-api-production.up.railway.app/api")

# Настройки сайта — загружаются при старте из API, используются во всех сообщениях
SITE = {
    "contact_short":      "1221",
    "contact_main":       "+998 79 222-12-21",
    "contact_zarafshan_1": "+998 88 200-12-21",
    "contact_zarafshan_2": "+998 94 738-04-44",
    "contact_navoi_1":    "+998 99 750-00-20",
    "contact_navoi_2":    "+998 99 112-48-48",
    "social_tg_group":    "https://t.me/artez_gilam_yuvish",
    "social_tg_bot":      "https://t.me/artez_orders_bot",
    "social_instagram":   "https://www.instagram.com/ziyoboboev/",
}

async def load_site_settings():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_URL}/settings/site", timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status == 200:
                    data = await r.json()
                    s = data.get("settings", {})
                    for k, v in s.items():
                        if v:
                            SITE[k] = v
                    _rebuild_dynamic_texts()
                    logging.info("✅ Site settings loaded from API")
    except Exception as e:
        logging.warning(f"Could not load site settings: {e}")

def _rebuild_dynamic_texts():
    """Обновляет строки в TEXTS которые содержат номера телефонов и ссылки."""
    sh  = SITE["contact_short"]
    mn  = SITE["contact_main"]
    z1  = SITE["contact_zarafshan_1"]
    z2  = SITE["contact_zarafshan_2"]
    n1  = SITE["contact_navoi_1"]
    n2  = SITE["contact_navoi_2"]
    tg  = SITE["social_tg_group"]
    ins = SITE["social_instagram"]

    TEXTS["ru"]["menu_title"] = (
        f"🏠 Главное меню\n\nООО «ARTEZ» — профессиональная чистка ковров\n"
        f"📍 Зарафшан и Навои\n🌐 [artez.uz](https://artez.uz)\n\n"
        f"☎️ Короткий номер: {sh}\n📞 Оператор:\n{mn}\n\n"
        f"*г. Зарафшан*\n📱 {z1}\n📱 {z2}\n\n"
        f"*г. Навои*\n📱 {n1}\n📱 {n2}"
    )
    TEXTS["uz"]["menu_title"] = (
        f"🏠 Asosiy menyu\n\nARTEZ MChJ — professional gilam tozalash\n"
        f"📍 Zarafshon va Navoiy\n🌐 [artez.uz](https://artez.uz)\n\n"
        f"☎️ Qisqa raqam: {sh}\n📞 Operator:\n{mn}\n\n"
        f"*Zarafshon shahri*\n📱 {z1}\n📱 {z2}\n\n"
        f"*Navoiy shahri*\n📱 {n1}\n📱 {n2}"
    )
    TEXTS["ru"]["order_done"] = (
        f"✅ *Заявка принята!*\n\nМы перезвоним вам в течение 30 минут.\n\n"
        f"Номер заявки: *#{{num}}*\n\n"
        f"☎️ Короткий номер: *{sh}*\n📞 {mn}\n\n"
        f"*Зарафшан:* {z1} / {z2}\n*Навои:* {n1} / {n2}"
    )
    TEXTS["uz"]["order_done"] = (
        f"✅ *Ariza qabul qilindi!*\n\n30 daqiqa ichida qayta qo'ng'iroq qilamiz.\n\n"
        f"Ariza raqami: *#{{num}}*\n\n"
        f"☎️ Qisqa raqam: *{sh}*\n📞 {mn}\n\n"
        f"*Zarafshon:* {z1} / {z2}\n*Navoiy:* {n1} / {n2}"
    )
    TEXTS["ru"]["order_rejected"] = (
        f"❌ К сожалению, заявка *{{num}}* не может быть выполнена.\n\n"
        f"Позвоните нам:\n☎️ {sh}\n📞 {mn}"
    )
    TEXTS["uz"]["order_rejected"] = (
        f"❌ Afsuski, *{{num}}* arizasi bajarilishi mumkin emas.\n\n"
        f"Bizga qo'ng'iroq qiling:\n☎️ {sh}\n📞 {mn}"
    )
    TEXTS["ru"]["branches_text"] = (
        f"📍 *Наши филиалы*\n\n"
        f"🏢 *Филиал Зарафшан*\nОбслуживает: Зарафшан, Учкудук, Тамдинский район\n"
        f"📞 {sh}\n📱 {mn}\n📱 {z1}\n📱 {z2}\n\n"
        f"🏢 *Филиал Навои*\nОбслуживает: Навои и все остальные районы области\n"
        f"📞 {sh}\n📱 {mn}\n📱 {n1}\n📱 {n2}"
    )
    TEXTS["uz"]["branches_text"] = (
        f"📍 *Filiallarimiz*\n\n"
        f"🏢 *Zarafshon filiali*\nXizmat ko'rsatadi: Zarafshon, Uchquduq, Tomdi tumani\n"
        f"📞 {sh}\n📱 {mn}\n📱 {z1}\n📱 {z2}\n\n"
        f"🏢 *Navoiy filiali*\nXizmat ko'rsatadi: Navoiy va viloyatning boshqa tumanlari\n"
        f"📞 {sh}\n📱 {mn}\n📱 {n1}\n📱 {n2}"
    )
    # Telegram и Instagram кнопки обновляются через promo_kb — ссылки в SITE

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
        "menu_title":     "🏠 Главное меню\n\nООО «ARTEZ» — профессиональная чистка ковров\n📍 Зарафшан и Навои\n🌐 [artez.uz](https://artez.uz)\n\n☎️ Короткий номер: 1221\n📞 Оператор:\n+998 79 222 12 21\n\n*г. Зарафшан*\n📱 +998 88 200 12 21\n📱 +998 94 738 04 44\n\n*г. Навои*\n📱 +998 99 750 00 20\n📱 +998 99 112 48 48",
        "btn_webapp":     "🌐 Открыть приложение",
        "btn_order":      "📋 Оставить заявку",
        "btn_calc":       "🧮 Калькулятор",
        "btn_prices":     "💰 Цены",
        "btn_branches":   "📍 Филиалы",
        "btn_promo":      "🎁 Акции",
        "btn_status":     "📦 Статус заказа",
        "btn_operator":   "👨‍💼 Оператор",
        "btn_info":       "ℹ️ О компании",
        "btn_profile":    "👤 Мой профиль",
        "profile_text":   "👤 *Ваш профиль*\n\n📛 Имя: {name}\n📞 Телефон: {phone}\n🆔 ID: {uid}\n\n📊 Заявок всего: *{total}*\n✅ Выполнено: *{done}*\n{last}",
        "profile_last":   "📅 Последняя заявка: {date}\n",
        "profile_nophone":"Не указан",
        "profile_link_phone": "📞 Привязать номер",
        "btn_use_saved_phone": "✅ Использовать {phone}",
        "btn_enter_other_phone": "⌨️ Ввести другой номер",
        "ask_phone_saved":"Шаг 2 из 7\n📞 Использовать сохранённый номер?",
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
        "link_phone_prompt": (
            "🔗 *Привязка номера к сайту ARTEZ*\n\n"
            "Нажмите кнопку ниже, чтобы поделиться своим номером телефона.\n"
            "После этого при регистрации на сайте *artez.uz* вы сможете получить код через Telegram вместо SMS."
        ),
        "link_phone_ok": (
            "✅ *Номер привязан!*\n\n"
            "📱 {phone}\n\n"
            "Теперь зайдите на сайт *artez.uz*, выберите «Регистрация» и нажмите «Получить код в Telegram».\n\n"
            "Если вы уже зарегистрированы — просто войдите в личный кабинет."
        ),
        "link_phone_ok_registered": (
            "✅ *Телефон привязан!*\n\n"
            "📱 {phone}\n\n"
            "Вы уже зарегистрированы на сайте — просто войдите на *artez.uz*."
        ),
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
        "order_done":     "✅ *Заявка принята!*\n\nМы перезвоним вам в течение 30 минут.\n\nНомер заявки: *#{num}*\n\n☎️ Короткий номер: *1221*\n📞 +998 79 222-12-21\n\n*Зарафшан:*\n+998 88 200-12-21\n+998 94 738-04-44\n\n*Навои:*\n+998 99 750-00-20\n+998 99 112-48-48",
        "order_rejected": "❌ К сожалению, заявка *{num}* не может быть выполнена.\n\nПозвоните нам:\n☎️ 1221\n📞 +998 79 222-12-21",
        "order_summary":  "📋 *Новая заявка #{num}* (бот)\n━━━━━━━━━━━━━━━\n👤 {name}\n📞 {phone}\n🏢 {branch}\n📍 {city}\n🏠 {address}\n🗺 {location}\n🧺 {service}\n📅 {date}\n🕐 {time}\n━━━━━━━━━━━━━━━\n🕒 {dt}",
        "prices_text":    "💰 *Прайс-лист ARTEZ*\n\n🧺 Стандартная чистка — 12 000 сум/м²\n✨ Глубокая химчистка — 16 000 сум/м²\n🛋 Бытовая техника/Понка — от 16 000 сум/шт\n🌿 Сухая чистка — 14 000 сум/м²\n\n📦 Минимальный заказ — 10 м²\n🚚 Вывоз и доставка — *бесплатно*",
        "calc_selected_header": "🧮 *Калькулятор стоимости*\n\n🧺 Услуга: {svc}",
        "calc_ask_w":     "Введите ширину в сантиметрах:\n\nПример: 200 (= 2 метра)",
        "calc_ask_l":     "Теперь введите длину в сантиметрах:\n\nПример: 300 (= 3 метра)",
        "calc_ask_svc":   "🧮 *Калькулятор стоимости*\n\nВыберите услугу:",
        "calc_result_below_min": "🧮 *Расчёт стоимости*\n\n📐 Размер: {w} × {l} см = {sqm} {unit}\n🧺 {svc}\n💰 {price} сум/{unit}\n\n⚠️ Ваш размер {sqm} {unit} — меньше мин. заказа ({min_order} {unit})\n💵 *Итого: {total} сум* _(за {min_order} {unit})_",
        "calc_result_no_min": "🧮 *Расчёт стоимости*\n\n📐 Размер: {w} × {l} см = {sqm} {unit}\n🧺 {svc}\n💰 {price} сум/{unit}\n\n💵 *Итого: {total} сум*",
        "branches_text":  "📍 *Наши филиалы*\n\n🏢 *Филиал Зарафшан*\nОбслуживает: Зарафшан, Учкудук, Тамдинский район\n📞 1221\n📱 +998 79 222-12-21\n📱 +998 88 200-12-21\n📱 +998 94 738-04-44\n\n🏢 *Филиал Навои*\nОбслуживает: Навои и все остальные районы области\n📞 1221\n📱 +998 79 222-12-21\n📱 +998 99 750-00-20\n📱 +998 99 112-48-48",
        "promo_text":     "🎁 *Акции и скидки*\n\n🔥 При заказе от 3 ковров — скидка до 20%\n🚚 На все заказы — бесплатная доставка и забор\n🚗 Если у вас свой автомобиль — скидка до 20% на страховой полис ОСАГО\n📢 Подписчикам нашей Telegram-группы и Instagram — скидка до 30%\n\nПодпишитесь и получите скидку 👇",
        "btn_promo_telegram": "📢 Telegram-группа",
        "btn_promo_instagram": "📸 Instagram",
        "info_text":      "ℹ️ *О компании ARTEZ*\n\nООО «ARTEZ» — профессиональная чистка ковров в Навоийской области.\n\n🏢 Два филиала: Зарафшан и Навои\n🚚 Бесплатный вывоз и доставка\n⚡ Срок чистки от 24 часов\n🛡 Бережное отношение к коврам\n\n🌐 [artez.uz](https://artez.uz)\n📢 Telegram-группа: [artez_gilam_yuvish](https://t.me/artez_gilam_yuvish)\n📸 Instagram: [@ziyoboboev](https://www.instagram.com/ziyoboboev/)\n\n☎️ Короткий номер: 1221\n📞 Оператор:\n+998 79 222 12 21\n\n*г. Зарафшан*\n📱 +998 88 200 12 21\n📱 +998 94 738 04 44\n\n*г. Навои*\n📱 +998 99 750 00 20\n📱 +998 99 112 48 48",
        "help_text":      "🆘 *Помощь*\n\n/start — Главное меню\n/order — Оставить заявку\n/calc — Калькулятор\n/prices — Цены\n/branches — Филиалы\n\nПо всем вопросам: 📞 1221",
        "status_text":    "📦 *Статус заказа*\n\nДля проверки статуса заказа позвоните нам:\n📞 1221\n📱 +998 79 222-12-21\n\nИли напишите оператору 👇",
        "status_menu_title": "📦 *Статус заказа*\n\nВыберите категорию:",
        "status_btn_new":       "🆕 Новые",
        "status_btn_progress":  "🔄 В работе",
        "status_btn_done":      "✅ Выполнено",
        "status_btn_cancelled": "❌ Отказано",
        "status_empty":   "📦 *Статус заказа*\n\nУ вас пока нет заявок.",
        "status_group_empty": "В этой категории заявок нет.",
        "status_order_line":  "📋 *{num}*\n🧺 {service}\n📅 {date}\n📍 Статус: {status}",
        "btn_back_to_status": "◀️ К категориям",
        "operator_text":  "👨‍💼 Соединяю с оператором...\n\nНапишите ваш вопрос — оператор ответит в ближайшее время.",
        "operator_msg":   "💬 *Сообщение клиенту*\n\n👤 {name}\n💬 {msg}\n🆔 Chat: {cid}",
        "cancel":         "❌ Заявка отменена. Возвращаемся в меню.",
        "btn_cancel":     "❌ Отмена",
        "ask_order_type": "📋 Выберите тип заявки:",
        "btn_order_quick":"⚡ Быстрая заявка",
        "btn_order_full": "📋 Подробная заявка",
        "quick_ask_name": "⚡ *Быстрая заявка*\n\nШаг 1 из 3\n👤 Введите ваше имя:",
        "quick_ask_phone":"Шаг 2 из 3\n📞 Поделитесь номером или введите вручную:\n\nФормат: +998XXXXXXXXX",
        "quick_ask_branch":"Шаг 3 из 3\n🏢 Выберите филиал:",
        "quick_done":     "✅ *Заявка принята!*\n\nМы свяжемся с вами в ближайшее время.\n\n☎️ Короткий номер: *1221*\n📞 +998 79 222-12-21",
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
        "menu_title":     "🏠 Asosiy menyu\n\nARTEZ MChJ — professional gilam tozalash\n📍 Zarafshon va Navoiy\n🌐 [artez.uz](https://artez.uz)\n\n☎️ Qisqa raqam: 1221\n📞 Operator:\n+998 79 222 12 21\n\n*Zarafshon shahri*\n📱 +998 88 200 12 21\n📱 +998 94 738 04 44\n\n*Navoiy shahri*\n📱 +998 99 750 00 20\n📱 +998 99 112 48 48",
        "btn_webapp":     "🌐 Ilovani ochish",
        "btn_order":      "📋 Ariza qoldirish",
        "btn_calc":       "🧮 Kalkulyator",
        "btn_prices":     "💰 Narxlar",
        "btn_branches":   "📍 Filiallar",
        "btn_promo":      "🎁 Aksiyalar",
        "btn_status":     "📦 Buyurtma holati",
        "btn_operator":   "👨‍💼 Operator",
        "btn_info":       "ℹ️ Kompaniya haqida",
        "btn_profile":    "👤 Mening profilim",
        "profile_text":   "👤 *Profilingiz*\n\n📛 Ism: {name}\n📞 Telefon: {phone}\n🆔 ID: {uid}\n\n📊 Jami buyurtmalar: *{total}*\n✅ Bajarildi: *{done}*\n{last}",
        "profile_last":   "📅 Oxirgi buyurtma: {date}\n",
        "profile_nophone":"Ko'rsatilmagan",
        "profile_link_phone": "📞 Raqam ulash",
        "btn_use_saved_phone": "✅ {phone} dan foydalanish",
        "btn_enter_other_phone": "⌨️ Boshqa raqam kiritish",
        "ask_phone_saved":"2-qadam (7 dan)\n📞 Saqlangan raqamdan foydalanasizmi?",
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
        "link_phone_prompt": (
            "🔗 *Sayt raqamini bog'lash*\n\n"
            "Quyidagi tugmani bosing va raqamingizni ulashing.\n"
            "Keyin *artez.uz* saytida ro'yxatdan o'tishda kodni SMS o'rniga Telegram orqali olishingiz mumkin."
        ),
        "link_phone_ok": (
            "✅ *Raqam bog'landi!*\n\n"
            "📱 {phone}\n\n"
            "*artez.uz* saytiga o'ting, «Ro'yxatdan o'tish» ni tanlang va «Telegram orqali kod olish» tugmasini bosing."
        ),
        "link_phone_ok_registered": (
            "✅ *Raqam bog'landi!*\n\n"
            "📱 {phone}\n\n"
            "Siz allaqachon saytda ro'yxatdan o'tgansiz — *artez.uz* ga kiring."
        ),
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
        "order_done":     "✅ *Ariza qabul qilindi!*\n\n30 daqiqa ichida qayta qo'ng'iroq qilamiz.\n\nAriza raqami: *#{num}*\n\n☎️ Qisqa raqam: *1221*\n📞 +998 79 222-12-21\n\n*Zarafshon:*\n+998 88 200-12-21\n+998 94 738-04-44\n\n*Navoiy:*\n+998 99 750-00-20\n+998 99 112-48-48",
        "order_rejected": "❌ Afsuski, *{num}* arizasi bajarilishi mumkin emas.\n\nBizga qo'ng'iroq qiling:\n☎️ 1221\n📞 +998 79 222-12-21",
        "order_summary":  "📋 *Yangi ariza #{num}* (bot)\n━━━━━━━━━━━━━━━\n👤 {name}\n📞 {phone}\n🏢 {branch}\n📍 {city}\n🏠 {address}\n🗺 {location}\n🧺 {service}\n📅 {date}\n🕐 {time}\n━━━━━━━━━━━━━━━\n🕒 {dt}",
        "prices_text":    "💰 *ARTEZ narx-navo*\n\n🧺 Standart tozalash — 12 000 so'm/m²\n✨ Chuqur kimyoviy — 16 000 so'm/m²\n🛋 Maishiy texnika/Ponka — 16 000 so'mdan/dona\n🌿 Quruq tozalash — 14 000 so'm/m²\n\n📦 Minimal buyurtma — 10 m²\n🚚 Olib ketish va yetkazish — *bepul*",
        "calc_selected_header": "🧮 *Narx kalkulyatori*\n\n🧺 Xizmat: {svc}",
        "calc_ask_w":     "Enini santimetrda kiriting:\n\nMisol: 200 (= 2 metr)",
        "calc_ask_l":     "Endi bo'yini santimetrda kiriting:\n\nMisol: 300 (= 3 metr)",
        "calc_ask_svc":   "🧮 *Narx kalkulyatori*\n\nXizmatni tanlang:",
        "calc_result_below_min": "🧮 *Narx hisobi*\n\n📐 O'lcham: {w} × {l} sm = {sqm} {unit}\n🧺 {svc}\n💰 {price} so'm/{unit}\n\n⚠️ Sizning o'lchamingiz {sqm} {unit} — minimal buyurtmadan kam ({min_order} {unit})\n💵 *Jami: {total} so'm* _({min_order} {unit} uchun)_",
        "calc_result_no_min": "🧮 *Narx hisobi*\n\n📐 O'lcham: {w} × {l} sm = {sqm} {unit}\n🧺 {svc}\n💰 {price} so'm/{unit}\n\n💵 *Jami: {total} so'm*",
        "branches_text":  "📍 *Filiallarimiz*\n\n🏢 *Zarafshon filiali*\nXizmat ko'rsatadi: Zarafshon, Uchquduq, Tomdi tumani\n📞 1221\n📱 +998 79 222-12-21\n📱 +998 88 200-12-21\n📱 +998 94 738-04-44\n\n🏢 *Navoiy filiali*\nXizmat ko'rsatadi: Navoiy va viloyatning boshqa tumanlari\n📞 1221\n📱 +998 79 222-12-21\n📱 +998 99 750-00-20\n📱 +998 99 112-48-48",
        "promo_text":     "🎁 *Aksiyalar va chegirmalar*\n\n🔥 3 ta va undan ko'p gilam buyurtma qilsangiz — 20% gacha chegirma\n🚚 Barcha buyurtmalar uchun — bepul olib ketish va yetkazish\n🚗 Agar shaxsiy avtomobilingiz bo'lsa — OSAGO sug'urta polisiga 20% gacha chegirma\n📢 Telegram-guruhimiz va Instagram'ga obuna bo'lganlar uchun — 30% gacha chegirma\n\nObuna bo'ling va chegirma oling 👇",
        "btn_promo_telegram": "📢 Telegram-guruh",
        "btn_promo_instagram": "📸 Instagram",
        "info_text":      "ℹ️ *ARTEZ haqida*\n\nARTEZ MChJ — Navoiy viloyatida professional gilam tozalash.\n\n🏢 Ikki filial: Zarafshon va Navoiy\n🚚 Bepul olib ketish va yetkazish\n⚡ Tozalash muddati 24 soatdan\n🛡 Gilamlarga ehtiyotkorona munosabat\n\n🌐 [artez.uz](https://artez.uz)\n📢 Telegram-guruh: [artez_gilam_yuvish](https://t.me/artez_gilam_yuvish)\n📸 Instagram: [@ziyoboboev](https://www.instagram.com/ziyoboboev/)\n\n☎️ Qisqa raqam: 1221\n📞 Operator:\n+998 79 222 12 21\n\n*Zarafshon shahri*\n📱 +998 88 200 12 21\n📱 +998 94 738 04 44\n\n*Navoiy shahri*\n📱 +998 99 750 00 20\n📱 +998 99 112 48 48",
        "help_text":      "🆘 *Yordam*\n\n/start — Asosiy menyu\n/order — Ariza qoldirish\n/calc — Kalkulyator\n/prices — Narxlar\n/branches — Filiallar\n\nBarcha savollar uchun: 📞 1221",
        "status_text":    "📦 *Buyurtma holati*\n\nBuyurtma holatini tekshirish uchun qo'ng'iroq qiling:\n📞 1221\n📱 +998 79 222-12-21\n\nYoki operatorga yozing 👇",
        "status_menu_title": "📦 *Buyurtma holati*\n\nKategoriyani tanlang:",
        "status_btn_new":       "🆕 Yangi",
        "status_btn_progress":  "🔄 Bajarilmoqda",
        "status_btn_done":      "✅ Bajarildi",
        "status_btn_cancelled": "❌ Bekor qilindi",
        "status_empty":   "📦 *Buyurtma holati*\n\nSizda hali buyurtmalar yo'q.",
        "status_group_empty": "Bu kategoriyada buyurtmalar yo'q.",
        "status_order_line":  "📋 *{num}*\n🧺 {service}\n📅 {date}\n📍 Holat: {status}",
        "btn_back_to_status": "◀️ Kategoriyalarga",
        "operator_text":  "👨‍💼 Operator bilan bog'lanmoqda...\n\nSavolingizni yozing — operator tez orada javob beradi.",
        "operator_msg":   "💬 *Mijozdan xabar*\n\n👤 {name}\n💬 {msg}\n🆔 Chat: {cid}",
        "cancel":         "❌ Ariza bekor qilindi. Menyuga qaytamiz.",
        "btn_cancel":     "❌ Bekor qilish",
        "ask_order_type": "📋 Ariza turini tanlang:",
        "btn_order_quick":"⚡ Tezkor ariza",
        "btn_order_full": "📋 Batafsil ariza",
        "quick_ask_name": "⚡ *Tezkor ariza*\n\n1-qadam (3 dan)\n👤 Ismingizni kiriting:",
        "quick_ask_phone":"2-qadam (3 dan)\n📞 Raqamingizni ulashing yoki qo'lda kiriting:\n\nFormat: +998XXXXXXXXX",
        "quick_ask_branch":"3-qadam (3 dan)\n🏢 Filialni tanlang:",
        "quick_done":     "✅ *Ariza qabul qilindi!*\n\nTez orada siz bilan bog'lanamiz.\n\n☎️ Qisqa raqam: *1221*\n📞 +998 79 222-12-21",
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

# Кэш цен из БД: {service_key: {type_key: {"price":.., "unit":.., "unit_key":.., "min_order":..}}}
PRICE_CACHE = {}
# Кэш единиц измерения: {key: {"name_ru":.., "name_uz":.., "symbol_ru":.., "symbol_uz":..}}
UNIT_CACHE = {}

# Дефолты на случай, если БД недоступна или таблица prices пуста
DEFAULT_PRICES = {
    "carpet":      {"standard": {"price": 12000, "unit": "sum/m2", "unit_key": "m2", "min_order": 10.0}, "express": {"price": 16000, "unit": "sum/m2", "unit_key": "m2", "min_order": 10.0}},
    "carpet_home": {"standard": {"price": 14000, "unit": "sum/m2", "unit_key": "m2", "min_order": 10.0}, "express": {"price": 18000, "unit": "sum/m2", "unit_key": "m2", "min_order": 10.0}},
    "sofa":        {"standard": {"price": 16000, "unit": "sum/m2", "unit_key": "m2", "min_order": None}, "express": {"price": 20000, "unit": "sum/m2", "unit_key": "m2", "min_order": None}},
    "mattress":    {"standard": {"price": 16000, "unit": "sum/m2", "unit_key": "m2", "min_order": None}, "express": {"price": 20000, "unit": "sum/m2", "unit_key": "m2", "min_order": None}},
    "curtains":    {"standard": {"price": 14000, "unit": "sum/m2", "unit_key": "m2", "min_order": None}, "express": {"price": 18000, "unit": "sum/m2", "unit_key": "m2", "min_order": None}},
}

DEFAULT_UNITS = {
    "m2":  {"name_ru": "Квадратный метр", "name_uz": "Kvadrat metr", "symbol_ru": "м²", "symbol_uz": "m²"},
    "m":   {"name_ru": "Метр",            "name_uz": "Metr",         "symbol_ru": "м",  "symbol_uz": "m"},
    "pcs": {"name_ru": "Штука",           "name_uz": "Dona",         "symbol_ru": "шт", "symbol_uz": "dona"},
    "cm":  {"name_ru": "Сантиметр",       "name_uz": "Santimetr",    "symbol_ru": "см", "symbol_uz": "sm"},
    "cm2": {"name_ru": "Кв. сантиметр",   "name_uz": "Kv. santimetr","symbol_ru": "см²","symbol_uz": "sm²"},
    "kg":  {"name_ru": "Килограмм",       "name_uz": "Kilogramm",    "symbol_ru": "кг", "symbol_uz": "kg"},
}

import time as _time
_PRICE_CACHE_TS = 0.0
_UNIT_CACHE_TS  = 0.0
PRICE_TTL = 60  # секунд — обновляем кэш цен каждую минуту

async def load_prices():
    """Загружает цены из БД в PRICE_CACHE. При ошибке/пустой БД использует дефолты."""
    global PRICE_CACHE, _PRICE_CACHE_TS
    try:
        data = await get_all_prices()
    except Exception as e:
        logging.warning(f"load_prices error: {e}")
        data = {}
    if not data:
        data = DEFAULT_PRICES
    PRICE_CACHE = data
    _PRICE_CACHE_TS = _time.monotonic()

async def load_units():
    """Загружает единицы измерения из БД в UNIT_CACHE."""
    global UNIT_CACHE, _UNIT_CACHE_TS
    try:
        rows = await get_all_units()
        data = {r["key"]: {
            "name_ru": r["name_ru"], "name_uz": r["name_uz"],
            "symbol_ru": r["symbol_ru"], "symbol_uz": r["symbol_uz"],
        } for r in rows}
    except Exception as e:
        logging.warning(f"load_units error: {e}")
        data = {}
    if not data:
        data = DEFAULT_UNITS
    UNIT_CACHE = data
    _UNIT_CACHE_TS = _time.monotonic()

async def ensure_prices_fresh():
    """Перезагружает кэш если прошло больше PRICE_TTL секунд."""
    if _time.monotonic() - _PRICE_CACHE_TS > PRICE_TTL:
        await load_prices()
    if _time.monotonic() - _UNIT_CACHE_TS > PRICE_TTL:
        await load_units()

def get_unit_symbol(unit_key, uid=None):
    is_uz = uid is not None and lang(uid) == "uz"
    entry = UNIT_CACHE.get(unit_key) or DEFAULT_UNITS.get(unit_key, DEFAULT_UNITS["m2"])
    return entry["symbol_uz"] if is_uz else entry["symbol_ru"]

def get_cached_price(service_key: str, type_key: str):
    entry = PRICE_CACHE.get(service_key, {}).get(type_key)
    if entry:
        return entry["price"]
    fallback = DEFAULT_PRICES.get(service_key, {}).get(type_key)
    return fallback["price"] if fallback else 12000

def get_cached_min_order(service_key: str, type_key: str):
    entry = PRICE_CACHE.get(service_key, {}).get(type_key)
    if entry and "min_order" in entry:
        return entry["min_order"]
    fallback = DEFAULT_PRICES.get(service_key, {}).get(type_key)
    return fallback["min_order"] if fallback else None

def get_cached_unit_key(service_key: str, type_key: str):
    entry = PRICE_CACHE.get(service_key, {}).get(type_key)
    if entry and entry.get("unit_key"):
        return entry["unit_key"]
    fallback = DEFAULT_PRICES.get(service_key, {}).get(type_key)
    return fallback["unit_key"] if fallback else "m2"


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
    "new":       "🆕 Новый",
    "confirmed": "✅ Подтверждён",
    "pickup":    "🚗 Вывоз",
    "received":  "📥 В мастерской",
    "washing":   "🧼 Мойка",
    "drying":    "💨 Сушка",
    "packing":   "📦 Упаковка",
    "ready":     "✅ Готов",
    "delivery":  "🚚 Доставка",
    "delivered": "✅ Доставлен",
    "cancelled": "❌ Отменён",
}
ORDER_STATUS_NAMES_UZ = {
    "new":       "🆕 Yangi",
    "confirmed": "✅ Tasdiqlangan",
    "pickup":    "🚗 Olib ketish",
    "received":  "📥 Ustaxonada",
    "washing":   "🧼 Yuvish",
    "drying":    "💨 Quritish",
    "packing":   "📦 Qadoqlash",
    "ready":     "✅ Tayyor",
    "delivery":  "🚚 Yetkazish",
    "delivered": "✅ Yetkazildi",
    "cancelled": "❌ Bekor qilindi",
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
    title = "💰 ARTEZ narx-navo" if is_uz else "💰 Прайс-лист ARTEZ"
    currency = "so'm" if is_uz else "сум"
    lines = [title, ""]
    min_groups: dict = {}  # {(min_val, unit_sym): [svc_name,...]}

    for svc in SERVICE_KEYS:
        svc_name = names.get(svc, svc)
        prices = PRICE_CACHE.get(svc, DEFAULT_PRICES.get(svc, {}))
        std = prices.get("standard")
        exp = prices.get("express")
        if not std and not exp:
            continue
        entry = std or exp
        unit_sym = get_unit_symbol(entry.get("unit_key", "m2"), uid)
        price_parts = []
        if std:
            price_parts.append(f"{std['price']:,}".replace(",", " "))
        if exp:
            price_parts.append(f"{exp['price']:,}".replace(",", " "))
        lines.append(f"🔹 {svc_name} ")
        lines.append(f"— {' / '.join(price_parts)} {currency}/{unit_sym}")
        if std and std.get("min_order"):
            key = (std["min_order"], unit_sym)
            min_groups.setdefault(key, []).append(svc_name)

    lines.append("")
    if min_groups:
        if is_uz:
            lines.append("📦 Min buyurtma: ")
            for (mo, unit_sym), svc_names in min_groups.items():
                mo_str = int(mo) if mo == int(mo) else mo
                lines.append(f"{mo_str} {unit_sym} ({', '.join(svc_names)}) ")
            lines.append("Standart / Ekspress")
            lines.append("🚚 Olib ketish va yetkazish — bepul")
        else:
            lines.append("📦 Мин. заказ: ")
            for (mo, unit_sym), svc_names in min_groups.items():
                mo_str = int(mo) if mo == int(mo) else mo
                lines.append(f"{mo_str} {unit_sym} ({', '.join(svc_names)}) ")
            lines.append("Стандарт / Экспресс")
            lines.append("🚚 Вывоз и доставка — бесплатно")
    else:
        if is_uz:
            lines.append("Standart / Ekspress")
            lines.append("🚚 Olib ketish va yetkazish — bepul")
        else:
            lines.append("Стандарт / Экспресс")
            lines.append("🚚 Вывоз и доставка — бесплатно")
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

class QuickForm(StatesGroup):
    name   = State()
    phone  = State()
    branch = State()

class CalcForm(StatesGroup):
    width   = State()
    length  = State()
    service = State()
    service_type = State()

class OperatorForm(StatesGroup):
    message = State()

class AdminReply(StatesGroup):
    waiting_reply = State()   # оператор пишет ответ клиенту

class AgentForm(StatesGroup):
    waiting_contact = State()  # ожидаем контакт для регистрации агента

class LinkPhoneForm(StatesGroup):
    waiting_contact = State()  # ожидаем контакт для привязки к сайту

# ══════════════════════════════════════
#  КЛАВИАТУРЫ
# ══════════════════════════════════════
def lang_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇷🇺 Русский язык", callback_data="lang_ru"),
        InlineKeyboardButton(text="🇺🇿 O'zbek tili",  callback_data="lang_uz"),
    ]])

def menu_kb(uid):
    rows = [
        [InlineKeyboardButton(text=t(uid,"btn_webapp"), web_app=WebAppInfo(url=WEBSITE_URL))],
        [InlineKeyboardButton(text=t(uid,"btn_order"),    callback_data="menu_order"),
         InlineKeyboardButton(text=t(uid,"btn_status"),   callback_data="menu_status")],
        [InlineKeyboardButton(text=t(uid,"btn_prices"),   callback_data="menu_prices"),
         InlineKeyboardButton(text=t(uid,"btn_calc"),     callback_data="menu_calc")],
        [InlineKeyboardButton(text=t(uid,"btn_profile"),  callback_data="menu_profile"),
         InlineKeyboardButton(text=t(uid,"btn_operator"), callback_data="menu_operator")],
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

LOCATION_PICKER_URL = "https://artez.uz/location_picker.html"

def location_kb(uid):
    """ReplyKeyboard: GPS / выбрать на карте / пропустить"""
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text=t(uid,"btn_send_loc"), request_location=True),
            KeyboardButton(text="🗺 Выбрать на карте", web_app=WebAppInfo(url=LOCATION_PICKER_URL)),
        ],[
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

def _group_id_for_branch(branch: str) -> int:
    """Возвращает chat_id группы по филиалу. Fallback — общий GROUP_ID."""
    if branch == "zarafshan" and GROUP_ID_ZARAFSHAN:
        return GROUP_ID_ZARAFSHAN
    if branch == "navoi" and GROUP_ID_NAVOI:
        return GROUP_ID_NAVOI
    return GROUP_ID

async def _notify_new_bot_client(uid: int, first_name: str, last_name: str, phone: str, username: str):
    """Уведомление о новом клиенте из бота в группу новых клиентов."""
    if not GROUP_NEW_CLIENTS_ID:
        return
    from datetime import datetime
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    name = f"{first_name or ''} {last_name or ''}".strip() or "—"
    tg_link = f'<a href="tg://user?id={uid}">{uid}</a>'
    text = (
        f"👤 {name}, 📞 <code>{phone}</code>, ✈️ {tg_link}, 🤖\n"
        f"📅 {now}"
    )
    try:
        await bot.send_message(GROUP_NEW_CLIENTS_ID, text, parse_mode="HTML")
    except Exception as e:
        logging.warning(f"_notify_new_bot_client error: {e}")


async def notify_group(text: str, order_num: int = None, client_id: int = None, phone: str = None, username: str = None, location_url: str = None, branch: str = ""):
    """Отправляет заявку в группу сотрудников с кнопками действий"""
    kb_rows = []
    if location_url:
        kb_rows.append([InlineKeyboardButton(text="🗺 Открыть на карте", url=location_url)])
    if order_num and client_id:
        if username:
            msg_button = InlineKeyboardButton(text="✉️ Написать", url=f"https://t.me/{username}")
        else:
            msg_button = InlineKeyboardButton(text="✉️ Написать", url=f"tg://user?id={client_id}")
        kb_rows.extend([
            [
                InlineKeyboardButton(text="✅ Принять заказ",  callback_data=f"accept_{order_num}_{client_id}"),
                msg_button,
            ],
            [
                InlineKeyboardButton(text="🚗 Назначить водителя", callback_data=f"driver_{order_num}_{client_id}"),
                InlineKeyboardButton(text="❌ Отклонить",          callback_data=f"reject_{order_num}_{client_id}"),
            ],
        ])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None
    target_group = _group_id_for_branch(branch)
    try:
        await bot.send_message(target_group, text, reply_markup=kb)
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

    # Проверка блокировки
    try:
        if await is_client_blocked(uid):
            await msg.answer("🚫 Ваш аккаунт заблокирован. Обратитесь в поддержку.")
            return
    except Exception:
        pass

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

    # Deep link: /start tglink_{user_id} — привязка аккаунта сайта
    args = msg.text.split(maxsplit=1)[1] if msg.text and " " in msg.text else ""
    if args.startswith("tglink_"):
        try:
            site_user_id = int(args.split("_", 1)[1])
            async with aiohttp.ClientSession() as s:
                r = await s.post(f"{API_URL}/user/link-tg",
                                 json={"user_id": site_user_id, "tg_id": uid,
                                       "tg_username": msg.from_user.username},
                                 timeout=aiohttp.ClientTimeout(total=8))
                data = await r.json()
            if data.get("ok"):
                name = data.get("name") or "друг"
                await msg.answer(
                    f"✅ Telegram успешно привязан к вашему аккаунту на сайте!\n\n"
                    f"Теперь вернитесь на сайт artez.uz и нажмите *Стать Агентом*.",
                    parse_mode="Markdown")
            else:
                await msg.answer("❌ Не удалось привязать аккаунт. Попробуйте ещё раз.")
        except Exception as e:
            logging.warning(f"tglink error: {e}")
            await msg.answer("❌ Ошибка привязки. Обратитесь к администратору.")
        return

    # Deep link: /start link_phone — привязка телефона к сайту для регистрации
    if args == "link_phone":
        # Проверяем — вдруг пользователь уже делился номером раньше
        saved_phone = await get_client_tg_phone(uid)
        if saved_phone:
            # Есть сохранённый номер — сразу привязываем без повторного шаринга
            registered = False
            try:
                async with aiohttp.ClientSession() as s:
                    r = await s.post(f"{API_URL}/tg-phone-link",
                                     json={"phone": saved_phone, "tg_id": uid},
                                     timeout=aiohttp.ClientTimeout(total=8))
                    data = await r.json()
                    registered = data.get("registered", False)
            except Exception as e:
                logging.warning(f"tg-phone-link (saved) error: {e}")
            key = "link_phone_ok_registered" if registered else "link_phone_ok"
            await msg.answer(
                t(uid, key).format(phone=saved_phone),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🌐 artez.uz", url="https://artez.uz")],
                    [InlineKeyboardButton(text=t(uid,"btn_menu"), callback_data="go_menu")],
                ]),
                parse_mode="Markdown"
            )
            return
        # Номера нет — просим поделиться
        share_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=t(uid,"btn_share_phone"), request_contact=True)]],
            resize_keyboard=True, one_time_keyboard=True
        )
        await state.set_state(LinkPhoneForm.waiting_contact)
        await msg.answer(t(uid,"link_phone_prompt"), reply_markup=share_kb, parse_mode="Markdown")
        return

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
    await ensure_prices_fresh()
    await cb.message.answer(build_prices_text(uid), reply_markup=back_kb(uid), parse_mode="Markdown")

@dp.callback_query(F.data == "menu_branches")
async def menu_branches(cb: CallbackQuery):
    uid = cb.from_user.id
    await cb.message.answer(t(uid,"branches_text"), reply_markup=back_kb(uid), parse_mode="Markdown")

def promo_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid,"btn_promo_telegram"),  url=SITE["social_tg_group"])],
        [InlineKeyboardButton(text=t(uid,"btn_promo_instagram"), url=SITE["social_instagram"])],
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

# ── АГЕНТ ─────────────────────────────────────────────────────────────
async def _do_agent_check(uid: int, phone: str | None, answer_fn):
    """Общая логика проверки/регистрации агента. answer_fn(text, kb, parse_mode)."""
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(f"{API_URL}/agent/status-by-tg/{uid}",
                            params={"phone": phone} if phone else {},
                            timeout=aiohttp.ClientTimeout(total=6))
            data = await r.json()
    except Exception:
        data = {}

    if data.get("is_agent"):
        await answer_fn(
            "✅ *Вы уже являетесь Агентом ARTEZ\\!*\n\n"
            "Войдите в кабинет агента:\n🔗 artez\\.uz/staff\\.html\n\n"
            "Логин: ваш номер телефона\n_Забыли пароль? Нажмите кнопку ниже_",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎯 Открыть кабинет агента", url="https://artez.uz/staff.html")],
                [InlineKeyboardButton(text="🔑 Сбросить пароль", callback_data="agent_reset_pass")],
                [InlineKeyboardButton(text="← Назад", callback_data="go_menu")],
            ]), "MarkdownV2")
        return

    if data.get("has_site_account"):
        # Регистрируем
        try:
            async with aiohttp.ClientSession() as s:
                r = await s.post(f"{API_URL}/agent/apply-by-tg",
                                 json={"tg_id": uid, "phone": phone},
                                 timeout=aiohttp.ClientTimeout(total=8))
                result = await r.json()
        except Exception:
            result = {}

        if result.get("ok"):
            p = result.get("phone", "")
            already = result.get("already", False)
            txt = (f"✅ *Вы уже являетесь Агентом ARTEZ\\!*\n\nЛогин: `{p}`\nПароль: как на сайте artez\\.uz\n\n🔗 artez\\.uz/staff\\.html"
                   if already else
                   f"🎉 *Ура\\! Вы стали Агентом ARTEZ\\!*\n\nЛогин: `{p}`\nПароль: как на сайте artez\\.uz\n\nВойдите в кабинет:\n🔗 artez\\.uz/staff\\.html")
            await answer_fn(txt, InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎯 Открыть кабинет агента", url="https://artez.uz/staff.html")],
                [InlineKeyboardButton(text="← Назад", callback_data="go_menu")],
            ]), "MarkdownV2")
        else:
            await answer_fn("❌ Не удалось зарегистрировать\\. Попробуйте через сайт artez\\.uz",
                            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="← Назад", callback_data="go_menu")]]),
                            "MarkdownV2")
        return

    # Аккаунт на сайте не найден — просим поделиться НАСТОЯЩИМ номером
    await answer_fn(
        "🤝 Стать Агентом ARTEZ\n\n"
        "Аккаунт на сайте не найден.\n\n"
        "Нажмите кнопку ниже — бот получит ваш реальный номер Telegram и найдёт ваш аккаунт на artez.uz",
        ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="📱 Поделиться номером", request_contact=True)],
        ], resize_keyboard=True, one_time_keyboard=True),
        None)

@dp.callback_query(F.data == "menu_agent")
async def menu_agent(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    await cb.answer()
    lang_u = user_lang.get(uid, "ru")
    if lang_u == "uz":
        info_text = (
            "🤝 *ARTEZ Agenti bo'lish*\n\n"
            "Agentlar mijozlarni jalb qilish orqali har bir buyurtmadan *komissiya* oladi\\.\n\n"
            "📋 *Shartlar:*\n"
            "• artez\\.uz saytida ro'yxatdan o'tgan bo'lish\n"
            "• Referral havola orqali mijoz topib kelish\n"
            "• Komissiya miqdori: buyurtma summasiga qarab\n\n"
            "🔒 *Maxfiylik siyosati:* artez\\.uz/privacy\n\n"
            "Davom etish uchun tasdiqlang:"
        )
        btn_confirm = "✅ Tasdiqlash — Agent bo'lish"
        btn_cancel  = "❌ Bekor qilish"
    else:
        info_text = (
            "🤝 *Стать Агентом ARTEZ*\n\n"
            "Агенты привлекают клиентов и получают *комиссию* с каждого заказа\\.\n\n"
            "📋 *Условия:*\n"
            "• Быть зарегистрированным на artez\\.uz\n"
            "• Приводить клиентов по реферальной ссылке\n"
            "• Размер комиссии: зависит от суммы заказа\n\n"
            "🔒 *Политика конфиденциальности:* artez\\.uz/privacy\n\n"
            "Нажмите «Подтвердить» чтобы продолжить:"
        )
        btn_confirm = "✅ Подтвердить — Стать Агентом"
        btn_cancel  = "❌ Отмена"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_confirm, callback_data="agent_confirm")],
        [InlineKeyboardButton(text=btn_cancel,  callback_data="go_menu")],
    ])
    await cb.message.answer(info_text, reply_markup=kb, parse_mode="MarkdownV2")

@dp.callback_query(F.data == "agent_confirm")
async def agent_confirm(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    await cb.answer()
    await cb.message.answer("⏳ Проверяем…" if user_lang.get(uid,"ru") == "ru" else "⏳ Tekshirilmoqda…")

    bot_client = await get_client_by_tg_id(uid)
    bot_phone = (bot_client.get("tg_phone") or bot_client.get("phone")) if bot_client else None

    async def reply(text, kb, pm):
        if pm:
            await cb.message.answer(text, reply_markup=kb, parse_mode=pm)
        else:
            await cb.message.answer(text, reply_markup=kb)
            await state.set_state(AgentForm.waiting_contact)

    await _do_agent_check(uid, bot_phone, reply)

@dp.message(AgentForm.waiting_contact, F.contact)
async def agent_contact_received(msg: Message, state: FSMContext):
    """Пользователь поделился контактом — сохраняем как tg_phone и ищем аккаунт."""
    await state.clear()
    await msg.answer("⏳ Проверяем…", reply_markup=ReplyKeyboardRemove())
    uid = msg.from_user.id
    phone = msg.contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone
    # Сохраняем в clients: phone (для заявок) и tg_phone (верифицированный)
    await upsert_client(tg_id=uid, username=msg.from_user.username,
                        first_name=msg.from_user.first_name,
                        last_name=msg.from_user.last_name,
                        phone=phone, lang=user_lang.get(uid, "ru"))
    await update_client_tg_phone(uid, phone)

    kb_back = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад", callback_data="go_menu")]
    ])

    async def reply(text, kb, pm):
        # После получения контакта — не показываем кнопку контакта снова
        if pm:
            await msg.answer(text, reply_markup=kb, parse_mode=pm)
        else:
            # "не найден" — показываем сообщение со ссылкой на сайт
            await msg.answer(
                f"❌ Номер `{phone}` не найден на сайте artez\\.uz\n\n"
                "Зарегистрируйтесь на сайте с этим номером, затем снова нажмите «Стать Агентом»",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🌐 Зарегистрироваться", url="https://artez.uz")],
                    [InlineKeyboardButton(text="← Назад", callback_data="go_menu")],
                ]), parse_mode="MarkdownV2")

    await _do_agent_check(uid, phone, reply)

@dp.message(LinkPhoneForm.waiting_contact, F.contact)
async def link_phone_contact_received(msg: Message, state: FSMContext):
    """Пользователь поделился номером для привязки к сайту."""
    await state.clear()
    uid = msg.from_user.id
    phone = msg.contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone

    # Принимаем только собственный контакт
    if msg.contact.user_id and int(msg.contact.user_id) != uid:
        await msg.answer("❌ " + ("Поделитесь своим номером." if user_lang.get(uid,"ru") == "ru" else "O'z raqamingizni ulashing."),
                         reply_markup=ReplyKeyboardRemove())
        return

    await msg.answer("⏳", reply_markup=ReplyKeyboardRemove())

    # Сохраняем номер в профиль клиента (чтобы отображался в «Мой профиль»)
    await upsert_client(tg_id=uid, username=msg.from_user.username,
                        first_name=msg.from_user.first_name,
                        last_name=msg.from_user.last_name,
                        phone=phone, lang=user_lang.get(uid, "ru"))
    await update_client_tg_phone(uid, phone)

    registered = False
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(f"{API_URL}/tg-phone-link",
                             json={"phone": phone, "tg_id": uid},
                             timeout=aiohttp.ClientTimeout(total=8))
            data = await r.json()
            registered = data.get("registered", False)
    except Exception as e:
        logging.warning(f"tg-phone-link error: {e}")

    key = "link_phone_ok_registered" if registered else "link_phone_ok"
    await msg.answer(
        t(uid, key).format(phone=phone),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌐 artez.uz", url="https://artez.uz")],
            [InlineKeyboardButton(text=t(uid,"btn_menu"), callback_data="go_menu")],
        ]),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("take_lead_"))
async def cb_take_lead(cb: CallbackQuery):
    """Сотрудник нажал 'Взять лид' в групповом чате."""
    try:
        tg_user_id = cb.from_user.id
        cq_data    = cb.data
        orig_text  = cb.message.text or ""

        try:
            lead_id = int(cq_data.split("_")[2])
        except (IndexError, ValueError):
            await cb.answer("❌ Неверный формат данных", show_alert=True)
            return

        staff = await get_staff_by_tg_id_for_lead(tg_user_id)
        if not staff:
            await cb.answer(
                "❌ Ваш Telegram не привязан к аккаунту сотрудника ARTEZ.\nОбратитесь к администратору.",
                show_alert=True)
            return
        if staff.get("role") == "agent":
            await cb.answer("❌ Агенты не могут брать лиды через Telegram.\nЛиды берут только сотрудники.", show_alert=True)
            return

        staff_id   = staff["id"]
        staff_name = f"{staff.get('first_name') or ''} {staff.get('last_name') or ''}".strip() or staff.get("login", "")
        took_verb  = "Взяла" if staff.get("gender") == "F" else "Взял"

        result, taker_name, taker_verb = await take_lead(lead_id, staff_id, staff_name)

        if result == 'not_found':
            await cb.answer("❌ Лид не найден", show_alert=True)
        elif result == 'already_mine':
            await cb.answer("✅ Этот лид уже ваш!")
        elif result == 'taken':
            await cb.answer(f"❌ Лид уже взят: {taker_name or 'другой сотрудник'}", show_alert=True)
            new_text = orig_text.rstrip("━" * 10).rstrip() + f"\n{'━'*10}\n✅ {taker_verb}: {taker_name or 'другой сотрудник'}"
            try:
                await cb.message.edit_text(new_text)
            except Exception:
                pass
        elif result == 'ok':
            await cb.answer("✅ Лид взят! Откройте приложение.")
            new_text = orig_text.rstrip("━" * 10).rstrip() + f"\n{'━'*10}\n✅ {took_verb}: {staff_name}"
            try:
                await cb.message.edit_text(new_text)
            except Exception:
                pass
        else:
            await cb.answer("❌ Ошибка базы данных", show_alert=True)
    except Exception as e:
        logging.warning(f"cb_take_lead error: {e}")
        try:
            await cb.answer("❌ Ошибка сервера. Попробуйте ещё раз.", show_alert=True)
        except Exception:
            pass


@dp.callback_query(F.data == "agent_reset_pass")
async def agent_reset_pass(cb: CallbackQuery):
    uid = cb.from_user.id
    API = os.getenv("WEBSITE_API", "https://artez-api.railway.app/api")
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.post(f"{API}/agent/reset-password-by-tg",
                             json={"tg_id": uid},
                             timeout=aiohttp.ClientTimeout(total=8))
            data = await r.json()
        if data.get("ok"):
            await cb.message.answer("🔑 Временный пароль отправлен выше.\n⏰ Действует 10 минут.\nПосле входа сразу смените пароль.")
        else:
            await cb.message.answer("❌ Ошибка: " + data.get("detail",""))
    except Exception as e:
        await cb.message.answer(f"❌ Ошибка соединения: {e}")
    await cb.answer()

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
        kb_empty = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(uid,"btn_order"), callback_data="menu_order")],
            [InlineKeyboardButton(text=t(uid,"btn_menu"),  callback_data="go_menu")],
        ])
        await cb.message.answer(t(uid,"status_empty"), reply_markup=kb_empty, parse_mode="Markdown")
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
@dp.callback_query(F.data == "menu_profile")
async def menu_profile(cb: CallbackQuery):
    uid = cb.from_user.id
    try:
        client = await get_client_by_tg_id(uid)
        orders = await get_client_orders(uid)
        total  = len(orders)
        done   = sum(1 for o in orders if o.get("status") in ("done","completed"))
        last_d = ""
        if orders:
            ts = orders[0].get("created_at")
            if ts:
                last_d = ts.strftime("%d.%m.%Y") if hasattr(ts, "strftime") else str(ts)[:10]
        name_parts = [cb.from_user.first_name or "", cb.from_user.last_name or ""]
        name  = " ".join(p for p in name_parts if p) or "—"
        phone_raw = (client or {}).get("phone")
        phone = phone_raw or t(uid, "profile_nophone")
        last_line = t(uid, "profile_last").format(date=last_d) if last_d else ""
        text = t(uid, "profile_text").format(
            name=name, phone=phone, uid=uid,
            total=total, done=done, last=last_line
        )
    except Exception as e:
        logging.warning(f"menu_profile error: {e}")
        phone_raw = None
        text = t(uid, "profile_text").format(name="—", phone="—", uid=uid, total=0, done=0, last="")

    # Проверяем статус агента
    is_agent = False
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(f"{API_URL}/agent/status-by-tg/{uid}",
                            timeout=aiohttp.ClientTimeout(total=4))
            is_agent = (await r.json()).get("is_agent", False)
    except Exception:
        pass

    kb_rows = []
    if not phone_raw:
        kb_rows.append([InlineKeyboardButton(text=t(uid,"profile_link_phone"), callback_data="link_phone_from_profile")])
    if is_agent:
        kb_rows.append([InlineKeyboardButton(text="✅ Агент ARTEZ", url="https://artez.uz/staff.html")])
    else:
        kb_rows.append([InlineKeyboardButton(text="🤝 Стать Агентом", callback_data="menu_agent")])
    kb_rows.append([InlineKeyboardButton(text=t(uid,"btn_settings"), callback_data="menu_settings")])
    kb_rows.append([InlineKeyboardButton(text=t(uid,"btn_menu"), callback_data="go_menu")])
    await cb.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="Markdown")

@dp.callback_query(F.data == "link_phone_from_profile")
async def link_phone_from_profile(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    saved_phone = await get_client_tg_phone(uid)
    if saved_phone:
        try:
            async with aiohttp.ClientSession() as s:
                await s.post(f"{API_URL}/tg-phone-link",
                             json={"phone": saved_phone, "tg_id": uid},
                             timeout=aiohttp.ClientTimeout(total=8))
        except Exception as e:
            logging.warning(f"link_phone_from_profile error: {e}")
        await cb.message.answer(t(uid, "link_phone_ok").format(phone=saved_phone),
                                reply_markup=back_kb(uid), parse_mode="Markdown")
        return
    share_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(uid,"btn_share_phone"), request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await state.set_state(LinkPhoneForm.waiting_contact)
    await cb.message.answer(t(uid,"link_phone_prompt"), reply_markup=share_kb, parse_mode="Markdown")

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
        btn_label = "✍️ Yozish" if lang(client_id) == "uz" else "✍️ Написать оператору"
        client_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=btn_label, callback_data="menu_operator")
        ]])
        await bot.send_message(
            client_id,
            f"📩 *Сообщение от оператора ARTEZ*\n\n{md_escape(msg.text)}",
            parse_mode="Markdown",
            reply_markup=client_kb
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
    await cb.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid,"btn_order_quick"), callback_data="order_type_quick")],
        [InlineKeyboardButton(text=t(uid,"btn_order_full"),  callback_data="order_type_full")],
        [InlineKeyboardButton(text=t(uid,"btn_cancel"),      callback_data="cancel_order")],
    ])
    await cb.message.answer(t(uid,"ask_order_type"), reply_markup=kb)

@dp.callback_query(F.data == "order_type_full")
async def menu_order_full(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    await cb.answer()
    user_data_db[uid] = {}
    await state.set_state(OrderForm.name)
    await cb.message.answer(t(uid,"ask_name"), reply_markup=cancel_kb(uid), parse_mode="Markdown")

@dp.callback_query(F.data == "order_type_quick")
async def menu_order_quick(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    await cb.answer()
    user_data_db[uid] = {"_quick": True}
    await state.set_state(QuickForm.name)
    await cb.message.answer(t(uid,"quick_ask_name"), reply_markup=cancel_kb(uid), parse_mode="Markdown")

_PHONE_RE_BOT = re.compile(r"^\+998\d{9}$")

def normalize_phone_bot(raw: str) -> str:
    """Normalize phone to +998XXXXXXXXX, return empty string if invalid."""
    v = raw.strip().replace(" ","").replace("-","").replace("(","").replace(")","")
    if v.startswith("998") and not v.startswith("+"):
        v = "+" + v
    return v if _PHONE_RE_BOT.match(v) else ""

async def _submit_bot_lead(uid: int, d: dict, is_quick: bool = False, user_from=None) -> bool:
    """POST lead to /api/bot/lead. Returns True on success."""
    try:
        user_obj   = user_from
        first_name = getattr(user_obj, 'first_name', '') or d.get("name", "")
        last_name  = getattr(user_obj, 'last_name',  '') or ''
        username   = getattr(user_obj, 'username',   '') or ''
        client_name = d.get("name") or f"{first_name} {last_name}".strip() or f"TG {uid}"

        note_parts = []
        if username: note_parts.append(f"@{username}")
        if d.get("service_type"): note_parts.append(f"Тип: {d['service_type']}")
        if d.get("date"):         note_parts.append(f"Дата: {d['date']}")

        payload = {
            "client_name":    client_name,
            "client_phone":   d.get("phone",""),
            "branch":         d.get("branch",""),
            "city":           d.get("city",""),
            "address":        d.get("address",""),
            "service":        d.get("service",""),
            "service_type":   d.get("service_type",""),
            "pickup_date":    d.get("date",""),
            "pickup_time":    d.get("time",""),
            "note":           " · ".join(note_parts) if note_parts else "",
            "location":       d.get("location",""),
            "location_address": d.get("location_address",""),
            "client_tg_id":   uid,
            "is_quick":       is_quick,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_URL}/bot/lead",
                json=payload,
                headers={"X-Bot-Token": BOT_TOKEN or ""},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                return r.status == 200
    except Exception as e:
        logging.warning(f"_submit_bot_lead error: {e}")
        return False

# ── БЫСТРАЯ ЗАЯВКА ──
@dp.message(QuickForm.name)
async def quick_name(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    user_data_db.setdefault(uid, {})["name"] = msg.text.strip()
    await state.set_state(QuickForm.phone)
    try:
        client = await get_client_by_tg_id(uid)
        saved_phone = (client or {}).get("phone") or ""
    except Exception:
        saved_phone = ""
    if saved_phone:
        user_data_db[uid]["_saved_phone"] = saved_phone
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text=t(uid,"btn_use_saved_phone").format(phone=saved_phone),
                callback_data="qphone_use_saved"
            ),
            InlineKeyboardButton(text=t(uid,"btn_enter_other_phone"), callback_data="qphone_enter_other"),
        ],[
            InlineKeyboardButton(text=t(uid,"btn_cancel"), callback_data="cancel_order"),
        ]])
        saved_txt = t(uid,"ask_phone_saved") if lang(uid)=="ru" else "2-qadam (3 dan)\n📞 Saqlangan raqamdan foydalanasizmi?"
        await msg.answer(saved_txt, reply_markup=kb, parse_mode="Markdown")
    else:
        await msg.answer(t(uid,"quick_ask_phone"), reply_markup=phone_kb(uid), parse_mode="Markdown")

@dp.callback_query(QuickForm.phone, F.data == "qphone_use_saved")
async def quick_phone_use_saved(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    await cb.answer()
    user_data_db[uid]["phone"] = user_data_db[uid].get("_saved_phone","")
    await state.set_state(QuickForm.branch)
    await cb.message.answer(t(uid,"quick_ask_branch"), reply_markup=branch_kb_quick(uid))

@dp.callback_query(QuickForm.phone, F.data == "qphone_enter_other")
async def quick_phone_enter_other(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    await cb.answer()
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb.message.answer(t(uid,"quick_ask_phone"), reply_markup=phone_kb(uid), parse_mode="Markdown")

async def _maybe_notify_new_client(uid: int, phone: str, user_from):
    """Отправляет уведомление если клиент впервые даёт номер."""
    try:
        existing = await get_client_tg_phone(uid)
        if not existing:
            asyncio.create_task(_notify_new_bot_client(
                uid, getattr(user_from, "first_name", "") or "",
                getattr(user_from, "last_name", "") or "",
                phone, getattr(user_from, "username", "") or ""))
    except Exception as e:
        logging.warning(f"_maybe_notify_new_client error: {e}")

@dp.message(QuickForm.phone, F.contact)
async def quick_phone_contact(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    raw = msg.contact.phone_number or ""
    norm = normalize_phone_bot(raw)
    if not norm:
        await msg.answer(t(uid,"phone_invalid"), reply_markup=phone_kb(uid), parse_mode="Markdown")
        return
    await _maybe_notify_new_client(uid, norm, msg.from_user)
    user_data_db.setdefault(uid, {})["phone"] = norm
    await state.set_state(QuickForm.branch)
    await msg.answer("✅", reply_markup=ReplyKeyboardRemove())
    await msg.answer(t(uid,"quick_ask_branch"), reply_markup=branch_kb_quick(uid))

@dp.message(QuickForm.phone, F.text)
async def quick_phone_text(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    raw = (msg.text or "").strip()
    if raw == t(uid,"btn_enter_phone"):
        await msg.answer(t(uid,"ask_phone_manual"), reply_markup=cancel_kb(uid))
        return
    norm = normalize_phone_bot(raw)
    if not norm:
        await msg.answer(t(uid,"phone_invalid"), reply_markup=phone_kb(uid), parse_mode="Markdown")
        return
    await _maybe_notify_new_client(uid, norm, msg.from_user)
    user_data_db.setdefault(uid, {})["phone"] = norm
    await state.set_state(QuickForm.branch)
    await msg.answer("✅", reply_markup=ReplyKeyboardRemove())
    await msg.answer(t(uid,"quick_ask_branch"), reply_markup=branch_kb_quick(uid))

@dp.callback_query(QuickForm.branch, F.data.in_({"qbranch_zarafshan","qbranch_navoi"}))
async def quick_branch(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    await cb.answer()
    branch = cb.data.replace("qbranch_","")
    user_data_db[uid]["branch"]      = branch
    user_data_db[uid]["branch_name"] = t(uid,"btn_zarafshan") if branch=="zarafshan" else t(uid,"btn_navoi")
    await finish_quick(cb.message, uid, state, user_from=cb.from_user)

def branch_kb_quick(uid):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(uid,"btn_zarafshan"), callback_data="qbranch_zarafshan"),
        InlineKeyboardButton(text=t(uid,"btn_navoi"),     callback_data="qbranch_navoi"),
    ],[
        InlineKeyboardButton(text=t(uid,"btn_cancel"), callback_data="cancel_order"),
    ]])

async def finish_quick(msg, uid: int, state: FSMContext, user_from=None):
    d = user_data_db.get(uid, {})
    user_obj = user_from or getattr(msg, 'from_user', None)
    first_name = getattr(user_obj, 'first_name', '') or ''
    last_name  = getattr(user_obj, 'last_name',  '') or ''
    username   = getattr(user_obj, 'username',   '') or ''

    await upsert_client(tg_id=uid, username=username,
                        first_name=first_name, last_name=last_name,
                        phone=d.get("phone",""), lang=lang(uid))

    result = await _submit_bot_lead(uid, d, is_quick=True, user_from=user_from)
    await state.clear()
    if result:
        await msg.answer(t(uid,"quick_done"), reply_markup=back_kb(uid), parse_mode="Markdown")
    else:
        await msg.answer("✅ " + t(uid,"quick_done"), reply_markup=back_kb(uid), parse_mode="Markdown")

@dp.message(OrderForm.name)
async def order_name(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    user_data_db[uid]["name"] = msg.text
    await state.set_state(OrderForm.phone)
    # Проверяем: есть ли сохранённый номер у клиента
    try:
        client = await get_client_by_tg_id(uid)
        saved_phone = (client or {}).get("phone") or ""
    except Exception:
        saved_phone = ""
    if saved_phone:
        user_data_db[uid]["_saved_phone"] = saved_phone
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text=t(uid, "btn_use_saved_phone").format(phone=saved_phone),
                callback_data="phone_use_saved"
            ),
            InlineKeyboardButton(
                text=t(uid, "btn_enter_other_phone"),
                callback_data="phone_enter_other"
            ),
        ]])
        await msg.answer(t(uid, "ask_phone_saved"), reply_markup=kb, parse_mode="Markdown")
    else:
        await msg.answer(t(uid, "ask_phone"), reply_markup=phone_kb(uid), parse_mode="Markdown")

# Клиент выбрал «Использовать сохранённый номер»
@dp.callback_query(OrderForm.phone, F.data == "phone_use_saved")
async def order_phone_use_saved(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    phone = user_data_db[uid].get("_saved_phone", "")
    if not phone:
        await cb.answer()
        await cb.message.answer(t(uid, "ask_phone"), reply_markup=phone_kb(uid), parse_mode="Markdown")
        return
    user_data_db[uid]["phone"] = phone
    await cb.message.edit_reply_markup(reply_markup=None)
    await state.set_state(OrderForm.branch)
    await cb.message.answer(f"✅ {phone}")
    await cb.message.answer(t(uid, "ask_branch"), reply_markup=branch_kb(uid))

# Клиент выбрал «Ввести другой номер» из inline-меню
@dp.callback_query(OrderForm.phone, F.data == "phone_enter_other")
async def order_phone_enter_other(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    await cb.answer()
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb.message.answer(t(uid, "ask_phone"), reply_markup=phone_kb(uid), parse_mode="Markdown")

# Клиент нажал «Поделиться номером» — Telegram прислал contact
@dp.message(OrderForm.phone, F.contact)
async def order_phone_contact(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    phone = msg.contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone
    await _maybe_notify_new_client(uid, phone, msg.from_user)
    user_data_db[uid]["phone"] = phone
    await state.set_state(OrderForm.branch)
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
    await _maybe_notify_new_client(uid, raw, msg.from_user)
    user_data_db.setdefault(uid, {})["phone"] = raw
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

# Клиент отправил GPS-локацию (нативная кнопка Telegram)
@dp.message(OrderForm.location, F.location)
async def order_location_geo(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    lat = msg.location.latitude
    lon = msg.location.longitude
    user_data_db[uid]["location"]         = f"{lat:.5f}, {lon:.5f}"
    user_data_db[uid]["location_address"] = ""
    await state.set_state(OrderForm.service)
    await msg.answer("📍 ✅", reply_markup=ReplyKeyboardRemove())
    await msg.answer(t(uid,"ask_service"), reply_markup=service_kb(uid))

# Клиент выбрал точку на карте (Telegram Mini App)
@dp.message(OrderForm.location, F.web_app_data)
async def order_location_webapp(msg: Message, state: FSMContext):
    import json as _json
    uid = msg.from_user.id
    try:
        data = _json.loads(msg.web_app_data.data)
        la, lo = float(data["lat"]), float(data["lon"])
        user_data_db[uid]["location"]         = f"{la:.5f}, {lo:.5f}"
        user_data_db[uid]["location_address"] = data.get("address", "")
    except Exception as e:
        logging.warning(f"WebApp location parse error: {e}")
        user_data_db[uid]["location"]         = ""
        user_data_db[uid]["location_address"] = ""
    await state.set_state(OrderForm.service)
    addr_txt = user_data_db[uid].get("location_address") or user_data_db[uid].get("location") or ""
    await msg.answer(f"📍 ✅ {addr_txt}", reply_markup=ReplyKeyboardRemove())
    await msg.answer(t(uid,"ask_service"), reply_markup=service_kb(uid))

# Клиент нажал «Пропустить»
@dp.message(OrderForm.location, F.text)
async def order_location_skip(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    user_data_db[uid]["location"]         = ""
    user_data_db[uid]["location_address"] = ""
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
    answer_fn = msg_or_cb.answer

    user_obj   = user_from or getattr(msg_or_cb, 'from_user', None)
    first_name = getattr(user_obj, 'first_name', '') or ''
    last_name  = getattr(user_obj, 'last_name',  '') or ''
    username   = getattr(user_obj, 'username',   '') or ''
    tg_name    = f"{first_name} {last_name}".strip() or f"@{username}"

    d["time"] = time_txt

    await upsert_client(tg_id=uid, username=username,
                        first_name=first_name, last_name=last_name,
                        phone=d.get("phone",""), lang=lang(uid))
    if d.get("phone",""):
        await upsert_crm_client(phone=d["phone"], first_name=first_name, last_name=last_name,
                                tg_id=uid, tg_username=username, source="bot")

    await _submit_bot_lead(uid, d, is_quick=False, user_from=user_from)

    await answer_fn(t(uid,"quick_done"), reply_markup=back_kb(uid), parse_mode="Markdown")

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
        "note":        f"Telegram (бот, подробная заявка)",
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
    await ensure_prices_fresh()
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
    min_order = get_cached_min_order(svc, svctype)
    if min_order:
        sqm_bill = max(sqm_real, min_order)
    else:
        sqm_bill = sqm_real
    price     = get_cached_price(svc, svctype)
    total     = int(sqm_bill * price)
    unit_sym  = get_unit_symbol(get_cached_unit_key(svc, svctype), uid)

    fmt_args = dict(
        w=int(w), l=int(l), sqm=round(sqm_real, 2), unit=unit_sym,
        svc=svc_display_name(uid, svc, svctype),
        price=f"{price:,}".replace(",", " "),
        total=f"{total:,}".replace(",", " "),
        min_order=min_order,
    )
    if min_order and sqm_real < min_order:
        result = t(uid, "calc_result_below_min").format(**fmt_args)
    else:
        result = t(uid, "calc_result_no_min").format(**fmt_args)
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

# ── МАРШРУТ: ВОДИТЕЛЬ ЗАБИРАЕТ / СДАЁТ (rp:) ──
_ROUTE_STATUS_RU = {
    "confirmed": "Подтверждён", "pickup": "Вывоз", "received": "В мастерской",
    "washing": "Стирка", "ready": "Готов", "delivery": "Доставка", "delivered": "Доставлен",
}
_STAFF_CONFIRM_ROLES = {"admin", "manager"}
_QTY_SEP = "\n\n<b>📦 Сколько изделий забрали?</b>"

def _route_pickup_kb(order_id: int, status: str) -> InlineKeyboardMarkup:
    if status == "confirmed":
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Забрал", callback_data=f"rp:{order_id}:take")
        ]])
    elif status == "pickup":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏭 Сдал в мастерскую", callback_data=f"rp:{order_id}:deliver")],
            [InlineKeyboardButton(text="↩️ Не забирал", callback_data=f"rp:{order_id}:undo")],
        ])
    elif status == "received":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить приём", callback_data=f"rp:{order_id}:confirm_receive")],
            [InlineKeyboardButton(text="↩️ Не сдавал", callback_data=f"rp:{order_id}:undo_deliver"),
             InlineKeyboardButton(text="📋 История", callback_data=f"rp:{order_id}:history")],
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📋 История", callback_data=f"rp:{order_id}:history")
        ]])

def _qty_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=str(n), callback_data=f"rp:{order_id}:qty:{n}") for n in range(1, 6)],
        [InlineKeyboardButton(text=str(n), callback_data=f"rp:{order_id}:qty:{n}") for n in range(6, 11)],
        [InlineKeyboardButton(text="↩️ Отменить", callback_data=f"rp:{order_id}:qty:0")],
    ])

@dp.callback_query(F.data.startswith("rp:"))
async def route_pickup_cb(cb: CallbackQuery):
    try:
        parts    = cb.data.split(":")
        order_id = int(parts[1])
        action   = parts[2]

        order = await get_order_by_id(order_id)
        if not order:
            await cb.answer("❌ Заказ не найден", show_alert=True)
            return

        cur   = order["status"]
        w     = cb.from_user
        wname = f"{w.first_name or ''} {w.last_name or ''}".strip()
        orig  = cb.message.html_text or cb.message.text or ""

        # ── История ──────────────────────────────────────────────────
        if action == "history":
            activity = await get_order_activity_by_id(order_id)
            lines = [f"📦 {order.get('order_num','')}"]
            for a in activity[-8:]:
                t = str(a.get("created_at",""))[:16].replace("T"," ")
                d = a.get("details","") or a.get("action","")
                for k,v in _ROUTE_STATUS_RU.items(): d = d.replace(k, v)
                lines.append(f"{t} {d}")
            await cb.answer("\n".join(lines)[:200], show_alert=True)
            return

        # ── Выбор количества изделий ─────────────────────────────────
        if action == "qty":
            qty = int(parts[3]) if len(parts) > 3 else 0
            clean = orig.split(_QTY_SEP)[0] if _QTY_SEP in orig else orig
            if qty == 0:
                await cb.message.edit_text(clean, reply_markup=_route_pickup_kb(order_id, "confirmed"),
                                           parse_mode="HTML", disable_web_page_preview=True)
                await cb.answer("Отменено")
                return
            await update_order_status_by_id(order_id, "pickup", by_tg_id=w.id, by_name=wname,
                                            note=f"Забрал {qty} изд.")
            await cb.message.edit_text(clean, reply_markup=_route_pickup_kb(order_id, "pickup"),
                                       parse_mode="HTML", disable_web_page_preview=True)
            await cb.answer(f"✅ Забрал {qty} изделий")
            return

        # ── Подтвердить приём (только admin/manager) ─────────────────
        if action == "confirm_receive":
            staff = await get_staff_by_tg_id_for_lead(w.id)
            if not staff or staff.get("role") not in _STAFF_CONFIRM_ROLES:
                await cb.answer("❌ Доступно только менеджерам и администраторам", show_alert=True)
                return
            staff_name = f"{staff.get('first_name','')} {staff.get('last_name','')}".strip() or wname
            await update_order_status_by_id(order_id, "washing", by_tg_id=w.id, by_name=staff_name,
                                            note="Подтверждён приём в мастерской")
            final_kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📋 История", callback_data=f"rp:{order_id}:history")
            ]])
            await cb.message.edit_reply_markup(reply_markup=final_kb)
            await cb.answer(f"✅ Принято! Статус → Стирка")
            return

        # ── Статусные действия водителя ───────────────────────────────
        if action == "take":
            if cur != "confirmed":
                await cb.answer(f"ℹ️ {_ROUTE_STATUS_RU.get(cur, cur)}")
                return
            qty_text = orig + _QTY_SEP
            await cb.message.edit_text(qty_text, reply_markup=_qty_kb(order_id),
                                       parse_mode="HTML", disable_web_page_preview=True)
            await cb.answer("Укажите количество изделий")
            return

        elif action == "undo":
            if cur != "pickup":
                await cb.answer(f"ℹ️ {_ROUTE_STATUS_RU.get(cur, cur)}")
                return
            new_status, toast = "confirmed", "↩️ Не забирал — отменено"

        elif action == "deliver":
            if cur != "pickup":
                await cb.answer(f"ℹ️ {_ROUTE_STATUS_RU.get(cur, cur)}")
                return
            new_status, toast = "received", "🏭 Сдан в мастерскую"

        elif action == "undo_deliver":
            if cur != "received":
                await cb.answer(f"ℹ️ {_ROUTE_STATUS_RU.get(cur, cur)}")
                return
            new_status, toast = "pickup", "↩️ Не сдавал — отменено"

        else:
            await cb.answer()
            return

        await update_order_status_by_id(order_id, new_status, by_tg_id=w.id, by_name=wname,
                                        note=f"Маршрут: {toast}")
        await cb.message.edit_text(orig, reply_markup=_route_pickup_kb(order_id, new_status),
                                   parse_mode="HTML", disable_web_page_preview=True)
        await cb.answer(toast)

    except Exception as e:
        logging.warning(f"route_pickup_cb error: {e}")
        try: await cb.answer("❌ Ошибка сервера", show_alert=True)
        except Exception: pass


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
    await ensure_prices_fresh()
    await msg.answer(build_prices_text(uid), reply_markup=back_kb(uid), parse_mode="Markdown")

@dp.message(Command("branches"))
async def cmd_branches(msg: Message):
    uid = msg.from_user.id
    if uid not in user_lang:
        await msg.answer("👋", reply_markup=lang_kb()); return
    await msg.answer(t(uid,"branches_text"), reply_markup=back_kb(uid), parse_mode="Markdown")

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
    await load_units()
    await load_site_settings()
    # Удаляем webhook если был установлен (artez_api мог его поставить)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("✅ Webhook deleted, switching to polling")
    except Exception as e:
        logging.warning(f"delete_webhook error: {e}")
    logging.info("✅ Bot started, polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
