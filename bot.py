import os
import base64
import anthropic
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ============================================================
# КОНФИГ
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@design_planner")

# ============================================================
# СИСТЕМНЫЙ ПРОМПТ
# ============================================================
SYSTEM_PROMPT = """Ты — контент-менеджер студии дизайна интерьеров Design Planner.

Студия специализируется на жилых интерьерах: квартиры, дома, студии.
Стиль работ: тёплый минимализм, Japandi, скандинавский.
Тон бренда: тёплый, экспертный, вдохновляющий. Без канцелярита.

Когда пишешь пост для Telegram-канала:
- Начинай с цепляющей первой строки (без эмодзи в начале)
- 3–5 предложений, ёмко и по делу
- В конце — 1 вопрос к читателям или призыв
- 3–5 тематических хэштегов в конце
- Эмодзи используй умеренно, по смыслу

Когда генерируешь идеи — давай конкретные темы с коротким описанием."""

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
drafts = {}

# ============================================================
# ГЕНЕРАЦИЯ ТЕКСТА
# ============================================================
async def generate_post(prompt: str) -> str:
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text

# ============================================================
# ГЕНЕРАЦИЯ ПО ФОТО (Vision)
# ============================================================
async def generate_post_from_photo(photo_b64: str) -> str:
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": photo_b64
                    }
                },
                {
                    "type": "text",
                    "text": "Посмотри на это фото интерьера и напиши пост для Telegram-канала студии дизайна. Опиши стиль, материалы, атмосферу — и сделай вдохновляющий пост с хэштегами."
                }
            ]
        }]
    )
    return response.content[0].text

# ============================================================
# КОМАНДЫ
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("✍️ Написать пост", callback_data="menu_post")],
        [InlineKeyboardButton("💡 Идеи на неделю", callback_data="menu_ideas")],
        [InlineKeyboardButton("📸 Пост по фото", callback_data="menu_photo")],
    ]
    await update.message.reply_text(
        "Привет! Я помогаю вести Telegram-канал студии Design Planner.\n\nЧто делаем?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Команды:\n\n"
        "/start — главное меню\n"
        "/post [тема] — написать пост\n"
        "/ideas — идеи контента на неделю\n"
        "/help — это сообщение\n\n"
        "Или просто отправь фото интерьера 📸"
    )

async def post_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args) if context.args else None
    if not topic:
        await update.message.reply_text("Напиши тему поста, например:\n/post Почему минимализм никогда не выйдет из моды")
        return
    await send_draft(update, context, topic)

async def ideas_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("Генерирую идеи... ✨")
    ideas = await generate_post(
        "Придумай 7 идей для постов в Telegram-канал студии дизайна интерьеров. "
        "Каждая идея: название + 1 предложение о чём пост. Пронумеруй."
    )
    await msg.edit_text(f"💡 Идеи на неделю:\n\n{ideas}")

# ============================================================
# ЧЕРНОВИК
# ============================================================
async def send_draft(update, context, topic: str):
    obj = update.message or update.callback_query.message
    msg = await obj.reply_text("Пишу пост... ✍️")
    draft = await generate_post(f"Напиши пост для Telegram-канала студии дизайна интерьеров на тему: {topic}")
    user_id = update.effective_user.id
    drafts[user_id] = {"text": draft, "topic": topic}
    keyboard = [
        [
            InlineKeyboardButton("✅ Опубликовать", callback_data="draft_publish"),
            InlineKeyboardButton("✏️ Переделать", callback_data="draft_redo"),
        ],
        [InlineKeyboardButton("❌ Отклонить", callback_data="draft_cancel")]
    ]
    await msg.edit_text(
        f"📝 Черновик:\n\n{draft}\n\n─────────────────\nЧто делаем с постом?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ============================================================
# ОБРАБОТКА ФОТО — реальный анализ через Claude Vision
# ============================================================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("Анализирую фото... 🔍")
    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        photo_bytes = await file.download_as_bytearray()
        photo_b64 = base64.b64encode(photo_bytes).decode("utf-8")

        draft = await generate_post_from_photo(photo_b64)
        user_id = update.effective_user.id
        drafts[user_id] = {"text": draft, "topic": "пост по фото"}

        keyboard = [
            [
                InlineKeyboardButton("✅ Опубликовать", callback_data="draft_publish"),
                InlineKeyboardButton("✏️ Переделать", callback_data="draft_redo"),
            ],
            [InlineKeyboardButton("❌ Отклонить", callback_data="draft_cancel")]
        ]
        await msg.edit_text(
            f"📝 Черновик:\n\n{draft}\n\n─────────────────\nЧто делаем с постом?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        await msg.edit_text(f"Не удалось обработать фото. Попробуй ещё раз.\n\nОшибка: {e}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_draft(update, context, update.message.text)

# ============================================================
# КНОПКИ
# ============================================================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data

    if data == "menu_post":
        await query.message.reply_text("Напиши тему поста — и я его сгенерирую:")

    elif data == "menu_ideas":
        msg = await query.message.reply_text("Генерирую идеи... ✨")
        ideas = await generate_post(
            "Придумай 7 идей для постов в Telegram-канал студии дизайна интерьеров. "
            "Каждая идея: название + 1 предложение о чём пост. Пронумеруй."
        )
        await msg.edit_text(f"💡 Идеи на неделю:\n\n{ideas}")

    elif data == "menu_photo":
        await query.message.reply_text("Отправь фото интерьера прямо сюда — проанализирую и напишу пост 📸")

    elif data == "draft_publish":
        draft = drafts.get(user_id)
        if not draft:
            await query.message.reply_text("Черновик не найден, попробуй снова.")
            return
        try:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=draft["text"])
            await query.message.edit_text("✅ Опубликовано в канал!")
        except Exception as e:
            await query.message.edit_text(
                f"⚠️ Не удалось опубликовать. Убедись что бот добавлен в канал как администратор.\n\nОшибка: {e}"
            )

    elif data == "draft_redo":
        draft = drafts.get(user_id)
        if draft:
            await send_draft(update, context, draft["topic"])

    elif data == "draft_cancel":
        drafts.pop(user_id, None)
        await query.message.edit_text("❌ Пост отклонён. Напиши новую тему когда будешь готов.")

# ============================================================
# ЗАПУСК
# ============================================================
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("post", post_cmd))
    app.add_handler(CommandHandler("ideas", ideas_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Бот запущен! ✅")
    app.run_polling()

if __name__ == "__main__":
    main()

