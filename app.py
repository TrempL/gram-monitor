"""
GRAM Monitor — маленький сайт с курсом GRAM (бывший Toncoin).

Как это устроено:
  браузер  ->  наш Flask-сервер  ->  CoinGecko API
Браузер никогда не ходит в CoinGecko сам: сервер запрашивает курс
и запоминает его (кэш), поэтому даже 100 открытых вкладок
не превысят лимит бесплатного API.
"""

import logging
import os
import threading
import time

import requests
from flask import Flask, jsonify, request, send_from_directory

# ---------- Настройки (можно переопределить переменными окружения) ----------
# ID монеты в API CoinGecko. После ребрендинга TON -> GRAM он остался прежним.
COIN_ID = os.getenv("COIN_ID", "the-open-network")
# Необязательный бесплатный "Demo"-ключ CoinGecko: с ним лимиты мягче.
API_KEY = os.getenv("COINGECKO_API_KEY", "")
BASE_URL = "https://api.coingecko.com/api/v3"

PRICE_TTL = 60        # курс обновляем не чаще раза в минуту
CHART_TTL = 600       # график — не чаще раза в 10 минут
STALE_AFTER = 600     # если курсу больше 10 минут — /health считает это проблемой

ALLOWED_CURRENCIES = {"usd", "rub"}
ALLOWED_DAYS = {"1", "7", "30"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gram-monitor")

app = Flask(__name__, static_folder="static", static_url_path="")

# ---------- Кэш ----------
_cache = {}               # ключ -> {"data": ..., "ts": время получения}
_lock = threading.Lock()  # чтобы два запроса одновременно не дёргали API


def coingecko_get(path, params):
    headers = {"accept": "application/json", "user-agent": "gram-monitor/1.0"}
    if API_KEY:
        headers["x-cg-demo-api-key"] = API_KEY
    resp = requests.get(BASE_URL + path, params=params, headers=headers, timeout=10)
    resp.raise_for_status()  # 4xx/5xx -> исключение
    return resp.json()


def cached(key, ttl, fetch):
    """Вернуть (данные, время_получения, устарели_ли).

    Если в кэше свежие данные — отдаём их. Иначе спрашиваем API.
    Если API упал, но старые данные есть — отдаём старые с пометкой stale.
    """
    now = time.time()
    with _lock:
        item = _cache.get(key)
        if item and now - item["ts"] < ttl:
            return item["data"], item["ts"], False
        try:
            data = fetch()
        except Exception as exc:
            log.warning("Не удалось получить %s: %s", key, exc)
            if item:
                return item["data"], item["ts"], True
            raise
        _cache[key] = {"data": data, "ts": now}
        return data, now, False


def fetch_price():
    data = coingecko_get("/simple/price", {
        "ids": COIN_ID,
        "vs_currencies": "usd,rub",
        "include_24hr_change": "true",
        "include_last_updated_at": "true",
    })
    coin = data.get(COIN_ID)
    if not coin:
        raise ValueError(f"CoinGecko не вернул данные для '{COIN_ID}'")
    return {
        "usd": coin["usd"],
        "rub": coin["rub"],
        "change_24h_usd": coin.get("usd_24h_change"),
        "change_24h_rub": coin.get("rub_24h_change"),
        "source_updated_at": coin.get("last_updated_at"),
    }


def fetch_chart(currency, days):
    data = coingecko_get(f"/coins/{COIN_ID}/market_chart",
                         {"vs_currency": currency, "days": days})
    # CoinGecko отдаёт [[время_в_мс, цена], ...]
    return [{"t": int(t), "p": p} for t, p in data["prices"]]


# ---------- Маршруты ----------
@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/price")
def api_price():
    try:
        data, ts, stale = cached("price", PRICE_TTL, fetch_price)
    except Exception:
        return jsonify(error="Курс временно недоступен"), 502
    return jsonify(**data, fetched_at=int(ts), stale=stale)


@app.get("/api/chart")
def api_chart():
    currency = request.args.get("currency", "usd").lower()
    days = request.args.get("days", "7")
    if currency not in ALLOWED_CURRENCIES or days not in ALLOWED_DAYS:
        return jsonify(error="currency: usd|rub, days: 1|7|30"), 400
    try:
        points, ts, stale = cached(f"chart:{currency}:{days}", CHART_TTL,
                                   lambda: fetch_chart(currency, days))
    except Exception:
        return jsonify(error="График временно недоступен"), 502
    return jsonify(currency=currency, days=days, points=points,
                   fetched_at=int(ts), stale=stale)


@app.get("/health")
def health():
    """Для скрипта мониторинга: 200 = всё хорошо, 503 = курс не обновляется."""
    try:
        _, ts, _ = cached("price", PRICE_TTL, fetch_price)
    except Exception as exc:
        return jsonify(status="error", detail=str(exc)), 503
    age = int(time.time() - ts)
    if age > STALE_AFTER:
        return jsonify(status="stale", age_sec=age), 503
    return jsonify(status="ok", age_sec=age)


if __name__ == "__main__":
    # Локальный запуск на Маке. Порт 8000, потому что 5000 на macOS занят AirPlay.
    app.run(host="127.0.0.1", port=8000, debug=True)
