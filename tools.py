import requests
import wikipediaapi
from datetime import datetime
import pytz
from timezonefinder import TimezoneFinder
from geopy.geocoders import Nominatim
from bs4 import BeautifulSoup

def calculate(expression: str) -> str:
    try:
        allowed = "0123456789+-*/.() "
        expression = "".join(c for c in expression if c in allowed)
        result = eval(expression, {"__builtins__": None}, {})
        return str(result)
    except Exception:
        return "Ошибка вычисления"

def get_weather(city: str):
    url = f"https://wttr.in/{city}?format=3&lang=ru&0"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            weather_text = response.text.strip()
        else:
            weather_text = "данные о погоде недоступны"

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
    except Exception as e:
        return f"Ошибка при получении погоды: {str(e)}"

def google_search(query: str) -> str:
    try:
        wiki = wikipediaapi.Wikipedia(
            user_agent="MyCourseWorkBot/1.0 (student_project@example.com)",
            language="ru"
        )
        page = wiki.page(query)
        if page.exists():
            return f"Найденные факты из базы знаний:\n{page.summary[:1500]}"
        else:
            url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200 and "result__snippet" in res.text:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(res.text, "html.parser")
                snippets = [s.get_text(strip=True) for s in soup.find_all("a", class_="result__snippet")[:2]]
                if snippets:
                    return "Факты из сети:\n" + "\n".join(snippets)
            return f"К сожалению, по запросу '{query}' не удалось найти подробных статей."
    except Exception as e:
        return f"Ошибка при поиске информации: {e}"

def convert_currency(amount: float, from_curr: str, to_curr: str) -> str:
    """Конвертирует валюту по актуальному курсу ЦБ РФ."""
    try:
        url = "https://www.cbr-xml-daily.ru/daily_json.js"
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return "Финансовый сервер ЦБ РФ временно недоступен."
            
        data = response.json()
        rates = data.get("Valute", {})
        
        from_curr, to_curr = from_curr.upper(), to_curr.upper()
        
        if from_curr == "RUB":
            val_in_rub = amount
        else:
            if from_curr not in rates:
                return f"Валюта {from_curr} не поддерживается ЦБ РФ."
            val_in_rub = amount * (rates[from_curr]["Value"] / rates[from_curr]["Nominal"])
            
        if to_curr == "RUB":
            result = val_in_rub
        else:
            if to_curr not in rates:
                return f"Валюта {to_curr} не поддерживается ЦБ РФ."
            result = val_in_rub / (rates[to_curr]["Value"] / rates[to_curr]["Nominal"])
            
        return f"Расчет: {amount} {from_curr} = {round(result, 2)} {to_curr} (по курсу ЦБ РФ)."
    except Exception as e:
        return f"Ошибка при конвертации валюты: {e}"