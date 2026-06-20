import asyncio
import os
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

# --- НАСТРОЙКИ ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("⚠️ Не найден BOT_TOKEN! Проверь файл .env")

MSK = ZoneInfo("Europe/Moscow")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)
scheduler = AsyncIOScheduler(timezone=MSK)

# --- ХРАНИЛИЩЕ ПРОГРЕССА (в памяти, для теста) ---
users_progress = {}

class QuizStates(StatesGroup):
    PROCESS = State()

# --- ДАННЫЕ КВИЗА ---
QUESTIONS = [
    {
        "title": "🏃‍♂️ Физическая готовность",
        "text": "Как ты оцениваешь свой текущий уровень энергии, здоровье и способность выдерживать новые нагрузки?",
        "scale": "🔹 1 — Сильная усталость, энергии почти нет\n🔹 2 — Часто устаю, долго восстанавливаюсь\n🔹 3 — Нормально, но бывают спады\n🔹 4 — Бодрость, запас энергии есть\n🔹 5 — Отличная форма, много сил"
    },
    {
        "title": "💡 Эмоциональный настрой",
        "text": "Насколько ты мотивирован(а) и в каком психологическом состоянии находишься?",
        "scale": "🔹 1 — Стресс, апатия, сопротивление\n🔹 2 — Мотивация есть, но мешает тревога\n🔹 3 — Ровный фон, без ярко выраженных эмоций\n🔹 4 — Хороший настрой, понимаю «зачем»\n🔹 5 — Вдохновение, готов(а) действовать"
    },
    {
        "title": "📚 Предыдущий опыт",
        "text": "Был ли у тебя успешный опыт формирования похожих привычек?",
        "scale": "🔹 1 — Никогда не пробовал(а)\n🔹 2 — Пробовал(а), но часто срывался(ась)\n🔹 3 — Были успехи, но давно\n🔹 4 — Успешно внедрял(а) похожие привычки\n🔹 5 — Делал(а) многократно, процесс отточен"
    },
    {
        "title": "🤝 Поддержка окружения",
        "text": "Как твоё окружение относится к твоим новым целям?",
        "scale": "🔹 1 — Критикуют или безразличны\n🔹 2 — Не мешают, но и не помогают\n🔹 3 — Понимают, но редко включаются\n🔹 4 — Активно поддерживают\n🔹 5 — Есть наставник/партнёр/группа"
    },
    {
        "title": "🛠 Доступность ресурсов",
        "text": "Есть ли у тебя время, место и условия для регулярного выполнения действия?",
        "scale": "🔹 1 — Нет времени/условий, всё придётся искать\n🔹 2 — Условия сильно ограничены\n🔹 3 — Базовое есть, но бывают помехи\n🔹 4 — Большинство ресурсов под рукой\n🔹 5 — Идеальные условия уже готовы"
    }
]

def get_result_text(score: int) -> str:
    if score >= 20: days, tip = "14–33 дня", "Отличный фундамент! Сохрани темп первые 2 недели."
    elif score >= 15: days, tip = "33–52 дня", "Хороший старт. Не бросай после первого месяца!"
    elif score >= 10: days, tip = "52–71 день", "Средний темп. Разбей цель на микро-шаги."
    else: days, tip = "71–90+ дней", "Начни с 5 минут в день. Регулярность важнее скорости."
    
    return (
        f"🎉 Результат готов!\n\n"
        f"📊 Твой балл: {score}/25\n"
        f"⏱️ Ожидаемое время: {days}\n\n"
        f"💡 Совет: {tip}\n\n"
        f"🔬 Методика Г.А. Черноваловой имеет точность ~95%. Это прогноз, а не приговор. Регулярность сделает своё дело!"
    )

# --- ДАННЫЕ 3-ДНЕВНОГО ИНТЕНСИВА ---
TRIAL_DAYS = {
    1: {
        "text": (
            "🌞 Доброе утро! Сегодня День 1 твоего пути к привычке.\n\n"
            "💪 Тренировка (5–7 мин):\n"
            "• 10 приседаний\n• 5 отжиманий (можно с колен)\n• 30 сек планка\n"
            "🔁 Повтори 2 раза. Отдых между подходами — 40 сек.\n\n"
            "🥗 Питание:\n"
            "• Стакан тёплой воды сразу после пробуждения.\n"
            "• Добавь к обеду или ужину порцию овощей.\n\n"
            "📌 Почему это работает: Мы не перегружаем организм, а учим его «включаться» в режим."
        ),
        "btn": "✅ День 1 выполнен"
    },
    2: {
        "text": (
            "🚀 Доброе утро! День 2. Ты уже преодолел начало!\n\n"
            "💪 Тренировка (7–9 мин):\n"
            "• 15 приседаний\n• 8 отжиманий\n• 40 сек планка\n"
            "• + 5 берпи между подходами\n🔁 Повтори 2 раза.\n\n"
            "🥗 Питание:\n"
            "• Замени 1 сладкий перекус на воду/чай.\n"
            "• Добавь белок на завтрак (яйцо, творог, йогурт).\n\n"
            "📌 Фишка дня: Белок + клетчатка = сытость без срывов."
        ),
        "btn": "✅ День 2 выполнен"
    },
    3: {
        "text": (
            "🔥 Доброе утро! День 3 — финиш пробного этапа.\n\n"
            "💪 Тренировка (10–12 мин):\n"
            "• 20 приседаний\n• 10 отжиманий\n• 45 сек планка\n"
            "• + 8 берпи между подходами\n• + 15 сек боковой планки на каждую сторону\n🔁 Повтори 3 раза.\n\n"
            "🥗 Питание:\n"
            "• Запиши план завтрака в заметки.\n"
            "• Добавь «полезные жиры» (орехи, авокадо, масло).\n\n"
            "📌 Что происходит в мозге: Нейронные связи укрепляются. Дальше привычка будет требовать меньше силы воли."
        ),
        "btn": "✅ День 3 выполнен"
    }
}

PRAISE = {
    1: "🌟 Отлично! Первый шаг — самый важный. Ты уже запустил процесс. Завтра добавим чуть больше динамики. Отдыхай и восстанавливайся. До завтра! Ты большой молодец! 💪",
    2: "🔥 Супер! День 2 закрыт. Твоё тело адаптируется, а мозг привыкает к регулярности. Завтра будет финальный рывок пробного этапа. До завтра! 🚀",
    3: "🎉 Вау, ты это сделал(а)! 3 дня позади — это уже маленькая победа. Сейчас я пришлю итоги пробного периода. Горжусь твоим упорством! Ты большой молодец! 🏆"
}

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_next_9am_msk():
    now = datetime.now(MSK)
    target = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return target

def schedule_trial_day(chat_id: int, day: int):
    run_time = get_next_9am_msk()
    job = scheduler.add_job(
        send_trial_day, 
        trigger=DateTrigger(run_date=run_time), 
        args=[chat_id, day], 
        id=f"trial_{chat_id}"
    )
    users_progress[chat_id]["job_id"] = job.id
    logging.info(f"📅 Задание День {day} для {chat_id} запланировано на {run_time.strftime('%H:%M %d.%m.%Y')} МСК")

async def send_trial_day(chat_id: int, day: int):
    if day not in TRIAL_DAYS or chat_id not in users_progress:
        return
    day_data = TRIAL_DAYS[day]
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=day_data["btn"], callback_data=f"done_day_{day}")]])
    try:
        await bot.send_message(chat_id, day_data["text"], reply_markup=kb)
        logging.info(f"📩 День {day} отправлен пользователю {chat_id}")
    except Exception as e:
        logging.error(f"❌ Ошибка отправки сообщения {chat_id}: {e}")

# --- ХЕНДЛЕРЫ ---
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    if message.chat.id in users_progress:
        del users_progress[message.chat.id]
    
    text = (
       "👋 Привет! Я бот молодого проекта ЭЙМ-8 и помогу плавно погрузиться в мир ЗОЖ!.\n\n"
        "Для начала мы предлагаем пройти корткий опрос.\n\n"
        "📊 Методика основана на научном исследовании Г.А. Черноваловой. \n\n"
        "Тест учитывает 5 ключевых факторов: физиологию, эмоции, прошлый опыт, окружение и ресурсы.\n\n"
        "✅ Точность прогноза  — около 95%. "
        "Ответь честно на 5 коротких вопросов, и я рассчитаю, сколько дней тебе потребуется для внедрения привычки.\n\n"
        "Готов(а) начать?"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Начать расчёт", callback_data="start_quiz")]])
    await message.answer(text, reply_markup=kb)

@router.callback_query(F.data == "start_quiz")
async def start_quiz(callback: CallbackQuery, state: FSMContext):
    await state.set_state(QuizStates.PROCESS)
    await state.update_data(answers=[], current_q=0, chat_id=callback.message.chat.id)
    await show_question(callback, state, 0)

async def show_question(callback: CallbackQuery, state: FSMContext, q_index: int):
    q = QUESTIONS[q_index]
    text = f"▫️ Вопрос {q_index + 1} из 5\n\n{q['title']}\n\n{q['text']}\n\n📏 Шкала:\n{q['scale']}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=str(i), callback_data=f"score_{i}") for i in range(1, 6)]])
    await callback.message.answer(text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("score_"), QuizStates.PROCESS)
async def handle_score(callback: CallbackQuery, state: FSMContext):
    score = int(callback.data.split("_")[1])
    data = await state.get_data()
    answers = data.get("answers", [])
    answers.append(score)
    current_q = data.get("current_q", 0)

    if current_q < 4:
        await state.update_data(answers=answers, current_q=current_q + 1)
        await show_question(callback, state, current_q + 1)
    else:
        total = sum(answers)
        users_progress[callback.message.chat.id] = {"quiz_score": total, "trial_day": 1, "job_id": None}
        await callback.message.answer(get_result_text(total))
        
        transition = (
            "✅ Отлично! Фундаментальная часть позади, и теперь ты знаешь, сколько времени потребуется для формирования привычки.\n\n"
            "🌱 С завтрашнего дня мы поможем тебе в этой задаче: запускаем бесплатный 3-дневный пробный период.\n"
            "В рамках него каждое утро мы будем присылать короткие, посильные задания по тренировкам и питанию. Они будут постепенно усложняться, но останутся интересными и выполнимыми.\n\n"
            "🕘 Первое задание придёт завтра в 09:00 по МСК. Мы верим, что ты справишься!\n\n"
            "💪 До завтра! Ты уже на верном пути."
        )
        await callback.message.answer(transition)
        
        schedule_trial_day(callback.message.chat.id, 1)
        await callback.answer()

@router.callback_query(F.data.startswith("done_day_"))
async def handle_trial_done(callback: CallbackQuery):
    day = int(callback.data.split("_")[-1])
    chat_id = callback.message.chat.id
    
    if chat_id not in users_progress or users_progress[chat_id]["trial_day"] != day:
        await callback.answer("⏳ Задание ещё не активно или уже выполнено.", show_alert=True)
        return

    await callback.message.answer(PRAISE.get(day, "👍 Отлично! Так держать!"))
    
    if day < 3:
        next_day = day + 1
        users_progress[chat_id]["trial_day"] = next_day
        if users_progress[chat_id].get("job_id"):
            scheduler.remove_job(users_progress[chat_id]["job_id"])
        schedule_trial_day(chat_id, next_day)
        await callback.answer()
    else:
        final = (
            "🎯 Пробный период завершён!\n\n"
            "Ты успешно прошёл 3-дневный интенсив. Исследования показывают, что после такой «разминки» скорость формирования привычки увеличивается на 30–40%.\n\n"
            "🛠 Прямо сейчас наша команда разрабатывает полную версию бота:\n"
            "✔ Персональные программы под твой график\n"
            "✔ Адаптация нагрузки и питания\n"
            "✔ Треки прогресса и умные напоминания\n"
            "✔ Поддержка куратора\n\n"
            "🔔 Хочешь быть в числе первых, кто получит доступ, и пройти полный курс со скидкой? Оставь заявку:\n"
            "👉 [📩 Хочу в полную версию](https://t.me/YOUR_MANAGER_USERNAME)"
        )
        await callback.message.answer(final, disable_web_page_preview=True)
        if users_progress[chat_id].get("job_id"):
            scheduler.remove_job(users_progress[chat_id]["job_id"])
        del users_progress[chat_id]
        await callback.answer()

async def main():
    scheduler.start()
    logging.info("🤖 Бот запущен. Ожидание сообщений...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())