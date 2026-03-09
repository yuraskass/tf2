from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Настройки ID предметов (посмотри их в своей таблице items)
TICKET_ID = 1
KEY_ID = 2


def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="tf2_lavk",
        connect_timeout=5
    )


# Общая логика покупки
async def process_purchase(item_id: int, amount: int, request: Request):
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Количество должно быть больше 0")

    client_ip = request.client.host
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        # Проверяем наличие нужного количества
        cursor.execute("SELECT quantity FROM items WHERE id = %s", (item_id,))
        item = cursor.fetchone()

        if not item:
            raise HTTPException(status_code=404, detail="Товар не найден")

        if item['quantity'] < amount:
            raise HTTPException(status_code=400, detail=f"Недостаточно товара! Осталось: {item['quantity']}")

        # Обновляем остаток и счетчик продаж
        cursor.execute("""
            UPDATE items 
            SET quantity = quantity - %s, sold_count = sold_count + %s 
            WHERE id = %s
        """, (amount, amount, item_id))

        # Логируем покупку
        cursor.execute(
            "INSERT INTO purchases (item_id, buyer_ip) VALUES (%s, %s)",
            (item_id, client_ip)
        )

        conn.commit()
        return {"status": "success", "message": f"Куплено {amount} шт.", "your_ip": client_ip}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


@app.get("/api/items")
async def get_items():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM items")
    items = cursor.fetchall()
    cursor.close()
    conn.close()
    return items


# Кнопка 1: Купить билеты
@app.post("/api/buy/tickets")
async def buy_tickets(request: Request, amount: int = 1):
    return await process_purchase(TICKET_ID, amount, request)


# Кнопка 2: Купить ключи
@app.post("/api/buy/keys")
async def buy_keys(request: Request, amount: int = 1):
    return await process_purchase(KEY_ID, amount, request)


@app.get("/api/solds")
async def get_history():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT p.id, i.name, p.buyer_ip, p.purchase_date 
        FROM purchases p
        JOIN items i ON p.item_id = i.id
        ORDER BY p.purchase_date DESC 
        LIMIT 10
    """
    cursor.execute(query)
    solds = cursor.fetchall()
    cursor.close()
    conn.close()
    return solds
