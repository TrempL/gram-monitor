# GRAM Monitor

Сайт с курсом GRAM (бывший Toncoin): цена в USD и RUB, изменение за 24 часа,
график за 24 ч / 7 / 30 дней, автообновление каждые 30 секунд.

**Стек:** Python 3 + Flask (бэкенд), HTML + Chart.js (страница), CoinGecko API (данные, без ключа).
На сервере: gunicorn + systemd + nginx.

```
браузер ──► nginx :80 ──► gunicorn :8000 (Flask, app.py) ──► CoinGecko
                                   └─ кэш: курс 1 мин, график 10 мин
```

| Адрес | Что отдаёт |
|---|---|
| `/` | страница |
| `/api/price` | курс USD/RUB + изменение за 24 ч |
| `/api/chart?currency=usd&days=7` | точки графика (`currency`: usd/rub, `days`: 1/7/30) |
| `/health` | `200` — курс свежий, `503` — проблема (для мониторинга) |

---

## Шаг 3. Запуск на Маке

```bash
cd ~/Projects/gram-monitor          # где лежит папка проекта
python3 -m venv .venv               # виртуальное окружение: свои библиотеки для проекта
source .venv/bin/activate           # включить его (в начале строки появится (.venv))
pip install -r requirements.txt
python app.py
```

Открой http://127.0.0.1:8000 и проверь API: http://127.0.0.1:8000/api/price.
Остановить: **Control + C**.

> Если `/api/price` отвечает ошибкой, проверь ID монеты:
> `curl "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd"`.
> Если там пусто, найди правильный ID через `curl "https://api.coingecko.com/api/v3/search?query=gram"`
> и запусти с ним: `COIN_ID=найденный_id python app.py`.

## Шаг 4. GitHub

1. На github.com → **New repository** → имя `gram-monitor`, **Public**, без README.
2. На Маке, в папке проекта:

```bash
git init
git add .
git commit -m "GRAM Monitor: первая версия"
git branch -M main
git remote add origin https://github.com/ТВОЙ_НИК/gram-monitor.git
git push -u origin main
```

`.gitignore` уже не пускает в репозиторий `.venv` и `.env` (секреты в Git не кладём).
Если `git push` попросит пароль — нужен не пароль, а токен (GitHub → Settings → Developer settings →
Personal access tokens) или SSH-ключ. Проще всего: `brew install gh && gh auth login`.

## Шаг 5. Деплой на VPS

Подключаемся: `ssh vps` (или `ssh daniil@168.113.184.96`).

**5.1. Пакеты**
```bash
sudo apt update
sudo apt install -y python3-venv nginx git curl
```

**5.2. Код и окружение**
```bash
cd ~
git clone https://github.com/ТВОЙ_НИК/gram-monitor.git
cd gram-monitor
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```
Быстрая проверка вручную: `.venv/bin/gunicorn -b 127.0.0.1:8000 app:app`,
во втором окне `ssh vps` → `curl 127.0.0.1:8000/api/price`. Потом Control + C.

**5.3. systemd — чтобы сайт работал всегда и поднимался после перезагрузки**
```bash
sudo cp deploy/gram-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gram-monitor
systemctl status gram-monitor        # должно быть active (running); выход — q
curl 127.0.0.1:8000/health
```

**5.4. nginx — принимает запросы из интернета на 80 порту и передаёт приложению**
```bash
sudo cp deploy/nginx-gram-monitor.conf /etc/nginx/sites-available/gram-monitor
sudo ln -s /etc/nginx/sites-available/gram-monitor /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default      # стандартная заглушка nginx нам не нужна
sudo nginx -t                                 # проверка конфига: "syntax is ok"
sudo systemctl reload nginx
```
Открой в браузере: **http://168.113.184.96** 🎉

**Обновление после правок** (на Маке `git push`, потом на сервере):
```bash
cd ~/gram-monitor && git pull
.venv/bin/pip install -r requirements.txt     # если менялись зависимости
sudo systemctl restart gram-monitor
```

**Полезное:**
- логи приложения: `journalctl -u gram-monitor -f`
- логи nginx: `sudo tail -f /var/log/nginx/error.log`
- 502 Bad Gateway в браузере = nginx жив, а приложение лежит → смотри `systemctl status gram-monitor`

HTTPS (замок в браузере) выдаётся только на домен, не на IP. Когда купишь домен —
`sudo apt install certbot python3-certbot-nginx && sudo certbot --nginx -d твой-домен.ru`.

## Шаг 6. Проверка в скрипте мониторинга

Вставь содержимое `deploy/check_gram.sh` в конец `~/scripts/monitor.sh`:
```bash
cat ~/gram-monitor/deploy/check_gram.sh >> ~/scripts/monitor.sh
~/scripts/monitor.sh; echo "код выхода: $?"
```
Скрипт проверяет три вещи: сервис `gram-monitor` запущен, nginx запущен, `/health` через nginx
отвечает 200. Если что-то не так — пишет ❌ и выходит с кодом 1. Cron уже запускает
`monitor.sh` каждые 10 минут, так что результат будет в `~/monitor.log`.

Проверь, что тревога срабатывает: `sudo systemctl stop gram-monitor && ~/scripts/monitor.sh`,
потом верни: `sudo systemctl start gram-monitor`.
