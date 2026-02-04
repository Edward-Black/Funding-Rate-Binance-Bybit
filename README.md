# Funding Rate Parser

Десктопное приложение для Windows: отображение **Funding Rate**, **Time to Next** и **Interval** по фьючерсным парам на биржах **Binance**, **Bybit** и **OKX**. Данные обновляются каждые 15 секунд; обратный отсчёт до следующего фандинга пересчитывается каждую секунду.

## Возможности

- **Текущий фандинг** по трём биржам: ставка (%), время до следующего фандинга (Xh Ym Zs), интервал (4h, 8h и т.д.).
- **Funding Rate History** — у каждой биржи раскрывающийся список прошедших фандингов с прокруткой; время в локальном часовом поясе.
- **Поле Trading Pair**: ввод только латиницы в верхнем регистре, цифр и дефиса (независимо от раскладки клавиатуры). Поддержка вставки по **Ctrl+V** с фильтрацией символов. Короткий тикер автоматически дополняется: `ZIL` → `ZILUSDT`.
- **Обновление**: кнопка **Refresh** или клавиша **Enter**; автообновление раз в 15 секунд.
- **Сохранение состояния окна**: при закрытии запоминаются размер, позиция на экране и последняя введённая пара. Перед сохранением все раскрытые списки истории сворачиваются, чтобы при следующем запуске окно открывалось в «обычном» размере.

## Установка

```bash
git clone <url-репозитория>
cd funding-parser
pip install -r requirements.txt
```

Кэш в Parquet опционален: без `pandas` и `pyarrow` приложение работает, кэш просто не ведётся. Для записи кэша:

```bash
pip install pandas pyarrow
```

## Запуск

**Рекомендуемый способ** — запуск GUI (API поднимается в фоне):

```bash
python run_gui.py
```

**Раздельный запуск** (API и окно отдельно):

Терминал 1:
```bash
python main.py
```

Терминал 2:
```bash
python -m gui.window
```

По умолчанию API слушает `127.0.0.1:8765`. Хост и порт можно задать переменными окружения `FUNDING_API_HOST` и `FUNDING_API_PORT`.

## API

- **`GET /api/funding?symbol=BTCUSDT`** — текущие данные по Binance, Bybit, OKX: `fundingRate`, `nextFundingTimeMs`, `interval` для каждой биржи.
- **`GET /api/funding-history?symbol=BTCUSDT`** — история фандингов: по каждой бирже список объектов `{ "fundingTime": <ms>, "fundingRate": "<string>" }`.

Пример:

```bash
curl "http://127.0.0.1:8765/api/funding?symbol=BTCUSDT"
```

## Сборка .exe (Windows)

1. Установить зависимости: `pip install -r requirements.txt`
2. В корне проекта выполнить:
   ```bash
   build.bat
   ```
   или вручную:
   ```bash
   pyinstaller FundingRate.spec --noconfirm
   ```
3. Исполняемый файл: `dist\FundingRate.exe`. Его можно копировать и запускать без установленного Python. Папка `data` (кэш Parquet) и файл `window_state.json` (размер/позиция окна и последняя пара) создаются рядом с exe при необходимости.

## Структура проекта

```
funding-parser/
├── main.py              # FastAPI-приложение, фоновое обновление кэша
├── run_gui.py           # Точка входа: запуск API + GUI (для exe и разработки)
├── config.py            # Хост, порт, интервал обновления, пути
├── app_state.py         # Общий кэш и текущий символ для API
├── requirements.txt
├── FundingRate.spec     # Конфигурация PyInstaller
├── build.bat            # Сборка exe
├── gui/
│   └── window.py       # Окно Tkinter: пара, биржи, история, сохранение состояния
├── routers/
│   └── funding.py      # Эндпоинты /api/funding и /api/funding-history
├── services/
│   └── exchange_fetcher.py  # Запросы к Binance, Bybit, OKX (текущий курс и история)
└── storage/
    └── parquet_cache.py     # Опциональная запись кэша в Parquet
```

## Лицензия

Проект предназначен для личного и образовательного использования. При использовании API бирж соблюдайте их условия использования и лимиты запросов.
