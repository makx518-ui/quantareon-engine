# КВАНТАРИОН — АСТРО-ФРАКТАЛ

## Быстрый запуск

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Скачать эфемериды для Хирона (один раз)
mkdir -p data/ephe
wget -O data/ephe/seas_18.se1 https://raw.githubusercontent.com/aloistr/swisseph/master/ephe/seas_18.se1

# 3. Запустить сервер
python api/main.py

# 4. Открыть браузер
# http://localhost:8000/docs — документация API
```

## Структура

```
quantarion-astrofractal/
├── engine/              — собственные модули (1644 стр)
│   ├── micro_cascade.py     фрактальный расчёт (4 уровня)
│   ├── degree_parser.py     парсер 360 градусов
│   ├── cascade_assembler.py сборка маркеров для ИИ
│   ├── natal.py             натальная карта (18 точек + ТЖ)
│   ├── horary.py            таймстамп → ASC → натал
│   ├── synastry.py          синастрия + уран-синхрон
│   └── matrix.py            карта оператора (постоянный слой)
├── astro/               — модули из Dream Oracle (5094 стр)
│   ├── astro_engine.py      базовый движок
│   ├── solar_calculator.py  соляр
│   ├── progressions_calculator.py  прогрессии
│   ├── solar_arc_calculator.py     дирекции
│   ├── transit_activations.py      транзиты
│   ├── profections_calculator.py   профекции
│   ├── eclipses_calculator.py      затмения
│   └── lunations_calculator.py     лунации
├── api/
│   └── main.py          FastAPI сервер (13 эндпоинтов)
├── data/
│   ├── gradusy_360_baza.txt  база градусов
│   └── ephe/                 эфемериды (Хирон)
├── frontend/
│   └── quantarion-panel.jsx  панель управления
└── requirements.txt
```

## API эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| POST | /natal | Натальная карта |
| POST | /cascade | Фрактальный расклад |
| POST | /horary | Хорарная ректификация |
| POST | /synastry | Синастрия двух карт |
| POST | /uran-sync | Уран-синхрон (антенна) |
| POST | /solar | Соляр |
| POST | /progressions | Прогрессии |
| POST | /directions | Дирекции |
| POST | /transit-aspects | Транзитные активации |
| POST | /profections | Профекции |
| GET | /transit | Текущие позиции планет |
| GET | /matrix | Статус матрицы оператора |
| GET | /geocode | Город → координаты |

## Проект Квантарион (Астро-фрактал)
Экспериментальный инструмент. Доступ: только оператор.
