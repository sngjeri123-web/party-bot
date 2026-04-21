import os
import io
import json
import base64
import random
import logging
import httpx
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# ========================
# НАСТРОЙКИ — ЗАПОЛНИ ПЕРЕД ЗАПУСКОМ
# ========================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
_admin_env = os.environ.get("ADMIN_ID")
ADMIN_ID = int(_admin_env) if _admin_env else None

# ========================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Состояния ConversationHandler ---
WAITING_NAMES = 1
WAITING_PHOTO = 2

# --- Данные ---
DATA_FILE = os.environ.get("DATA_FILE", "bot_data.json")
participants = {}
draw_done = False
revealed = False


def _save_data():
    """Сохранить данные на диск."""
    try:
        dir_name = os.path.dirname(DATA_FILE)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        data = {
            "draw_done": draw_done,
            "revealed": revealed,
            "participants": {},
        }
        for cid, p in participants.items():
            entry = {
                "names": p["names"],
                "cuisine": p.get("cuisine"),
                "mission": p.get("mission"),
                "photo": base64.b64encode(p["photo"]).decode() if p.get("photo") else None,
                "card": base64.b64encode(p["card"]).decode() if p.get("card") else None,
            }
            data["participants"][str(cid)] = entry
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, ensure_ascii=False)
        logger.info(f"Данные сохранены ({len(participants)} участников)")
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")


def _load_data():
    """Загрузить данные с диска."""
    global participants, draw_done, revealed
    try:
        if not os.path.exists(DATA_FILE):
            return
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
        draw_done = data.get("draw_done", False)
        revealed = data.get("revealed", False)
        participants.clear()
        for cid_str, p in data.get("participants", {}).items():
            participants[int(cid_str)] = {
                "names": p["names"],
                "cuisine": tuple(p["cuisine"]) if p.get("cuisine") else None,
                "mission": p.get("mission"),
                "photo": base64.b64decode(p["photo"]) if p.get("photo") else None,
                "card": base64.b64decode(p["card"]) if p.get("card") else None,
            }
        logger.info(f"Данные загружены ({len(participants)} участников)")
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")

# --- Кухни мира (название, эмодзи, описание, код страны для flagcdn) ---
CUISINES = [
    ("Итальянская", "🇮🇹", "Паста, пицца, ризотто, тирамису", "it"),
    ("Грузинская", "🇬🇪", "Хачапури, хинкали, шашлык, сациви", "ge"),
    ("Японская", "🇯🇵", "Суши, рамен, темпура, мисо-суп", "jp"),
    ("Мексиканская", "🇲🇽", "Тако, буррито, начос, гуакамоле", "mx"),
    ("Французская", "🇫🇷", "Круассаны, рататуй, крем-брюле, багет", "fr"),
    ("Тайская", "🇹🇭", "Том ям, пад тай, карри, манго с рисом", "th"),
    ("Индийская", "🇮🇳", "Карри, наан, тандури, самоса", "in"),
    ("Греческая", "🇬🇷", "Гирос, мусака, дзадзики, сувлаки", "gr"),
    ("Турецкая", "🇹🇷", "Кебаб, баклава, лахмаджун, айран", "tr"),
    ("Китайская", "🇨🇳", "Димсам, утка по-пекински, вок, пельмени", "cn"),
    ("Корейская", "🇰🇷", "Кимчи, бибимбап, булгоги, токпокки", "kr"),
    ("Испанская", "🇪🇸", "Паэлья, тапас, хамон, гаспачо", "es"),
    ("Узбекская", "🇺🇿", "Плов, самса, лагман, манты", "uz"),
    ("Американская (BBQ)", "🇺🇸", "Бургеры, рёбрышки, стейк, кукуруза", "us"),
    ("Вьетнамская", "🇻🇳", "Фо, спринг-роллы, бань ми, бун бо", "vn"),
    ("Ливанская", "🇱🇧", "Хумус, фалафель, табуле, шаурма", "lb"),
    ("Марокканская", "🇲🇦", "Тажин, кускус, пастилла, харира", "ma"),
    ("Бразильская", "🇧🇷", "Шурраско, фейжоада, пау-ди-кейжу, асаи", "br"),
    ("Украинская", "🇺🇦", "Борщ, вареники, сало, голубцы", "ua"),
    ("Армянская", "🇦🇲", "Долма, лаваш, хоровац, гата", "am"),
]

# Кэш загруженных флагов
_flag_cache = {}

# --- Тайные задания ---
MISSIONS_18_PLUS = [
    "🔥 Кормите друг друга с рук и максимально пошло комментируйте каждый кусочек. «Ммм, какой сочный...»",
    "🔥 Каждый тост заканчивайте фразой «...и в постели». Без исключений.",
    "🔥 Устройте «стриптиз» фартука — медленно и эротично снимайте фартук под конец готовки. Музыку включите сами.",
    "🔥 Проведите «мастер-класс» по вашему блюду в стиле ASMR — шёпотом и с придыханием. Чем ближе к микрофону, тем лучше.",
    "🔥 Придумайте пошлое название для КАЖДОГО блюда на столе и озвучивайте их вслух весь вечер.",
    "🔥 Изображайте что ваше блюдо — мощный афродизиак. Расписывайте его «свойства» каждому гостю с серьёзным лицом.",
    "🔥 Снимите 15-секундный «OnlyFans рилс» про вашу готовку. Фейковый, но максимально убедительный.",
]

MISSIONS_FUN = [
    "😂 Весь вечер говорите с акцентом страны вашей кухни. Не знаете какой — выдумайте. Главное не сломаться.",
    "😂 Расскажите полностью выдуманную историю происхождения вашего блюда. Чем бредовее — тем лучше. Отстаивайте до конца.",
    "😂 Каждый раз когда кто-то хвалит вашу еду — вставайте и кланяйтесь как на вручении Оскара. Можно со слезами.",
    "😂 Вы — фуд-критики из Мишлен. Попробуйте блюдо другой пары и дайте рецензию голосом Гордона Рамзи. IT'S RAW!",
    "😂 Устройте дегустацию вслепую для другой пары. Завяжите им глаза и снимайте реакцию на видео.",
    "😂 Перед подачей блюда обязаны станцевать народный танец вашей кухни. Загуглите или выдумайте — неважно.",
    "😂 Сделайте 10 фото блюда как фуд-блогер. Покажите ВСЕ 10 с серьёзным разбором ракурсов и света.",
    "😂 Придумайте рекламный джингл для вашего блюда и спойте его хором перед подачей. Бонус если с хореографией.",
]

ALL_MISSIONS = MISSIONS_18_PLUS + MISSIONS_FUN


# --- Генерация картинок ---

CARD_W, CARD_H = 800, 520

async def download_flag(country_code: str) -> Image.Image:
    """Скачать флаг страны с flagcdn.com, кэшировать."""
    if country_code in _flag_cache:
        return _flag_cache[country_code].copy()
    url = f"https://flagcdn.com/w1280/{country_code}.png"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
            _flag_cache[country_code] = img
            return img.copy()
    except Exception as e:
        logger.error(f"Не удалось скачать флаг {country_code}: {e}")
        img = Image.new("RGBA", (1280, 854), (60, 60, 80, 255))
        return img


def _round_corners(img: Image.Image, radius: int) -> Image.Image:
    """Закругляем углы изображения."""
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, img.width, img.height), radius=radius, fill=255)
    result = img.copy()
    result.putalpha(mask)
    return result


def _draw_gradient(draw: ImageDraw.Draw, w: int, h: int,
                   start_y: int, color: tuple, max_alpha: int = 200):
    """Рисуем вертикальный градиент снизу вверх."""
    for y in range(start_y, h):
        progress = (y - start_y) / (h - start_y)
        alpha = int(max_alpha * progress)
        draw.line([(0, y), (w, y)], fill=(*color, alpha))


def crop_circle(photo_bytes: bytes, size: int = 240) -> Image.Image:
    """Обрезать фото в круг с толстой белой обводкой и тенью."""
    img = Image.open(io.BytesIO(photo_bytes)).convert("RGBA")
    w, h = img.size
    s = min(w, h)
    left = (w - s) // 2
    top = (h - s) // 2
    img = img.crop((left, top, left + s, top + s))
    img = img.resize((size, size), Image.LANCZOS)

    border = 6
    total = size + border * 2 + 16  # +16 для тени

    # Тень
    shadow = Image.new("RGBA", (total, total), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    for i in range(8):
        a = 30 - i * 3
        offset = border + i
        shadow_draw.ellipse(
            (offset, offset + 4, total - offset, total - offset + 4),
            fill=(0, 0, 0, max(a, 0)),
        )

    # Белая обводка
    border_draw = ImageDraw.Draw(shadow)
    border_draw.ellipse(
        (8, 8, 8 + size + border * 2, 8 + size + border * 2),
        fill=(255, 255, 255, 255),
    )

    # Круглая маска для фото
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, size, size), fill=255)

    circle = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    circle.paste(img, (0, 0), mask)
    shadow.paste(circle, (8 + border, 8 + border), circle)
    return shadow


def _get_font(size: int, bold: bool = False):
    """Попробовать загрузить системный шрифт."""
    if bold:
        font_paths = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNSText-Bold.otf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
    else:
        font_paths = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNSText.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _center_text(draw: ImageDraw.Draw, y: int, text: str,
                 font, fill, card_w: int, shadow: bool = False):
    """Рисуем текст по центру, опционально с тенью."""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (card_w - tw) // 2
    if shadow:
        draw.text((x + 2, y + 2), text, fill=(0, 0, 0, 140), font=font)
    draw.text((x, y), text, fill=fill, font=font)


async def generate_card(photo_bytes: Optional[bytes], names: str,
                        cuisine_name: str, flag_emoji: str,
                        description: str, country_code: str) -> bytes:
    """Генерирует красивую карточку: фото в кружке на фоне флага + текст."""

    # Фон — флаг, растянутый и размытый
    flag = await download_flag(country_code)
    flag = flag.resize((CARD_W, CARD_H), Image.LANCZOS)

    # Градиентное затемнение (снизу сильнее)
    gradient_overlay = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(gradient_overlay)
    # Верхнее лёгкое затемнение
    for y in range(CARD_H):
        top_alpha = 80
        bottom_alpha = 210
        alpha = int(top_alpha + (bottom_alpha - top_alpha) * (y / CARD_H))
        grad_draw.line([(0, y), (CARD_W, y)], fill=(0, 0, 0, alpha))

    card = Image.alpha_composite(flag, gradient_overlay)

    # Фото в кружке
    if photo_bytes:
        circle = crop_circle(photo_bytes, 240)
        cx = (CARD_W - circle.width) // 2
        card.paste(circle, (cx, 16), circle)
        text_top = 296
    else:
        text_top = 100

    # Плашка для текста — полупрозрачный закруглённый прямоугольник
    plate_margin = 40
    plate_top = text_top - 16
    plate_h = CARD_H - plate_top - 20
    plate = Image.new("RGBA", (CARD_W - plate_margin * 2, plate_h), (0, 0, 0, 0))
    plate_draw = ImageDraw.Draw(plate)
    plate_draw.rounded_rectangle(
        (0, 0, plate.width, plate.height),
        radius=24,
        fill=(0, 0, 0, 90),
    )
    card.paste(plate, (plate_margin, plate_top), plate)

    # Текст
    draw = ImageDraw.Draw(card)
    font_names = _get_font(42, bold=True)
    font_cuisine = _get_font(30, bold=True)
    font_desc = _get_font(20)
    font_divider = _get_font(16)

    # Имена
    _center_text(draw, text_top, names, font_names, "white", CARD_W, shadow=True)

    # Разделитель
    div_y = text_top + 56
    div_w = 120
    div_x = (CARD_W - div_w) // 2
    draw.line([(div_x, div_y), (div_x + div_w, div_y)], fill=(255, 220, 100, 200), width=2)

    # Кухня (без эмодзи — они не рендерятся в Pillow)
    cuisine_text = f"{cuisine_name} кухня"
    _center_text(draw, div_y + 14, cuisine_text, font_cuisine, (255, 220, 100), CARD_W, shadow=True)

    # Описание
    _center_text(draw, div_y + 58, description, font_desc, (210, 210, 210), CARD_W)

    # Закруглённые углы у всей карточки
    card = _round_corners(card, 28)

    # Финальная картинка на белом фоне (чтобы прозрачные углы не были чёрными)
    final = Image.new("RGB", (CARD_W, CARD_H), (30, 30, 35))
    final.paste(card, (0, 0), card)

    buf = io.BytesIO()
    final.save(buf, format="PNG", quality=95)
    buf.seek(0)
    return buf.getvalue()


# --- Вспомогательные функции ---

def get_admin_keyboard():
    """Клавиатура для админа."""
    admin_chat = ADMIN_ID
    registered = admin_chat in participants if admin_chat else False
    keyboard = []
    if not registered:
        keyboard.append([InlineKeyboardButton("📝 Зарегать нашу пару", callback_data="admin_register")])
    else:
        names = participants[admin_chat]["names"]
        keyboard.append([InlineKeyboardButton(f"✅ Вы: {names}", callback_data="noop")])
    keyboard.extend([
        [InlineKeyboardButton("📊 Кто зарегался", callback_data="admin_status")],
        [InlineKeyboardButton("🎲 Запустить жеребьёвку!", callback_data="admin_draw")],
        [InlineKeyboardButton("🔓 Раскрыть задания всем", callback_data="admin_reveal")],
        [InlineKeyboardButton("🔄 Сбросить всё", callback_data="admin_reset")],
    ])
    return InlineKeyboardMarkup(keyboard)


def get_user_keyboard():
    """Клавиатура для участника после жеребьёвки."""
    keyboard = [
        [InlineKeyboardButton("🍽 Моя кухня", callback_data="my_cuisine")],
        [InlineKeyboardButton("🤫 Моё задание", callback_data="my_mission")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_reregister_keyboard():
    """Клавиатура для повторной регистрации."""
    keyboard = [
        [InlineKeyboardButton("🔄 Зарегаться заново", callback_data="reregister")],
    ]
    return InlineKeyboardMarkup(keyboard)


def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь админом."""
    return ADMIN_ID is not None and user_id == ADMIN_ID


# --- Хэндлеры ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка /start."""
    global ADMIN_ID
    user = update.effective_user
    chat_id = update.effective_chat.id

    # Если админ ещё не установлен — первый кто написал /start становится админом
    if ADMIN_ID is None:
        ADMIN_ID = user.id
        await update.message.reply_text(
            f"👑 Привет, {user.first_name}! Ты теперь админ вечеринки.\n"
            f"Твой Telegram ID: `{user.id}`\n\n"
            f"Когда все зарегаются — жми кнопку жеребьёвки!",
            parse_mode="Markdown",
            reply_markup=get_admin_keyboard(),
        )
        return ConversationHandler.END

    # Если это админ снова
    if is_admin(user.id):
        await update.message.reply_text(
            "👑 Админ-панель:",
            reply_markup=get_admin_keyboard(),
        )
        return ConversationHandler.END

    # Если участник уже зарегистрирован
    if chat_id in participants:
        if draw_done:
            await update.message.reply_text(
                f"Ты уже в деле, {participants[chat_id]['names']}! 🎉\n"
                f"Жми кнопки чтобы посмотреть свою кухню и задание.",
                reply_markup=get_user_keyboard(),
            )
        else:
            await update.message.reply_text(
                f"Ты уже зарегался как: **{participants[chat_id]['names']}** ✅\n"
                f"Жди жеребьёвку! 🎰",
                parse_mode="Markdown",
            )
        return ConversationHandler.END

    # Новый участник — просим ввести имена
    await update.message.reply_text(
        "🎉 Добро пожаловать на вечеринку «Кухня народов»!\n\n"
        "Напиши имена вашей пары, например:\n"
        "• `Макс и Катя`\n"
        "• Или просто своё имя, если ты один: `Артём`",
        parse_mode="Markdown",
    )
    return WAITING_NAMES


async def receive_names(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем имена от участника."""
    names = update.message.text.strip()

    if len(names) < 2 or len(names) > 100:
        await update.message.reply_text(
            "🤔 Что-то не то. Напиши имена нормально, например: `Макс и Катя`",
            parse_mode="Markdown",
        )
        return WAITING_NAMES

    context.user_data["reg_names"] = names
    await update.message.reply_text(
        f"👍 **{names}** — отлично!\n\n"
        f"Теперь пришли ваше совместное фото 📸\n"
        f"(или напиши `скип` если без фото)",
        parse_mode="Markdown",
    )
    return WAITING_PHOTO


async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем фото от участника."""
    chat_id = update.effective_chat.id
    names = context.user_data.get("reg_names", "???")
    photo_bytes = None

    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        buf = io.BytesIO()
        await photo_file.download_to_memory(buf)
        photo_bytes = buf.getvalue()
    elif update.message.text and update.message.text.strip().lower() in ("скип", "skip", "нет", "-"):
        photo_bytes = None
    else:
        await update.message.reply_text(
            "📸 Пришли фото или напиши `скип`",
            parse_mode="Markdown",
        )
        return WAITING_PHOTO

    participants[chat_id] = {
        "names": names,
        "cuisine": None,
        "mission": None,
        "photo": photo_bytes,
        "card": None,
    }
    _save_data()

    count = len(participants)
    photo_status = "с фото ✨" if photo_bytes else "без фото"
    await update.message.reply_text(
        f"✅ Зарегано: **{names}** ({photo_status})\n"
        f"Вы {count}-е участники! Ждите жеребьёвку 🎰\n\n"
        f"Когда админ запустит розыгрыш — я пришлю вам кухню и тайное задание.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена."""
    await update.message.reply_text("Ок, отменено. Напиши /start чтобы начать заново.")
    return ConversationHandler.END


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий inline-кнопок."""
    global draw_done, revealed, participants

    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    data = query.data

    # --- Админские кнопки ---
    if data == "admin_status" and is_admin(user_id):
        if not participants:
            await query.edit_message_text(
                "📊 Пока никто не зарегался. Пусто 🦗",
                reply_markup=get_admin_keyboard(),
            )
            return

        lines = [f"📊 **Зарегистрировано: {len(participants)}**\n"]
        for i, (cid, p) in enumerate(participants.items(), 1):
            cuisine_status = f" → {p['cuisine'][0]} {p['cuisine'][1]}" if p.get("cuisine") else ""
            lines.append(f"{i}. {p['names']}{cuisine_status}")

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=get_admin_keyboard(),
        )

    elif data == "admin_draw" and is_admin(user_id):
        if draw_done:
            await query.edit_message_text(
                "⚠️ Жеребьёвка уже была! Чтобы переиграть — сначала сбрось кнопкой 🔄",
                reply_markup=get_admin_keyboard(),
            )
            return

        if not participants:
            await query.edit_message_text(
                "❌ Никто не зарегался! Нельзя разыграть пустоту 😅",
                reply_markup=get_admin_keyboard(),
            )
            return

        # Рандомим кухни
        num = len(participants)
        selected_cuisines = random.sample(CUISINES, min(num, len(CUISINES)))
        selected_missions = random.sample(ALL_MISSIONS, min(num, len(ALL_MISSIONS)))

        for i, (cid, p) in enumerate(participants.items()):
            p["cuisine"] = selected_cuisines[i]
            p["mission"] = selected_missions[i]

        draw_done = True
        _save_data()

        await query.edit_message_text(
            "🎲 Жеребьёвка запущена! Генерирую карточки... ⏳",
        )

        # Генерируем карточки и рассылаем
        success = 0
        for cid, p in participants.items():
            cuisine_name, flag_emoji, description, country_code = p["cuisine"]
            try:
                card_bytes = await generate_card(
                    p.get("photo"), p["names"],
                    cuisine_name, flag_emoji, description, country_code,
                )
                p["card"] = card_bytes

                await context.bot.send_photo(
                    chat_id=cid,
                    photo=card_bytes,
                    caption=(
                        f"🎉🎉🎉 ЖЕРЕБЬЁВКА СОСТОЯЛАСЬ!\n\n"
                        f"🍽 **{p['names']}**, вам выпала:\n"
                        f"**{flag_emoji} {cuisine_name} кухня**\n"
                        f"_{description}_\n\n"
                        f"━━━━━━━━━━━━━━━\n\n"
                        f"🤫 **Ваше ТАЙНОЕ задание:**\n"
                        f"{p['mission']}\n\n"
                        f"⚠️ Никому не говорите про задание до конца вечеринки!"
                    ),
                    parse_mode="Markdown",
                    reply_markup=get_user_keyboard(),
                )
                success += 1
            except Exception as e:
                logger.error(f"Не удалось отправить сообщение {cid}: {e}")

        _save_data()
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🎲 Жеребьёвка завершена!\n"
                f"✅ Отправлено {success}/{len(participants)} участникам.\n\n"
                f"Все получили карточку с кухней и тайным заданием!"
            ),
            reply_markup=get_admin_keyboard(),
        )

    elif data == "admin_reveal" and is_admin(user_id):
        if not draw_done:
            await query.edit_message_text(
                "⚠️ Сначала проведи жеребьёвку!",
                reply_markup=get_admin_keyboard(),
            )
            return

        if revealed:
            await query.edit_message_text(
                "⚠️ Задания уже раскрыты!",
                reply_markup=get_admin_keyboard(),
            )
            return

        revealed = True
        _save_data()

        # Собираем общий список
        lines = ["🔓 **РАСКРЫТИЕ ТАЙНЫХ ЗАДАНИЙ!**\n", "Вот кто что делал весь вечер:\n"]
        for cid, p in participants.items():
            cuisine_name, flag, _ = p["cuisine"]
            lines.append(f"**{p['names']}** — {flag} {cuisine_name}")
            lines.append(f"   └ {p['mission']}\n")

        reveal_text = "\n".join(lines)

        # Рассылаем всем
        success = 0
        for cid in participants:
            try:
                await context.bot.send_message(
                    chat_id=cid,
                    text=reveal_text,
                    parse_mode="Markdown",
                )
                success += 1
            except Exception as e:
                logger.error(f"Не удалось отправить reveal {cid}: {e}")

        await query.edit_message_text(
            f"🔓 Задания раскрыты!\n"
            f"Отправлено {success}/{len(participants)} участникам.",
            reply_markup=get_admin_keyboard(),
        )

    elif data == "admin_register" and is_admin(user_id):
        if chat_id in participants:
            await query.edit_message_text(
                f"✅ Вы уже зарегались как: {participants[chat_id]['names']}",
                reply_markup=get_admin_keyboard(),
            )
            return
        await query.edit_message_text(
            "📝 Напиши имена вашей пары, например:\n"
            "`Макс и Катя`",
            parse_mode="Markdown",
        )
        context.user_data["admin_state"] = "awaiting_names"
        return

    elif data == "noop":
        return

    elif data == "admin_reset" and is_admin(user_id):
        # Подтверждение сброса
        keyboard = [
            [
                InlineKeyboardButton("✅ Да, сбросить", callback_data="confirm_reset"),
                InlineKeyboardButton("❌ Нет", callback_data="cancel_reset"),
            ]
        ]
        await query.edit_message_text(
            "⚠️ Точно сбросить ВСЁ? Все регистрации и результаты удалятся!",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data == "confirm_reset" and is_admin(user_id):
        participants.clear()
        draw_done = False
        revealed = False
        _save_data()
        await query.edit_message_text(
            "🔄 Всё сброшено! Можно начинать заново.",
            reply_markup=get_admin_keyboard(),
        )

    elif data == "cancel_reset" and is_admin(user_id):
        await query.edit_message_text(
            "👑 Админ-панель:",
            reply_markup=get_admin_keyboard(),
        )

    # --- Кнопка перерегистрации ---
    elif data == "reregister":
        await query.edit_message_text(
            "🎉 Давай заново!\n\n"
            "Напиши /start чтобы зарегаться.",
        )
        return

    # --- Кнопки участников ---
    elif data == "my_cuisine":
        if chat_id not in participants or not participants[chat_id].get("cuisine"):
            await query.edit_message_text(
                "🤷 Ты не зареган или жеребьёвка ещё не была!",
                reply_markup=get_reregister_keyboard() if chat_id not in participants else get_user_keyboard(),
            )
            return
        p = participants[chat_id]
        cuisine_name, flag, description = p["cuisine"]
        await query.edit_message_text(
            f"🍽 **{p['names']}**, ваша кухня:\n\n"
            f"**{flag} {cuisine_name}**\n"
            f"_{description}_",
            parse_mode="Markdown",
            reply_markup=get_user_keyboard(),
        )

    elif data == "my_mission":
        if chat_id not in participants or not participants[chat_id].get("mission"):
            await query.edit_message_text(
                "🤷 Ты не зареган или жеребьёвка ещё не была!",
                reply_markup=get_reregister_keyboard() if chat_id not in participants else get_user_keyboard(),
            )
            return
        p = participants[chat_id]
        await query.edit_message_text(
            f"🤫 **Ваше тайное задание:**\n\n"
            f"{p['mission']}\n\n"
            f"⚠️ Никому не показывай!",
            parse_mode="Markdown",
            reply_markup=get_user_keyboard(),
        )


async def admin_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода от админа (имена и фото, через inline-кнопку)."""
    if not is_admin(update.effective_user.id):
        return
    state = context.user_data.get("admin_state")
    if not state:
        return

    chat_id = update.effective_chat.id

    if state == "awaiting_names":
        if not update.message.text:
            return
        names = update.message.text.strip()
        if len(names) < 2 or len(names) > 100:
            await update.message.reply_text(
                "🤔 Что-то не то. Напиши нормально, например: `Макс и Катя`",
                parse_mode="Markdown",
            )
            return
        context.user_data["admin_reg_names"] = names
        context.user_data["admin_state"] = "awaiting_photo"
        await update.message.reply_text(
            f"👍 **{names}** — отлично!\n\n"
            f"Теперь пришли ваше совместное фото 📸\n"
            f"(или напиши `скип` если без фото)",
            parse_mode="Markdown",
        )
        return

    if state == "awaiting_photo":
        names = context.user_data.get("admin_reg_names", "???")
        photo_bytes = None

        if update.message.photo:
            photo_file = await update.message.photo[-1].get_file()
            buf = io.BytesIO()
            await photo_file.download_to_memory(buf)
            photo_bytes = buf.getvalue()
        elif update.message.text and update.message.text.strip().lower() in ("скип", "skip", "нет", "-"):
            photo_bytes = None
        else:
            await update.message.reply_text(
                "📸 Пришли фото или напиши `скип`",
                parse_mode="Markdown",
            )
            return

        participants[chat_id] = {
            "names": names,
            "cuisine": None,
            "mission": None,
            "photo": photo_bytes,
            "card": None,
        }
        _save_data()
        context.user_data["admin_state"] = None

        photo_status = "с фото ✨" if photo_bytes else "без фото"
        await update.message.reply_text(
            f"✅ Зарегано: **{names}** ({photo_status}) — это вы, админ!",
            parse_mode="Markdown",
            reply_markup=get_admin_keyboard(),
        )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать админ-панель по команде /admin."""
    if is_admin(update.effective_user.id):
        await update.message.reply_text(
            "👑 Админ-панель:",
            reply_markup=get_admin_keyboard(),
        )


async def results_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /results — показать результаты в беседе (без заданий)."""
    if not draw_done:
        await update.message.reply_text("⏳ Жеребьёвка ещё не проводилась!")
        return

    await update.message.reply_text("🍽 **Кухня народов — распределение:**", parse_mode="Markdown")

    for cid, p in participants.items():
        if not p.get("cuisine"):
            continue
        cuisine_name, flag_emoji, description, country_code = p["cuisine"]
        caption = f"**{p['names']}**\n{flag_emoji} {cuisine_name} кухня\n_{description}_"
        try:
            if p.get("card"):
                await update.message.reply_photo(photo=p["card"], caption=caption, parse_mode="Markdown")
            else:
                await update.message.reply_text(caption, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Ошибка отправки results для {cid}: {e}")
            await update.message.reply_text(caption, parse_mode="Markdown")


def main():
    """Запуск бота."""
    if not BOT_TOKEN:
        print("❌ ОШИБКА: Задай переменную окружения BOT_TOKEN!")
        print("   Локально: BOT_TOKEN=твой_токен python3 bot.py")
        print("   Railway: добавь BOT_TOKEN в Variables")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    # ConversationHandler для регистрации (имена → фото)
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_NAMES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_names),
            ],
            WAITING_PHOTO: [
                MessageHandler(filters.PHOTO, receive_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_photo),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("results", results_command))
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO) & ~filters.COMMAND, admin_input_handler
    ))
    app.add_handler(CallbackQueryHandler(button_handler))

    _load_data()
    print("🎉 Бот запущен! Жду участников...")
    print(f"   Админ ID: {ADMIN_ID if ADMIN_ID else 'будет определён при первом /start'}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
