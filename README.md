# ShopHelper

TES для SMB-ритейла: цифровой план зала, FEFO-партии, смарт-задачи на выкладку, PWA для сотрудников.

## Два типа задач в UI

| Тип | Модель | Назначение |
|-----|--------|------------|
| **Выкладка** | `PlacementTask` (int) | Автоматически из планограммы и триггера 30% `current_qty` / `max_capacity` на слоте |
| **Поручение** | `StaffTask` (UUID) | Ручное задание менеджера (уборка зоны и т.д.) |

Общий список: `GET /api/task-pool/`. WebSocket: `ws/task-pool/`, уведомления магазина: `ws/notifications/`.

Чат выкладки (проблема на складе): `ws/chat/<placement_task_id>/`, REST `GET|POST /api/placement-tasks/{id}/messages/`.

Чат поручений: `ws/staff-tasks/<uuid>/chat/`.

## Запуск (разработка)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
daphne -b 127.0.0.1 -p 8000 shophelper.asgi:application
```

Фронтенд: `cd frontend && npm install && npm start`.

## PostgreSQL + Redis (production-like)

```bash
docker compose up -d
```

В `.env`:

```
DATABASE_URL=postgres://shophelper:shophelper@localhost:5432/shophelper
REDIS_URL=redis://localhost:6379/0
```

Channels использует Redis при заданном `REDIS_URL`.

## Учёт на слоте (MVP)

- `EquipmentSlot.current_qty` / `max_capacity` — остаток и вместимость витрины.
- Триггер пополнения: `current_qty < 30% * max_capacity`.
- Закрытие выкладки: атомарно `batch -= qty`, `slot.current_qty += qty`, `COMPLETED`.
- Статусы выкладки: `CREATED` → `IN_PROGRESS` → `COMPLETED` | `FAILED` (кнопка «Проблема»).

Симуляция продажи со слота: `POST /api/slots/{id}/adjust-qty/` с телом `{"delta": -2}`.

## Как проверить MVP за 2 минуты

1. `python manage.py migrate`
2. Запуск: `python manage.py runserver` (или `daphne … asgi:application`) и `cd frontend && npm start`
3. Войти **менеджером** → вкладка **Карта зала** → открыть оборудование с планограммой: на слоте видно **«на полке: X / Y»**, кнопка **«Симулировать продажу (−1)»**
4. При заполнении &lt; 30% появится задача **CREATED** (вкладка **Задачи** или `GET /api/task-pool/`)
5. Войти **сотрудником** (`role=employee`, привязка к `store`) → `/employee` → взять задачу → QR → фото
6. Toast на PWA сотрудника при `ws/notifications/` (нужен тот же магазин у пользователя)

Для теста PWA под админом: в шапке админки ссылка «PWA сотрудника» (откроется `/employee` только для `role=employee` — создайте пользователя `employee` в Django Admin).
