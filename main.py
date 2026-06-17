import telebot
import sqlite3
import threading
import time
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv
from telebot import types
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from tools import calculate, get_weather, google_search, convert_currency

def calc(expr): return calculate(expr)
def weather(city): return get_weather(city)
def search(query): return google_search(query)
def currency(info): return convert_currency(info)

# =====================================================================
# 1. КОНФИГУРАЦИЯ И НАСТРОЙКА АГЕНТА
# =====================================================================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

llm = ChatGroq(
    temperature=0.2, 
    groq_api_key=GROQ_API_KEY,
    model_name="llama-3.1-8b-instant"
)

# =====================================================================
# 2. БЛОК РАБОТЫ С БАЗОЙ ДАННЫХ (КОНТЕКСТНАЯ ПАМЯТЬ)
# =====================================================================
def init_db():
    """Создает базу данных и таблицу истории, если они еще не существуют."""
    conn = sqlite3.connect("bot_memory.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            role TEXT,
            content TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_message(chat_id, role, content):
    """Сохраняет реплику в базу данных."""
    conn = sqlite3.connect("bot_memory.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO history (chat_id, role, content) VALUES (?, ?, ?)", (chat_id, role, content))
    conn.commit()
    conn.close()

def get_chat_history(chat_id, limit=6):
    """Извлекает последние сообщения строго для конкретного chat_id."""
    conn = sqlite3.connect("bot_memory.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM history WHERE chat_id = ? ORDER BY id DESC LIMIT ?", (chat_id, limit))
    rows = cursor.fetchall()
    conn.close()
    rows.reverse()
    
    messages = []
    for role, content in rows:
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    return messages

init_db()

# =====================================================================
# 3. ПОЛЬЗОВАТЕЛЬСКИЙ ИНТЕРФЕЙС И ОФОРМЛЕНИЕ
# =====================================================================
def get_main_keyboard():
    """Создает адаптивную экранную клавиатуру с кнопками-подсказками."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_weather = types.KeyboardButton("🌤 Погода")
    btn_calc = types.KeyboardButton("🧮 Калькулятор")
    btn_search = types.KeyboardButton("🔍 Поиск знаний")
    btn_currency = types.KeyboardButton("💵 Курс валют")
    btn_timer = types.KeyboardButton("⏰ Напоминание")
    
    markup.add(btn_weather, btn_calc)
    markup.add(btn_search)
    markup.add(btn_currency, btn_timer)
    return markup

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Выводит официальную именную карточку курсовой работы."""
    welcome_text = (
        "——————————————————————\n"
        "**КУРСОВАЯ РАБОТА**\n"
        "Тема: «Создание LLM агента, который умеет сам вызывать функции: калькулятор, запрос погоды через API, поиск в интернете.»\n"
        "——————————————————————\n\n"
        "🤖 **Разработчик:** студент колледжа 1-МОК, группы 31ИС\n"
        "👉 **Щучкин Иван Алексеевич**\n\n"
        "🤖 **Статус:** Интеллектуальный ИИ-Агент успешно запущен и готов к демонстрации.\n\n"
        "🧠 *Краткая справка:* Я функционирую на базе большой языковой модели **Llama 3.1**, "
        "обладаю изолированной контекстной памятью SQLite и умею автономно вызывать внешние программные модули.\n\n"
        "✨ **Доступный инструментарий:**\n"
        "• 🌤 __Модуль метеоданных__ (wttr.in API)\n"
        "• 🧮 __Инженерный калькулятор__ (динамический расчет)\n"
        "• 🔍 __Глобальный поиск знаний__ (Wikipedia API)\n"
        "• 💵 __Финансовый конвертер__ (API Центробанка РФ)\n"
        "• ⏰ __Асинхронный планировщик задач__ (Фоновые потоки)\n\n"
        "ℹ️ _Вы можете отправлять комплексные запросы на естественном языке (например, попросить посчитать пример и сразу напомнить о задаче) или использовать интерактивное меню ниже._ 👇"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=get_main_keyboard())

# =====================================================================
# 4. АСИНХРОННЫЙ МОДУЛЬ НАПОМИНАНИЙ
# =====================================================================
def send_delayed_reminder(chat_id, delay_seconds, text):
    """Спит указанное время в отдельном потоке и отправляет пуш в Telegram."""
    time.sleep(delay_seconds)
    try:
        reminder_box = (
            "🔔 ———————————————————— 🔔\n"
            "🌟 **ВАЖНОЕ НАПОМИНАНИЕ!** 🌟\n"
            "——————————————————————\n"
            f"📌 *Вы просили не забыть:*\n"
            f"» `{text}`\n"
            "——————————————————————"
        )
        bot.send_message(chat_id, reminder_box)
    except Exception as e:
        print(f"Ошибка фоновой отправки напоминания: {e}")

# =====================================================================
# 5. МАРШРУТИЗАЦИЯ И ОБРАБОТКА ЗАПРОСОВ (ЯДРО АГЕНТА)
# =====================================================================

@bot.message_handler(func=lambda message: True)
def handle_agent_message(message):
    try:
        chat_id = message.chat.id
        user_text = message.text
        
        if user_text == "🌤 Погода":
            bot.send_message(chat_id, "📍 Напишите, какой город вас интересует? Например: `Какая сейчас погода в Питере?`")
            return
        elif user_text == "🧮 Калькулятор":
            bot.send_message(chat_id, "🔢 Отправьте математический пример. Например: `Сколько будет 124 умножить на 45?`")
            return
        elif user_text == "🔍 Поиск знаний":
            bot.send_message(chat_id, "📖 О чем вы хотите узнать? Например: `Кто такой Илон Маск?`")
            return
        elif user_text == "💵 Курс валют":
            bot.send_message(chat_id, "💰 Напишите запрос обмена. Например: `Переведи 150 долларов в рубли`")
            return
        elif user_text == "⏰ Напоминание":
            bot.send_message(chat_id, "⏱ Напишите временную задачу. Например: `Напомни через 15 секунд проверить код`")
            return

        print(f"\n[Запрос пользователя]: {user_text}")
        save_message(chat_id, "user", user_text)
        
        system_instruction = """Ты — ИИ-агент курсовой работы студента Щучкина. Ты управляешь инструментами.
        Ты общаешься вежливо, структурировано и строго на русском языке.
        Твои ответы должны быть лаконичными и информативными.
        Если ты используешь инструменты, выводи только суть.
        Никаких долгих вступлений, никакой воды.
        Если ответа нет, ответь кратко и по делу.
        Когда ты формируешь обычный текстовый ответ (без вызова инструментов), всегда разбивай его на логические абзацы, используй списки, маркеры и выделяй ключевые слова жирным шрифтом (**слово**).
        
        Сначала проанализируй запрос на логические подвохи. Если это абсурд/загадка (яблоки на дубе, ножки у стола), ответь сам красивым развернутым текстом, объяснив подвох и иронию.
        Если подвоха нет, строго выбери инструменты (каждый инструмент пиши строго с новой строки):
        
        1. CALC:выражение -> математика (пример: CALC:124*45)
        2. WEATHER:город -> погода (пример: WEATHER:Токио)
        3. SEARCH:запрос -> факты из базы знаний (пример: SEARCH:история Дубая)
        4. CURRENCY:сумма:из_какой:в_какую -> конвертация валют (USD, EUR, RUB, CNY, KZT) (пример: CURRENCY:100:USD:RUB)
        5. TIMER:секунды:текст -> напоминание (переведи время строго в секунды). (пример: TIMER:60:выключить чайник)
        
        Если инструменты не нужны, просто напиши свой красивый ответ."""

        messages = [SystemMessage(content=system_instruction)]
        messages.extend(get_chat_history(chat_id, limit=6))

        ai_response = llm.invoke(messages).content.strip()
        print(f"[Решение ИИ]:\n{ai_response}")

        lines = [line.strip() for line in ai_response.split('\n') if line.strip()]
        
        final_replies = []
        is_tool_used = False

        for action in lines:
            if action.startswith("CALC:"):
                is_tool_used = True
                expr = action.replace("CALC:", "").strip()
                res = calculate(expr)
                final_replies.append(f"Вычисление: {expr} = {res}")
                
            elif action.startswith("WEATHER:"):
                is_tool_used = True
                city = action.replace("WEATHER:", "").strip()
                res = get_weather(city)
                final_replies.append(f"Погода в {city.capitalize()}: {res}")
                
            elif action.startswith("SEARCH:"):
                is_tool_used = True
                query = action.replace("SEARCH:", "").strip()
                search_data = google_search(query)
                
                if "Ошибка" not in search_data and "не дал результатов" not in search_data:
                    safe_data = search_data[:1000]
                    
                    summary_prompt = [
                        SystemMessage(content="Ты — полезный ассистент. Оформи факты в красивый, структурированный текстовый блок на русском языке. Пиши только суть, без лишней воды. Если пользователь присылает математический пример — реши его. ЕСЛИ пользователь присылает текст, который не является математическим примером или запросом к твоим инструментам (например, случайный набор символов или знак вопроса между числами) — НЕ ПЫТАЙСЯ считать. Вежливо ответь c извинением. Никогда не генерируй слишком длинные ответы, чтобы не вызывать ошибки Telegram."),
                        HumanMessage(content=f"Данные для выжимки:\n{safe_data}")
                    ]
                    
                    try:
                        final_answer = llm.invoke(summary_prompt).content.strip()
                    except Exception as api_err:
                        print(f"[Защита от ошибки 401 / лимитов]: {api_err}")
                        final_answer = "⚠️ Поисковые данные оказались слишком объемными для бесплатного тарифа Groq API. Попробуйте сузить поисковый запрос."
                else:
                    final_answer = "К сожалению, в глобальной базе знаний детальной информации не найдено."
                
                final_replies.append(f"🧱 **[ 🔍 Анализ глобальной сети ]**\n🎯 *Запрос:* _{query}_\n\n{final_answer}")

            elif action.startswith("CURRENCY:"):
                is_tool_used = True
                parts = action.replace("CURRENCY:", "").split(":")
                if len(parts) == 3:
                    try:
                        amount = float(parts[0])
                        from_curr = parts[1].strip().upper()
                        to_curr = parts[2].strip().upper()
                        result = convert_currency(amount, from_curr, to_curr)
                        final_replies.append(f"🧱 **[ 💵 Финансовый конвертер ]**\n🔄 *Конвертация:* `{amount} {from_curr} ➔ {to_curr}`\n📈 *{result}*")
                    except:
                        final_replies.append("🧱 **[ 💵 Финансовый конвертер ]**\n⚠️ Ошибка формата числовых параметров.")
                else:
                    final_replies.append("🧱 **[ 💵 Финансовый конвертер ]**\n⚠️ Неверная структура команды.")

            elif action.startswith("TIMER:"):
                is_tool_used = True
                parts = action.replace("TIMER:", "").split(":", 1)
                if len(parts) == 2:
                    try:
                        seconds = int(parts[0])
                        reminder_text = parts[1].strip()
                        
                        t = threading.Thread(target=send_delayed_reminder, args=(chat_id, seconds, reminder_text))
                        t.start()
                        
                        time_display = f"{seconds} сек." if seconds < 60 else f"{round(seconds/60, 1)} мин."
                        final_replies.append(f"🧱 **[ ⏰ Модуль планирования ]**\n📥 *Задача принята!* Создан фоновый поток.\n🔔 Сигнал сработает через: `{time_display}`")
                    except Exception as e:
                        final_replies.append(f"🧱 **[ ⏰ Модуль планирования ]**\n⚠️ Ошибка создания задачи: {e}")

        if is_tool_used:
            bot_answer = "\n\n" + "\n\n".join(final_replies)
        else:
            bot_answer = ai_response

        save_message(chat_id, "assistant", bot_answer)
        try:
            bot.reply_to(message, bot_answer, reply_markup=get_main_keyboard())
        except Exception as e:
            print(f"[Ошибка отправки]: {e}")
            bot.reply_to(message, "Ошибка формата ответа.", reply_markup=get_main_keyboard())
            
    except Exception as e:
        print(f"[Системная ошибка ядра]: {e}")
        bot.reply_to(message, f"💥 Произошла системная ошибка в работе ядра агента.", reply_markup=get_main_keyboard())

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Бот работает!".encode("utf-8"))
    def log_message(self, format, *args):
        return

def run_health_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"[HealthCheck]: Веб-сервер запущен на порту {port}")
    server.serve_forever()

if __name__ == "__main__":
    web_thread = threading.Thread(target=run_health_server, daemon=True)
    web_thread.start()  



# =====================================================================
# 6. ЗАПУСК СЕРВЕРА
# =====================================================================
print("=======================================================")
print(" КУРСОВАЯ РАБОТА СТУДЕНТА ЩУЧКИНА И.А. (ГР. 32)")
print(" ИИ-БОТ УСПЕШНО ЗАПУЩЕН И ГОТОВ К РАБОТЕ")
print("=======================================================")

bot.infinity_polling()