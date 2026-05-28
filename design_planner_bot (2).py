import os
import asyncio
import anthropic
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ============================================================
# КОНФИГ — вставь свои токены
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@design_planner")

# ============================================================
# СИСТЕМНЫЙ ПРОМПТ — голос студии
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

# Временное хранилище черновиков (в памяти)
drafts = {}

# ============================================================
# ГЕНЕРАЦИЯ ЧЕРЕЗ CLAUDE
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
# КОМАНДЫ
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("✍️ Написать пост", callback_data="menu_post")],
        [InlineKeyboardButton("💡 Идеи на неделю", callback_data="menu_ideas")],
        [InlineKeyboardButton("📸 Пост по фото", callback_data="menu_photo")],
    ]
    await update.message.reply_text(
        "Привет! Я помогаю вести Telegram-канал студии Design Planner.\n\n"
        "Что делаем?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Команды:\n\n"
        "/start — главное меню\n"
        "/post [тема] — написать пост\n"
        "/ideas — идеи контента на неделю\n"
        "/help — это сообщение"
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
# ГЕНЕРАЦИЯ И ОТПРАВКА ЧЕРНОВИКА
# ============================================================
async def send_draft(update, context, topic: str, photo=None):
    obj = update.message or update.callback_query.message
    msg = await obj.reply_text("Пишу пост... ✍️")

    prompt = f"Напиши пост для Telegram-канала студии дизайна интерьеров на тему: {topic}"
    draft = await generate_post(prompt)

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
# ОБРАБОТКА ФОТО
# ============================================================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Фото получил! 📸 Опиши кратко что на нём — стиль, комната, детали — "
        "и я напишу пост."
    )
    context.user_data["awaiting_photo_desc"] = True

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if context.user_data.get("awaiting_photo_desc"):
        context.user_data["awaiting_photo_desc"] = False
        await send_draft(update, context, f"пост к фото интерьера: {text}")
        return

    # Свободный текст — генерируем пост
    await send_draft(update, context, text)

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
        await query.message.reply_text("Отправь фото интерьера — напишу пост к нему 📸")

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
