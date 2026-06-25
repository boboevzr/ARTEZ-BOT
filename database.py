import os
import asyncpg
import logging
from datetime import datetime

DB_URL = os.getenv("DATABASE_URL", "")

pool = None

async def init_db():
    global pool
    if not DB_URL:
        logging.warning("DATABASE_URL not set, DB disabled")
        return
    pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=5)
    await create_tables()
    logging.info("✅ Database connected")

async def create_tables():
    async with pool.acquire() as conn:
        await conn.execute("""
        -- ══════════════════════════════════════
        --  КЛИЕНТЫ
        -- ══════════════════════════════════════
        CREATE TABLE IF NOT EXISTS clients (
            id              SERIAL PRIMARY KEY,
            tg_id           BIGINT UNIQUE NOT NULL,   -- Telegram user ID
            tg_username     VARCHAR(100),              -- @username если есть
            first_name      VARCHAR(100),
            last_name       VARCHAR(100),
            phone           VARCHAR(20),
            lang            VARCHAR(5) DEFAULT 'ru',
            total_orders    INT DEFAULT 0,
            created_at      TIMESTAMP DEFAULT NOW(),
            updated_at      TIMESTAMP DEFAULT NOW()
        );

        -- ══════════════════════════════════════
        --  СОТРУДНИКИ
        -- ══════════════════════════════════════
        CREATE TABLE IF NOT EXISTS staff (
            id              SERIAL PRIMARY KEY,
            tg_id           BIGINT UNIQUE NOT NULL,
            tg_username     VARCHAR(100),
            first_name      VARCHAR(100),
            last_name       VARCHAR(100),
            role            VARCHAR(20) NOT NULL
                            CHECK (role IN ('admin','manager','washer','packer','driver')),
            branch          VARCHAR(20) CHECK (branch IN ('zarafshan','navoi')),
            is_active       BOOLEAN DEFAULT TRUE,
            created_at      TIMESTAMP DEFAULT NOW()
        );

        -- ══════════════════════════════════════
        --  ЗАКАЗЫ
        -- ══════════════════════════════════════
        CREATE TABLE IF NOT EXISTS orders (
            id                  SERIAL PRIMARY KEY,
            order_num           VARCHAR(20) UNIQUE NOT NULL,  -- ARTEZ-1001

            -- Клиент
            client_tg_id        BIGINT NOT NULL,
            client_tg_username  VARCHAR(100),
            client_first_name   VARCHAR(100),
            client_last_name    VARCHAR(100),
            client_phone        VARCHAR(20),

            -- Заявка
            source              VARCHAR(20) DEFAULT 'bot'
                                CHECK (source IN ('bot','site','phone','walkin')),
            branch              VARCHAR(30),
            city                VARCHAR(100),
            address             TEXT,
            location            VARCHAR(100),
            service             VARCHAR(200),
            pickup_date         VARCHAR(50),
            pickup_time         VARCHAR(100),
            note                TEXT,

            -- Статус
            status              VARCHAR(30) DEFAULT 'new'
                                CHECK (status IN (
                                    'new',        -- Новый
                                    'confirmed',  -- Подтверждён
                                    'pickup',     -- Вывоз
                                    'received',   -- В мастерской
                                    'washing',    -- Мойка
                                    'drying',     -- Сушка
                                    'packing',    -- Упаковка
                                    'ready',      -- Готов
                                    'delivery',   -- Доставка
                                    'delivered',  -- Доставлен
                                    'cancelled'   -- Отменён
                                )),

            -- Оператор (кто принял заявку)
            operator_tg_id      BIGINT,
            operator_username   VARCHAR(100),
            operator_first_name VARCHAR(100),
            operator_last_name  VARCHAR(100),
            accepted_at         TIMESTAMP,

            -- Мойщик / исполнитель
            washer_tg_id        BIGINT,
            washer_username     VARCHAR(100),
            washer_first_name   VARCHAR(100),
            washer_last_name    VARCHAR(100),
            washing_started_at  TIMESTAMP,
            washing_done_at     TIMESTAMP,

            -- Водитель вывоза
            driver_pickup_tg_id         BIGINT,
            driver_pickup_username      VARCHAR(100),
            driver_pickup_first_name    VARCHAR(100),
            driver_pickup_last_name     VARCHAR(100),
            pickup_at                   TIMESTAMP,

            -- Водитель доставки
            driver_delivery_tg_id       BIGINT,
            driver_delivery_username    VARCHAR(100),
            driver_delivery_first_name  VARCHAR(100),
            driver_delivery_last_name   VARCHAR(100),
            delivered_at                TIMESTAMP,

            -- Время
            created_at          TIMESTAMP DEFAULT NOW(),
            updated_at          TIMESTAMP DEFAULT NOW()
        );

        -- ══════════════════════════════════════
        --  ИСТОРИЯ СТАТУСОВ
        -- ══════════════════════════════════════
        CREATE TABLE IF NOT EXISTS order_status_history (
            id              SERIAL PRIMARY KEY,
            order_num       VARCHAR(20) NOT NULL,
            old_status      VARCHAR(30),
            new_status      VARCHAR(30) NOT NULL,
            changed_by_tg_id      BIGINT,
            changed_by_name       VARCHAR(200),
            note            TEXT,
            created_at      TIMESTAMP DEFAULT NOW()
        );

        -- ══════════════════════════════════════
        --  ЕДИНИЦЫ ИЗМЕРЕНИЯ
        -- ══════════════════════════════════════
        CREATE TABLE IF NOT EXISTS units (
            id          SERIAL PRIMARY KEY,
            key         VARCHAR(20) UNIQUE NOT NULL,  -- m2, m, pcs, cm, cm2, kg
            name_ru     VARCHAR(50) NOT NULL,          -- м², м, шт, см, см², кг
            name_uz     VARCHAR(50) NOT NULL,          -- m², m, dona, sm, sm², kg
            symbol_ru   VARCHAR(10) NOT NULL,          -- м²
            symbol_uz   VARCHAR(10) NOT NULL,          -- m²
            created_at  TIMESTAMP DEFAULT NOW()
        );

        -- ══════════════════════════════════════
        --  ЦЕНЫ НА УСЛУГИ
        -- ══════════════════════════════════════
        CREATE TABLE IF NOT EXISTS prices (
            id              SERIAL PRIMARY KEY,
            service_key     VARCHAR(30) NOT NULL,
            type_key        VARCHAR(20) NOT NULL,
            price           INT NOT NULL,
            unit            VARCHAR(20) DEFAULT 'sum/m2',
            unit_key        VARCHAR(20) DEFAULT 'm2',
            min_order       NUMERIC(10,2) DEFAULT NULL,
            updated_at      TIMESTAMP DEFAULT NOW(),
            UNIQUE(service_key, type_key)
        );

        -- Добавляем новые колонки если их нет (для существующих таблиц)
        ALTER TABLE prices ADD COLUMN IF NOT EXISTS unit_key VARCHAR(20) DEFAULT 'm2';
        ALTER TABLE prices ADD COLUMN IF NOT EXISTS min_order NUMERIC(10,2) DEFAULT NULL;

        -- Снять старый CHECK на status (чтобы добавить drying)
        DO $$ DECLARE r RECORD;
        BEGIN
          FOR r IN SELECT conname FROM pg_constraint
                   WHERE conrelid='orders'::regclass AND contype='c' AND conname LIKE '%status%'
          LOOP EXECUTE format('ALTER TABLE orders DROP CONSTRAINT %I', r.conname);
          END LOOP;
        END $$;
        -- Добавить CHECK со всеми статусами включая drying
        ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_status_check;
        ALTER TABLE orders ADD CONSTRAINT orders_status_check CHECK (status IN (
          'new','confirmed','pickup','received','washing','drying','packing','ready','delivery','delivered','cancelled'
        ));

        -- Индексы
        CREATE INDEX IF NOT EXISTS idx_orders_client   ON orders(client_tg_id);
        CREATE INDEX IF NOT EXISTS idx_orders_status   ON orders(status);
        CREATE INDEX IF NOT EXISTS idx_orders_branch   ON orders(branch);
        CREATE INDEX IF NOT EXISTS idx_orders_created  ON orders(created_at);
        CREATE INDEX IF NOT EXISTS idx_clients_tg_id   ON clients(tg_id);
        """)

        # Дефолтные единицы измерения
        units_count = await conn.fetchval("SELECT COUNT(*) FROM units")
        if units_count == 0:
            default_units = [
                ("m2",  "Квадратный метр", "kvadrat metr",  "м²",  "m²"),
                ("m",   "Метр",            "metr",          "м",   "m"),
                ("pcs", "Штука",           "dona",          "шт",  "dona"),
                ("cm",  "Сантиметр",       "santimetr",     "см",  "sm"),
                ("cm2", "Кв. сантиметр",   "kv. santimetr", "см²", "sm²"),
                ("kg",  "Килограмм",       "kilogramm",     "кг",  "kg"),
            ]
            await conn.executemany("""
                INSERT INTO units (key, name_ru, name_uz, symbol_ru, symbol_uz)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (key) DO NOTHING
            """, default_units)

        # Дефолтные цены — добавляются только если таблица prices ещё пуста
        count = await conn.fetchval("SELECT COUNT(*) FROM prices")
        if count == 0:
            defaults = [
                ("carpet",      "standard", 12000, "sum/m2", "m2",  10.0),
                ("carpet",      "express",  16000, "sum/m2", "m2",  10.0),
                ("carpet_home", "standard", 14000, "sum/m2", "m2",  10.0),
                ("carpet_home", "express",  18000, "sum/m2", "m2",  10.0),
                ("sofa",        "standard", 16000, "sum/m2", "m2",  None),
                ("sofa",        "express",  20000, "sum/m2", "m2",  None),
                ("mattress",    "standard", 16000, "sum/m2", "m2",  None),
                ("mattress",    "express",  20000, "sum/m2", "m2",  None),
                ("curtains",    "standard", 14000, "sum/m2", "m2",  None),
                ("curtains",    "express",  18000, "sum/m2", "m2",  None),
            ]
            await conn.executemany("""
                INSERT INTO prices (service_key, type_key, price, unit, unit_key, min_order)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (service_key, type_key) DO NOTHING
            """, defaults)

    # Миграции для существующих БД
    migrations = [
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS tg_phone VARCHAR(20) DEFAULT NULL",
        "ALTER TABLE clients ADD COLUMN IF NOT EXISTS language VARCHAR(5) DEFAULT 'ru'",
    ]
    async with pool.acquire() as conn:
        for sql in migrations:
            try:
                await conn.execute(sql)
            except Exception:
                pass

    logging.info("✅ Tables created/verified")


# ══════════════════════════════════════
#  КЛИЕНТЫ
# ══════════════════════════════════════
async def upsert_client(tg_id, username, first_name, last_name, phone=None, lang="ru"):
    if not pool: return
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO clients (tg_id, tg_username, first_name, last_name, phone, lang, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT (tg_id) DO UPDATE SET
                tg_username  = EXCLUDED.tg_username,
                first_name   = EXCLUDED.first_name,
                last_name    = EXCLUDED.last_name,
                lang         = EXCLUDED.lang,
                phone        = COALESCE(EXCLUDED.phone, clients.phone),
                updated_at   = NOW()
        """, tg_id, username, first_name, last_name, phone, lang)


# ══════════════════════════════════════
#  ЗАКАЗЫ
# ══════════════════════════════════════
async def get_next_order_num(prefix: str = "ARTEZ") -> str:
    """Возвращает следующий номер заказа на основе данных в БД (переживает редеплои)"""
    if not pool:
        return f"{prefix}-1001"
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT order_num FROM orders
            WHERE order_num LIKE $1
            ORDER BY id DESC
            LIMIT 1
        """, f"{prefix}-%")
        if row and row["order_num"]:
            try:
                last_num = int(row["order_num"].split("-")[-1])
            except (ValueError, IndexError):
                last_num = 1000
        else:
            last_num = 1000
        return f"{prefix}-{last_num + 1}"


async def save_order(data: dict) -> str:
    if not pool: return data.get("order_num","")
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO orders (
                order_num, source,
                client_tg_id, client_tg_username, client_first_name, client_last_name, client_phone,
                branch, city, address, location, service, pickup_date, pickup_time, note,
                status
            ) VALUES (
                $1, $2,
                $3, $4, $5, $6, $7,
                $8, $9, $10, $11, $12, $13, $14, $15,
                'new'
            )
            ON CONFLICT (order_num) DO NOTHING
        """,
            data.get("order_num"),
            data.get("source","bot"),
            data.get("client_tg_id"),
            data.get("client_tg_username"),
            data.get("client_first_name"),
            data.get("client_last_name"),
            data.get("phone"),
            data.get("branch"),
            data.get("city"),
            data.get("address"),
            data.get("location"),
            data.get("service"),
            data.get("pickup_date"),
            data.get("pickup_time"),
            data.get("note"),
        )
        # Увеличиваем счётчик заказов клиента
        await conn.execute("""
            UPDATE clients SET total_orders = total_orders + 1, updated_at = NOW()
            WHERE tg_id = $1
        """, data.get("client_tg_id"))
        # Пишем в историю
        await conn.execute("""
            INSERT INTO order_status_history (order_num, new_status, note)
            VALUES ($1, 'new', 'Заявка создана через бот')
        """, data.get("order_num"))
    return data.get("order_num")


async def update_order_status(order_num: str, new_status: str,
                               by_tg_id=None, by_name=None, note=None,
                               extra: dict = None):
    """Обновить статус заказа и записать в историю"""
    if not pool: return
    async with pool.acquire() as conn:
        # Берём старый статус
        old = await conn.fetchrow("SELECT status FROM orders WHERE order_num=$1", order_num)
        old_status = old["status"] if old else None

        # Базовое обновление
        set_parts = ["status=$1", "updated_at=NOW()"]
        vals = [new_status]

        # Дополнительные поля в зависимости от статуса
        if extra:
            i = 2
            for k, v in extra.items():
                set_parts.append(f"{k}=${i}")
                vals.append(v)
                i += 1

        vals.append(order_num)
        await conn.execute(
            f"UPDATE orders SET {', '.join(set_parts)} WHERE order_num=${len(vals)}",
            *vals
        )
        # История
        await conn.execute("""
            INSERT INTO order_status_history
            (order_num, old_status, new_status, changed_by_tg_id, changed_by_name, note)
            VALUES ($1,$2,$3,$4,$5,$6)
        """, order_num, old_status, new_status, by_tg_id, by_name, note)


async def get_order(order_num: str):
    if not pool: return None
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM orders WHERE order_num=$1", order_num)


async def get_orders_by_status(status: str, branch: str = None):
    if not pool: return []
    async with pool.acquire() as conn:
        if branch:
            return await conn.fetch(
                "SELECT * FROM orders WHERE status=$1 AND branch=$2 ORDER BY created_at DESC",
                status, branch
            )
        return await conn.fetch(
            "SELECT * FROM orders WHERE status=$1 ORDER BY created_at DESC", status
        )


async def get_client_by_tg_id(tg_id: int) -> dict | None:
    if not pool: return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM clients WHERE tg_id=$1", tg_id)
        return dict(row) if row else None

async def update_client_tg_phone(tg_id: int, tg_phone: str):
    """Сохраняет верифицированный Telegram-номер (из contact share) в clients.tg_phone."""
    if not pool: return
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE clients SET tg_phone=$2, updated_at=NOW() WHERE tg_id=$1",
            tg_id, tg_phone)

async def get_client_tg_phone(tg_id: int) -> str | None:
    """Возвращает сохранённый верифицированный номер клиента (tg_phone или phone)."""
    if not pool: return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT tg_phone, phone FROM clients WHERE tg_id=$1", tg_id)
    if not row: return None
    return row["tg_phone"] or row["phone"] or None

async def get_client_orders(tg_id: int):
    if not pool: return []
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM orders WHERE client_tg_id=$1 ORDER BY created_at DESC LIMIT 10",
            tg_id
        )

async def get_stats(branch: str = None):
    """Статистика заказов"""
    if not pool: return {}
    async with pool.acquire() as conn:
        where = f"WHERE branch='{branch}'" if branch else ""
        row = await conn.fetchrow(f"""
            SELECT
                COUNT(*) FILTER (WHERE status='new')       AS new_count,
                COUNT(*) FILTER (WHERE status='delivered') AS done_count,
                COUNT(*) FILTER (WHERE status='cancelled') AS cancel_count,
                COUNT(*)                                    AS total
            FROM orders {where}
        """)
        return dict(row) if row else {}


# ══════════════════════════════════════
#  ЦЕНЫ НА УСЛУГИ
# ══════════════════════════════════════
async def get_all_prices() -> dict:
    """Возвращает все цены в виде {service_key: {type_key: {"price":.., "unit":.., "unit_key":.., "min_order":..}}}"""
    if not pool:
        return {}
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT service_key, type_key, price, unit, unit_key, min_order FROM prices")
    result = {}
    for r in rows:
        result.setdefault(r["service_key"], {})[r["type_key"]] = {
            "price": r["price"],
            "unit": r["unit"],
            "unit_key": r["unit_key"],
            "min_order": float(r["min_order"]) if r["min_order"] is not None else None,
        }
    return result


async def get_price(service_key: str, type_key: str):
    """Возвращает цену (int) для конкретной услуги и типа, либо None если не найдено"""
    if not pool:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT price FROM prices WHERE service_key=$1 AND type_key=$2",
            service_key, type_key
        )
    return row["price"] if row else None


async def set_price(service_key: str, type_key: str, price: int, unit: str = None,
                     unit_key: str = None, min_order=None) -> bool:
    """Устанавливает (или создаёт) цену для услуги/типа. Возвращает True при успехе."""
    if not pool:
        return False
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO prices (service_key, type_key, price, unit, unit_key, min_order, updated_at)
            VALUES ($1, $2, $3,
                    COALESCE($4, 'sum/m2'),
                    COALESCE($5, 'm2'),
                    $6, NOW())
            ON CONFLICT (service_key, type_key) DO UPDATE SET
                price      = EXCLUDED.price,
                unit       = COALESCE($4, prices.unit),
                unit_key   = COALESCE($5, prices.unit_key),
                min_order  = $6,
                updated_at = NOW()
        """, service_key, type_key, price, unit, unit_key, min_order)
    return True


# ══════════════════════════════════════
#  ЕДИНИЦЫ ИЗМЕРЕНИЯ
# ══════════════════════════════════════
async def get_all_units():
    """Возвращает список всех единиц измерения"""
    if not pool:
        return []
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM units ORDER BY id")


async def get_unit(key: str):
    if not pool:
        return None
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM units WHERE key=$1", key)


async def add_unit(key: str, name_ru: str, name_uz: str, symbol_ru: str, symbol_uz: str) -> bool:
    if not pool:
        return False
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO units (key, name_ru, name_uz, symbol_ru, symbol_uz)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (key) DO UPDATE SET
                name_ru = EXCLUDED.name_ru,
                name_uz = EXCLUDED.name_uz,
                symbol_ru = EXCLUDED.symbol_ru,
                symbol_uz = EXCLUDED.symbol_uz
        """, key, name_ru, name_uz, symbol_ru, symbol_uz)
    return True


async def delete_unit(key: str) -> bool:
    if not pool:
        return False
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM units WHERE key=$1", key)
    return result != "DELETE 0"


# ══════════════════════════════════════
#  СОТРУДНИКИ (водители и т.п.)
# ══════════════════════════════════════
async def add_staff(tg_id: int, first_name: str, role: str = "driver", last_name: str = "", tg_username: str = "") -> bool:
    """Добавляет или обновляет сотрудника. Возвращает True при успехе."""
    if not pool:
        return False
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO staff (tg_id, tg_username, first_name, last_name, role, is_active)
            VALUES ($1, $2, $3, $4, $5, TRUE)
            ON CONFLICT (tg_id) DO UPDATE SET
                first_name  = EXCLUDED.first_name,
                last_name   = EXCLUDED.last_name,
                tg_username = EXCLUDED.tg_username,
                role        = EXCLUDED.role,
                is_active   = TRUE
        """, tg_id, tg_username, first_name, last_name, role)
    return True


async def remove_staff(tg_id: int) -> bool:
    """Деактивирует сотрудника (is_active=FALSE)."""
    if not pool:
        return False
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE staff SET is_active=FALSE WHERE tg_id=$1", tg_id
        )
    return result != "UPDATE 0"


async def get_staff_by_role(role: str):
    """Возвращает список активных сотрудников с указанной ролью."""
    if not pool:
        return []
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM staff WHERE role=$1 AND is_active=TRUE ORDER BY first_name",
            role
        )


async def is_client_blocked(tg_id: int) -> bool:
    if not pool: return False
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT blocked FROM clients WHERE tg_id=$1", tg_id)
    return bool(row and row.get("blocked"))

async def get_client_lang(tg_id: int):
    """Возвращает сохранённый язык клиента ('ru'/'uz') или None, если клиент не найден."""
    if not pool:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT lang FROM clients WHERE tg_id=$1", tg_id)
    return row["lang"] if row else None


async def set_client_lang(tg_id: int, lang: str):
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE clients SET lang=$1, updated_at=NOW() WHERE tg_id=$2",
            lang, tg_id
        )


# ══════════════════════════════════════
#  CRM SYNC (shared crm_clients table)
# ══════════════════════════════════════
# ══════════════════════════════════════
#  ЛИДЫ (для обработки кнопки "Взять лид" в боте)
# ══════════════════════════════════════
async def get_staff_by_tg_id_for_lead(tg_id: int):
    """Возвращает сотрудника artez_api по tg_id из таблицы staff."""
    if not pool: return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, first_name, last_name, gender, role, login FROM staff WHERE tg_id=$1 AND active=TRUE",
            str(tg_id))
        return dict(row) if row else None

async def take_lead(lead_id: int, staff_id: int, staff_name: str):
    """Назначает лид на сотрудника. Возвращает ('ok'|'already_mine'|'taken', taker_name, lead_code)."""
    if not pool: return ('error', '', '')
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT assigned_to, lead_code FROM leads WHERE id=$1", lead_id)
        if not row:
            return ('not_found', '', '')
        if row['assigned_to'] and row['assigned_to'] != staff_id:
            taker = await conn.fetchrow(
                "SELECT first_name, last_name, gender FROM staff WHERE id=$1", row['assigned_to'])
            taker_name = (f"{taker['first_name'] or ''} {taker['last_name'] or ''}".strip()
                          if taker else 'другой сотрудник')
            taker_verb = 'Взяла' if taker and taker.get('gender') == 'F' else 'Взял'
            return ('taken', taker_name, taker_verb)
        if row['assigned_to'] == staff_id:
            return ('already_mine', '', '')
        await conn.execute("UPDATE leads SET assigned_to=$1, updated_at=NOW() WHERE id=$2", staff_id, lead_id)
        try:
            await conn.execute("""
                INSERT INTO lead_calls (lead_id, staff_id, action, note, created_at)
                VALUES ($1,$2,'note',$3,NOW())
            """, lead_id, staff_id, f"Лид взят через Telegram: {staff_name}")
        except Exception:
            pass
        return ('ok', '', '')


async def upsert_crm_client(phone: str, first_name: str = "", last_name: str = "",
                             tg_id: int = None, tg_username: str = None,
                             source: str = "bot"):
    """Синхронизирует клиента в общую CRM-таблицу crm_clients."""
    if not pool or not phone:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO crm_clients (phone, first_name, last_name, tg_id, tg_username, source)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (phone) DO UPDATE SET
                    first_name  = CASE WHEN $2 != '' THEN $2 ELSE crm_clients.first_name END,
                    last_name   = CASE WHEN $3 != '' THEN $3 ELSE crm_clients.last_name END,
                    tg_id       = COALESCE($4, crm_clients.tg_id),
                    tg_username = CASE WHEN $5 IS NOT NULL AND $5 != ''
                                       THEN $5 ELSE crm_clients.tg_username END,
                    orders_count = (SELECT COUNT(*) FROM orders WHERE client_phone = $1),
                    last_order_at = NOW(),
                    updated_at  = NOW()
            """, phone, first_name or "", last_name or "", tg_id, tg_username, source)
    except Exception as e:
        logging.warning(f"upsert_crm_client error: {e}")
