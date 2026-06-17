import requests
import wikipediaapi
from datetime import datetime
import pytz
from timezonefinder import TimezoneFinder
from geopy.geocoders import Nominatim

def calculate(expression: str) -> str:
    try:
        allowed = "0123456789+-*/.() "
        expression = "".join(c for c in expression if c in allowed)
        if not expression.strip():
            return "не передан пример"
        result = eval(expression, {"__builtins__": None}, {})
        return str(result)
    except Exception:
        return "ошибка вычисления"

def get_weather(city: str) -> str:
    if not city:
        return "город не указан"
    url = f"https://wttr.in/{city}?format=3&lang=ru&0"
    try:
        response = requests.get(url, timeout=5)
        weather_text = response.text.strip() if response.status_code == 200 else "данные о погоде недоступны"

        geolocator = Nominatim(user_agent="shchukin_ai_bot_31is", timeout=10)
        location = geolocator.geocode(city)
        time_text = ""
        
        if location:
            tf = TimezoneFinder()
            tz_str = tf.timezone_at(lng=location.longitude, lat=location.latitude)
            if tz_str:
                tz = pytz.timezone(tz_str)
                time_now = datetime.now(tz).strftime("%H:%M")
                time_text = f" | Время: {time_now}"

        return f"{weather_text}{time_text}"
    except Exception:
        return f"Погода в г. {city} временно недоступна."

def google_search(query: str) -> str:
    if not query:
        return "пустой запрос"
    try:
        wiki = wikipediaapi.Wikipedia(
            user_agent="MyCourseWorkBot/1.0 (student_project@example.com)",
            language="ru"
        )
        page = wiki.page(query)
        if page.exists():
            return page.summary[:1000]
            
        search_url = "https://ru.wikipedia.org/w/api.php"
        params = {
            "action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": 1
        }
        res = requests.get(search_url, timeout=5).json()
        search_results = res.get("query", {}).get("search", [])
        
        if search_results:
            title = search_results[0]["title"]
            page = wiki.page(title)
            if page.exists():
                return page.summary[:1000]
                
        return f"Информация про '{query}' отсутствует в базе знаний."
    except Exception:
        return "Сервер базы знаний временно недоступен."

def convert_currency(amount, from_currency: str, to_currency: str) -> str:
    try:
        amount = float(amount)
        url = "https://www.cbr-xml-daily.ru/daily_json.js"
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return "Сервер ЦБ РФ недоступен."
            
        data = response.json()
        rates = data.get("Valute", {})
        
        from_curr = from_currency.upper().strip()
        to_curr = to_currency.upper().strip()
        
        if from_curr == "RUB":
            val_in_rub = amount
        else:
            if from_curr not in rates: return f"Валюта {from_curr} не поддерживается."
            val_in_rub = amount * (rates[from_curr]["Value"] / rates[from_curr]["Nominal"])
            
        if to_curr == "RUB":
            result = val_in_rub
        else:
            if to_curr not in rates: return f"Валюта {to_curr} не поддерживается."
            result = val_in_rub / (rates[to_curr]["Value"] / rates[to_curr]["Nominal"])
            
        return f"{amount} {from_curr} = {round(result, 2)} {to_curr}"
    except Exception:
        return "Ошибка конвертации."