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

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)

llm = ChatGroq(
    temperature=0.1, 
    groq_api_key=GROQ_API_KEY,
    model_name="llama-3.1-8b-instant"
)

# =====================================================================
# БАЗА ДАННЫХ
# =====================================================================
def init_db():
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
    conn = sqlite3.connect("bot_memory.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO history (chat_id, role, content) VALUES (?, ?, ?)", (chat_id, role, content))
    conn.commit()
    conn.close()

def get_chat_history(chat_id, limit=2):
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

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("🌤 Погода"), types.KeyboardButton("🧮 Калькулятор"))
    markup.add(types.KeyboardButton("🔍 Поиск знаний"))
    markup.add(types.KeyboardButton("💵 Курс валют"), types.KeyboardButton("⏰ Напоминание"))
    return markup

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "КУРСОВАЯ РАБОТА\n"
        "Тема: «Создание LLM агента с автономным вызовом функций»\n\n"
        "Разработчик: студент 1-МОК, гр. 31ИС\n"
        "Щучкин Иван Алексеевич\n\n"
        "Бот переведен на детерминированный CLI-интерфейс обработки команд."
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=get_main_keyboard())

def send_delayed_reminder(chat_id, delay_seconds, text):
    time.sleep(delay_seconds)
    try:
        bot.send_message(chat_id, f"⏰ НАПОМИНАНИЕ: {text}")
    except Exception as e:
        print(f"Ошибка напоминания: {e}")

# =====================================================================
# ЯДРО АГЕНТА (МАРШРУТИЗАЦИЯ)
# =====================================================================
@bot.message_handler(func=lambda message: True)
def handle_agent_message(message):
    try:
        chat_id = message.chat.id
        user_text = message.text
        
        if user_text == "🌤 Погода":
            bot.send_message(chat_id, "Напишите запрос, например: Погода в Москве")
            return
        elif user_text == "🧮 Калькулятор":
            bot.send_message(chat_id, "Отправьте пример, например: Сколько будет 7274*6373")
            return
        elif user_text == "🔍 Поиск знаний":
            bot.send_message(chat_id, "Что найти? Например: Сколько лет Дональду Трампу")
            return
        elif user_text == "💵 Курс валют":
            bot.send_message(chat_id, "Например: Переведи 150 долларов в рубли")
            return
        elif user_text == "⏰ Напоминание":
            bot.send_message(chat_id, "Например: Напомни через 10 секунд проверить код")
            return

        save_message(chat_id, "user", user_text)
        
        if any(c.isdigit() for c in user_text) and not any(word in user_text.lower() for word in ["лет", "год", "доллар", "евро", "рубл"]):
            allowed_math = set("0123456789+-*/.() ")

            if not set(user_text).issubset(allowed_math):
                bot_answer = "Результат вычислений: Ошибка: выражение содержит недопустимые символы (например, '?') и не может быть вычислено."
                save_message(chat_id, "assistant", bot_answer)
                bot.reply_to(message, bot_answer, reply_markup=get_main_keyboard())
                return
            else:
                print(f"[Перехват чистой математики]: {user_text}")
                bot_answer = f"Результат вычислений: {calculate(user_text)}"
                save_message(chat_id, "assistant", bot_answer)
                bot.reply_to(message, bot_answer, reply_markup=get_main_keyboard())
                return
        
        system_instruction = (
            "Ты — ИИ-рулевой для вызова программных функций. Отвечай кратко.\n"
            "ВНИМАНИЕ: Текущий год — 2026. Если тебя спрашивают про возраст людей или объектов, "
            "тебе ОБЯЗАТЕЛЬНО нужно сначала узнать их дату рождения или основания через поиск В Википедии!\n\n"
            "Если пользователю нужно что-то узнать, найти, посчитать или проверить погоду, ты "
            "ОБЯЗАН выдать СТРОГО ОДНУ команду из списка ниже и БОЛЬШЕ НИЧЕГО не писать:\n"
            "1. RUN_CALC:выражение (Пример: RUN_CALC:2+2)\n"
            "2. RUN_WEATHER:город (Пример: RUN_WEATHER:Москва)\n"
            "3. RUN_SEARCH:запрос (Пример: RUN_SEARCH:Дональд Трамп)\n"
            "4. RUN_CURRENCY:сумма:из_валюты:в_валюту (Пример: RUN_CURRENCY:100:USD:RUB)\n\n"
            "Если это простой диалог (приветствие, спасибо, пустой или абстрактный вопрос), "
            "просто ответь текстом на русском языке в 1 предложение без команд."
        )

        if "напомни через" in user_text.lower():
            try:
                words = user_text.lower().split()
                seconds = int(words[2])
                reminder_text = " ".join(words[4:])
                threading.Thread(target=send_delayed_reminder, args=(chat_id, seconds, reminder_text), daemon=True).start()
                bot.reply_to(message, f"Задача принята. Напоминание сработает через {seconds} сек.")
                return
            except:
                pass

        messages = [SystemMessage(content=system_instruction)]
        messages.extend(get_chat_history(chat_id, limit=2))
        messages.append(HumanMessage(content=user_text))

        ai_response = llm.invoke(messages).content.strip()
        print(f"[Решение модели]: {ai_response}")

        bot_answer = ""
        
        if "RUN_CALC:" in ai_response:
            expr = ai_response.split("RUN_CALC:")[1].strip()
            bot_answer = f"Результат вычислений: {calculate(expr)}"
            
        elif "RUN_WEATHER:" in ai_response:
            city = ai_response.split("RUN_WEATHER:")[1].strip()
            bot_answer = get_weather(city)
            
        elif "RUN_SEARCH:" in ai_response:
            query = ai_response.split("RUN_SEARCH:")[1].strip()
            search_res = google_search(query)
            
            summary_prompt = [
                SystemMessage(content="Текущий год — 2026. На основе предоставленных фактов из Википедии напиши ОДНО краткое итоговое предложение с ответом на вопрос пользователя."),
                HumanMessage(content=f"Вопрос пользователя: {user_text}\n\nФакты из Википедии:\n{search_res}")
            ]
            bot_answer = llm.invoke(summary_prompt).content.strip()
            
        elif "RUN_CURRENCY:" in ai_response:
            parts = ai_response.split("RUN_CURRENCY:")[1].strip().split(":")
            if len(parts) == 3:
                bot_answer = convert_currency(parts[0], parts[1], parts[2])
            else:
                bot_answer = "Неверный формат команды конвертации валют."
        else:
            bot_answer = ai_response

        if not bot_answer:
            bot_answer = "Извините, запрос не удалось обработать. Попробуйте еще раз."

        save_message(chat_id, "assistant", bot_answer)
        bot.reply_to(message, bot_answer, reply_markup=get_main_keyboard())
            
    except Exception as e:
        print(f"[Системная ошибка ядра]: {e}")
        bot.reply_to(message, "Ошибка обработки. Пожалуйста, перефразируйте ваш запрос.", reply_markup=get_main_keyboard())

# =====================================================================
# HEALTH SERVER И ЗАПУСК
# =====================================================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("OK".encode("utf-8"))
    def log_message(self, format, *args): return

def run_health_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=run_health_server, daemon=True).start()
    bot.infinity_polling()