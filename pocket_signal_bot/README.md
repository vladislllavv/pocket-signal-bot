# Pocket Signal Bot 🚀

Telegram бот с AI-аналитикой торговых сигналов.

## 🚀 Запуск на Railway.app (бесплатно)

### Шаг 1. Создать бота в Telegram
1. Открой Telegram → найди **@BotFather**
2. Напиши `/newbot`
3. Введи имя: например `Мой Сигнал Бот`
4. Введи username: `твой_signal_bot` (заканчивается на `bot`)
5. **СОХРАНИ ТОКЕН**, который придёт от BotFather

### Шаг 2. Зарегистрироваться на Railway
1. Зайди на https://railway.app
2. Нажми **Login** → **GitHub**
3. Если нет GitHub — зарегистрируйся на https://github.com

### Шаг 3. Загрузить код на GitHub
1. Скачай проект: https://github.com/твой_логин/pocket-signal-bot (создай новый репозиторий)
2. Или создай новый репозиторий и загрузи туда все файлы

### Шаг 4. Задеплоить на Railway
1. На railway.app нажми **New Project** → **Deploy from GitHub repo**
2. Выбери свой репозиторий
3. Railway сам найдёт Dockerfile и начнёт сборку

### Шаг 5. Добавить переменные (токен)
1. В проекте Railway перейди в **Variables**
2. Добавь:
   - **Key:** `BOT_TOKEN` **Value:** `твой_токен_от_BotFather`
   - **Key:** `WEBHOOK_SECRET` **Value:** `любой_секрет`
   - **Key:** `FREE_SIGNALS_PER_DAY` **Value:** `5`
3. Railway автоматом перезапустит проект

### Шаг 6. Готово!
- Открой Telegram и напиши `/start` своему боту
- Домен для Webhook: `https://твой-проект.railway.app` (показан в настройках Railway)

## 📝 Команды
- `/start` — главное меню
- `/menu` — открыть меню
- `/premium` — подписка
