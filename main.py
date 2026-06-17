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
from langchain_core.tools import tool

# Импортируем функции из твоих tools.py
from tools import calculate, get_weather, google_search, convert_currency

# =====================================================================
# 1. КОНФИГУРАЦИЯ И ОПРЕДЕЛЕНИЕ ИНСТРУМЕНТОВ ДЛЯ КУРСОВОЙ
# =====================================================================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)

@tool
def tool_calculate(expression: str) -> str:
    """Математический калькулятор. Принимает чистую строку с примером, например: '7274*6373' или '124+45'."""
    return calculate(expression)

@tool
def tool_get_weather(city: str) -> str:
    """Запрос текущей погоды для указанного города на русском языке."""
    return get_weather(city)

@tool
def tool_google_search(query: str) -> str:
    """Поиск фактов в глобальной сети или Википедии по текстовому запросу."""
    return google_search(query)

@tool
def tool_convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """Конвертер валют по курсу ЦБ РФ. Требует количество, исходную валюту и целевую (например: 100, 'USD', 'RUB')."""
    return convert_currency(amount, from_currency, to_currency)

tools_list = [tool_calculate, tool_get_weather, tool_google_search, tool_convert_currency]
llm = ChatGroq(
    temperature=0.1, 
    groq_api_key=GROQ_API_KEY,
    model_name="llama-3.1-8b-instant"
).bind_tools(tools_list)

tools_map = {
    "tool_calculate": tool_calculate,
    "tool_get_weather": tool_get_weather,
    "tool_google_search": tool_google_search,
    "tool_convert_currency": tool_convert_currency
}

# =====================================================================
# 2. БЛОК РАБОТЫ С БАЗОЙ ДАННЫХ (КОНТЕКСТНАЯ ПАМЯТЬ)
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

def get_chat_history(chat_id, limit=4):
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
# 3. ПОЛЬЗОВАТЕЛЬСКИЙ ИНТЕРФЕЙС
# =====================================================================
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
        "Бот переведен на отказоустойчивую архитектуру Native Tool Calling. "
        "Используйте кнопки меню или пишите запросы текстом."
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=get_main_keyboard())

# =====================================================================
# 4. АСИНХРОННЫЙ МОДУЛЬ НАПОМИНАНИЙ
# =====================================================================
def send_delayed_reminder(chat_id, delay_seconds, text):
    time.sleep(delay_seconds)
    try:
        bot.send_message(chat_id, f"⏰ НАПОМИНАНИЕ: {text}")
    except Exception as e:
        print(f"Ошибка отправки напоминания: {e}")

# =====================================================================
# 5. МАРШРУТИЗАЦИЯ И ОБРАБОТКА ЗАПРОСОВ (ЯДРО АГЕНТА)
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
            bot.send_message(chat_id, "Отправьте пример, например: Сколько будет 7274 умножить на 6373")
            return
        elif user_text == "🔍 Поиск знаний":
            bot.send_message(chat_id, "Что найти? Например: Кто такой Илон Маск")
            return
        elif user_text == "💵 Курс валют":
            bot.send_message(chat_id, "Например: Переведи 150 долларов в рубли")
            return
        elif user_text == "⏰ Напоминание":
            bot.send_message(chat_id, "Например: Напомни через 10 секунд проверить код")
            return

        save_message(chat_id, "user", user_text)
        
        system_instruction = (
            "Ты — лаконичный ИИ-агент, помогающий пользователю. Отвечай строго на русском языке.\n"
            "Твоя главная черта — максимальная краткость и точность. Никакой воды и долгих вступлений.\n"
            "ПРАВИЛА ВЫЗОВА ИНСТРУМЕНТОВ:\n"
            "1. Если для ответа нужны точные вычисления, погода, курс валют или поиск фактов в сети — "
            "вызывай подходящий инструмент. Передавай в него только реальные параметры.\n"
            "2. Если запрос неполный или абстрактный (например, 'сколько лет', 'привет'), "
            "НЕ вызывай инструменты. Ответь обычным коротким текстом и вежливо попроси уточнить вопрос.\n"
            "3. Если ты отвечаешь обычным текстом (без инструментов), пиши ответ в 1-2 простых предложения. "
            "Не используй сложные списки, маркеры и лишнее форматирование."
        )

        if "напомни через" in user_text.lower():
            try:
                words = user_text.lower().split()
                seconds = int(words[2])
                reminder_text = " ".join(words[4:])
                threading.Thread(target=send_delayed_reminder, args=(chat_id, seconds, reminder_text), daemon=True).start()
                bot.reply_to(message, f"Задача принята. Напоминание сработает через {seconds} сек.", reply_markup=get_main_keyboard())
                return
            except:
                pass

        messages = [SystemMessage(content=system_instruction)]
        messages.extend(get_chat_history(chat_id, limit=2))
        messages.append(HumanMessage(content=user_text))

        ai_msg = llm.invoke(messages)
        bot_answer = ""
        
        if ai_msg.tool_calls:
            for tool_call in ai_msg.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                
                print(f"[Вызов инструмента]: {tool_name} с параметрами {tool_args}")
                
                if tool_name in tools_map:
                    try:
                        # Получаем чистый результат выполнения функции
                        result = tools_map[tool_name].invoke(tool_args)
                        bot_answer = str(result)
                    except Exception as tool_err:
                        print(f"[Ошибка выполнения инструмента]: {tool_err}")
                        bot_answer = "Извините, не удалось обработать этот запрос внутри системных модулей."
                else:
                    bot_answer = "Ошибка: затребован неизвестный модуль."
        else:
            bot_answer = ai_msg.content.strip()

        if not bot_answer:
            bot_answer = "Не удалось сформировать ответ. Пожалуйста, повторите запрос."

        save_message(chat_id, "assistant", bot_answer)
        bot.reply_to(message, bot_answer, reply_markup=get_main_keyboard())
            
    except Exception as e:
        print(f"[Системная ошибка ядра]: {e}")
        bot.reply_to(message, "Произошла техническая ошибка. Повторите запрос позже.", reply_markup=get_main_keyboard())

# =====================================================================
# 6. ВЕБ-СЕРВЕР ДЛЯ HEALTH CHECK (RENDER) И ЗАПУСК БОТА
# =====================================================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("OK".encode("utf-8"))
    def log_message(self, format, *args):
        return

def run_health_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=run_health_server, daemon=True).start()
    print("=======================================================")
    print(" ИИ-АГЕНТ ЩУЧКИНА И.А. УСПЕШНО ЗАПУЩЕН")
    print("=======================================================")
    bot.infinity_polling()