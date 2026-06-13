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

## Жизненный цикл товара

| Шаг | Действие | UI / API |
|-----|----------|----------|
| 1 | **Номенклатура** — карточка Product (SKU, габариты, категория) | Админка → вкладка **Номенклатура**; `POST /api/products/` (admin) |
| 2 | Приёмка — партия со сроком годности | Вкладка **Приёмка**; `POST /api/batches/` |
| 3 | Планограмма на слот | **Карта зала** |
| 4 | Выкладка | **Центр задач** / PWA сотрудника |

На шаге 1 **не** создаётся остаток на складе (`StockItem`) — только после приёмки.

- `GET /api/categories/` — список категорий
- `POST /api/categories/` — новая категория (admin)
- `GET /api/products/` — каталог с габаритами
- `POST /api/products/` — регистрация товара (admin)

## Заказы поставщику

Цепочка: управляющий оформляет заказ → задача **Приёмка** в PWA сотрудника → фактические кол-ва и сроки → склад (FEFO-партии).

| Эндпоинт | Назначение |
|----------|------------|
| `GET /api/employees/` | Сотрудники для назначения приёмки (admin) |
| `GET /api/suppliers/` | Справочник поставщиков |
| `POST /api/suppliers/` | Регистрация поставщика (admin, ИНН 10/12 цифр) |
| `GET /api/supply-orders/` | Список заказов с позициями и задачей приёмки |
| `POST /api/supply-orders/` | Создание (`status`, опционально `assigned_to`, `planned_receiving_date`) |
| `PATCH /api/supply-orders/{id}/` | Редактирование черновика (в т.ч. `planned_receiving_date`) |
| `POST /api/supply-orders/{id}/submit/` | Черновик → «В пути» + задача приёмки (тело: `assigned_to`, `planned_receiving_date`) |
| `GET /api/receiving-tasks/` | Задачи приёмки (сотрудник / admin) |
| `POST /api/receiving-tasks/{id}/accept/` | Взять в работу |
| `POST /api/receiving-tasks/{id}/complete/` | `lines[{item_id, expiration_date, actual_quantity, discrepancy_note?}]` → `received` |

Прямой `POST .../supply-orders/{id}/receive/` отключён — приёмка только через задачу сотрудника.

**Плановая дата приёмки** — поле `planned_receiving_date` (дата `YYYY-MM-DD`, необязательно) при создании, в черновике и при `submit`. Отображается в PWA сотрудника и в карточке заказа у управляющего.

**Расхождения:** если `actual_quantity` ≠ заказанному `quantity`, в `complete` обязательно непустое `discrepancy_note` на строке; на заказе выставляется `has_discrepancies`. В интерфейсе сотрудника — сводка и подтверждение; у управляющего — фильтр «С расхождениями» и панель детализации.

## Цифровой двойник (карта зала)

| Эндпоинт | Назначение |
|----------|------------|
| `GET /api/store-map/` | Размер холста зала (`width_m`, `length_m`) |
| `GET /api/zones/` | Зоны + оборудование + вложенные `slots[]` (планограмма, остатки) |
| `GET /api/slots/{id}/qr/` | QR-токен слота |

**Типы оборудования:** `shelf`, `hanger`, `fridge`, `box`, `mannequin` (миграция с legacy `shelving` / `pegboard` / `pallet` / `display`).

**Индикация слотов** (режим мерчандайзинга, react-konva): каждый `EquipmentSlot` — отдельная ячейка; цвет по `current_qty / max_capacity`:

- зелёный — &gt; 70%
- жёлтый — 30–70% или активная задача выкладки
- красный — &lt; 30%

Поля слота в API: `active_placement_task`, `nearest_batch_expiry` (FEFO по партиям на полке). Spatial Engine считает `max_capacity` по типу оборудования (сетка / вешалка / навал / манекен = 1).

UI: вкладка **Карта зала** — в режиме просмотра Konva + правая панель детализации; в режиме редактирования — DOM-перетаскивание оборудования.

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

## Автосписание просрочки с полок

Если **партия последней завершённой выкладки** на слот просрочена (`expiration_date < сегодня`), остаток на слоте (`current_qty`) обнуляется, пишется журнал `ShelfWriteOff`, срабатывает триггер пополнения 30%.

```bash
# Просмотр без изменений
python manage.py write_off_expired_shelf --dry-run

# Списание (все магазины или --store-id N)
python manage.py write_off_expired_shelf
```

API (админ): `POST /api/inventory/write-off-expired/` (query `dry_run=true` для пробного прогона).

**Ограничение:** учитывается только последняя `COMPLETED` выкладка с `batch`; слоты без такой истории не списываются автоматически.

Рекомендуется запускать **ежедневно** (Планировщик заданий Windows / cron).

## Как проверить MVP за 2 минуты

1. `python manage.py migrate`
2. Запуск: `python manage.py runserver` (или `daphne … asgi:application`) и `cd frontend && npm start`
3. Войти **менеджером** → вкладка **Карта зала** → открыть оборудование с планограммой: на слоте видно **«на полке: X / Y»**, кнопка **«Симулировать продажу (−1)»**
4. При заполнении &lt; 30% появится задача **CREATED** (вкладка **Задачи** или `GET /api/task-pool/`)
5. Войти **сотрудником** (`role=employee`, привязка к `store`) → `/employee` → взять задачу → QR → фото
6. Toast на PWA сотрудника при `ws/notifications/` (нужен тот же магазин у пользователя)

Для теста PWA под админом: в шапке админки ссылка «PWA сотрудника» (откроется `/employee` только для `role=employee` — создайте пользователя `employee` в Django Admin).
