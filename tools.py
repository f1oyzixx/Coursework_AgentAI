import requests
import wikipediaapi
from datetime import datetime
import pytz
from timezonefinder import TimezoneFinder
from geopy.geocoders import Nominatim

def calculate(expression: str) -> str:
    """Математический калькулятор."""
    try:
        allowed = "0123456789+-*/.() "
        expression = "".join(c for c in expression if c in allowed)
        if not expression.strip():
            return "Не передан математический пример."
        result = eval(expression, {"__builtins__": None}, {})
        return str(result)
    except Exception:
        return "Ошибка вычисления примеров."

def get_weather(city: str) -> str:
    """Запрос текущей погоды и времени."""
    if not city or len(city.strip()) < 2:
        return "Неверно указан город."
    
    url = f"https://wttr.in/{city}?format=3&lang=ru&0"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            weather_text = response.text.strip()
        else:
            weather_text = f"Данные о погоде в городе {city} временно недоступны."

        geolocator = Nominatim(user_agent="shchukin_ai_bot_31is", timeout=10)
        location = geolocator.geocode(city)
        time_text = ""
        
        if location:
            tf = TimezoneFinder()
            tz_str = tf.timezone_at(lng=location.longitude, lat=location.latitude)
            if tz_str:
                tz = pytz.timezone(tz_str)
                time_now = datetime.now(tz).strftime("%H:%M")
                time_text = f" | Местное время: {time_now}"

        return f"{weather_text}{time_text}"
    except Exception:
        return f"Погода в г. {city} сейчас недоступна (таймаут сервера)."

def google_search(query: str) -> str:
    """Поиск информации в Википедии (с автопоиском похожих тем)."""
    if not query or len(query.strip()) < 2:
        return "Пустой поисковый запрос."
        
    try:
        wiki = wikipediaapi.Wikipedia(
            user_agent="MyCourseWorkBot/1.0 (student_project@example.com)",
            language="ru"
        )
        
        page = wiki.page(query)
        if page.exists():
            return page.summary[:800]
            
        search_url = f"https://ru.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "srlimit": 1
        }
        res = requests.get(search_url, timeout=5).json()
        search_results = res.get("query", {}).get("search", [])
        
        if search_results:
            title = search_results[0]["title"]
            page = wiki.page(title)
            if page.exists():
                return f"[Найдено по теме '{title}']: {page.summary[:800]}"
                
        return f"Информации по запросу '{query}' не найдено в базе знаний."
    except Exception as e:
        return f"Сервер знаний временно недоступен."

def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """Конвертирует валюту по актуальному курсу ЦБ РФ."""
    try:
        amount = float(amount)
        url = "https://www.cbr-xml-daily.ru/daily_json.js"
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return "Финансовый сервер ЦБ РФ временно недоступен."
            
        data = response.json()
        rates = data.get("Valute", {})
        
        from_curr = from_currency.upper().strip()
        to_curr = to_currency.upper().strip()
        
        if from_curr == "RUB":
            val_in_rub = amount
        else:
            if from_curr not in rates:
                return f"Валюта {from_curr} не поддерживается."
            val_in_rub = amount * (rates[from_curr]["Value"] / rates[from_curr]["Nominal"])
            
        if to_curr == "RUB":
            result = val_in_rub
        else:
            if to_curr not in rates:
                return f"Валюта {to_curr} не поддерживается."
            result = val_in_rub / (rates[to_curr]["Value"] / rates[to_curr]["Nominal"])
            
        return f"{amount} {from_curr} = {round(result, 2)} {to_curr} (по курсу ЦБ РФ)"
    except Exception:
        return "Ошибка конвертации валют."