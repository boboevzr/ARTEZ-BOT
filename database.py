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
                                    'received',   -- Принят на мастерскую
                                    'washing',    -- В чистке
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

        -- Индексы
        CREATE INDEX IF NOT EXISTS idx_orders_client   ON orders(client_tg_id);
        CREATE INDEX IF NOT EXISTS idx_orders_status   ON orders(status);
        CREATE INDEX IF NOT EXISTS idx_orders_branch   ON orders(branch);
        CREATE INDEX IF NOT EXISTS idx_orders_created  ON orders(created_at);
        CREATE INDEX IF NOT EXISTS idx_clients_tg_id   ON clients(tg_id);
        """)
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
