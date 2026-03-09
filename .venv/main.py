from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector
from fastapi import Body
from pydantic import BaseModel

class PurchaseRequest(BaseModel):
    amount: int
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


TICKET_ID = 2
KEY_ID = 1


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

        
        cursor.execute(
            "INSERT INTO purchases (item_id, buyer_ip, amount) VALUES (%s, %s, %s)",
            (item_id, client_ip, amount)
        )

        conn.commit()
        return {"status": "success", "message": f"Куплено {amount} шт.", "your_ip": client_ip}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
async def process_sale(item_id: int, amount: int, request: Request):
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Количество должно быть больше 0")

    client_ip = request.client.host
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        # Проверяем наличие нужного количества
        cursor.execute("SELECT sold_count FROM items WHERE id = %s", (item_id,))
        item = cursor.fetchone()

        if not item:
            raise HTTPException(status_code=404, detail="Товар не найден")

        if item['sold_count'] < amount:
            raise HTTPException(status_code=400, detail=f"Недостаточно товара! Осталось: {item['sold_count']}")

        # Обновляем остаток и счетчик продаж
        cursor.execute("""
            UPDATE items 
            SET quantity = quantity + %s, sold_count = sold_count - %s 
            WHERE id = %s
        """, (amount, amount, item_id))

        # Логируем покупку
        cursor.execute(
            "INSERT INTO sales (item_id, seller_ip, amount) VALUES (%s, %s, %s)",
            (item_id, client_ip, amount)
        )

        conn.commit()
        return {"status": "success", "message": f"Продано {amount} шт.", "your_ip": client_ip}

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



@app.post("/api/buy/tickets")
async def buy_tickets(request: Request, data: PurchaseRequest): # Теперь берем данные из модели
    return await process_purchase(TICKET_ID, data.amount, request)
@app.post("/api/sale/tickets")
async def sale_tickets(request: Request, data: PurchaseRequest): # Теперь берем данные из модели
    return await process_sale(TICKET_ID, data.amount, request)



@app.post("/api/sale/keys")
async def sale_keys(request: Request, data: PurchaseRequest): # Теперь берем данные из модели
    return await process_sale(KEY_ID, data.amount, request)

@app.post("/api/buy/keys")
async def buy_keys(request: Request, data: PurchaseRequest): # Теперь берем данные из модели
    return await process_purchase(KEY_ID, data.amount, request)



@app.get("/api/solds")
async def get_history():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT p.amount,p.id, i.name, p.buyer_ip, p.purchase_date 
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
@app.get("/api/purch")
async def get_purch():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    # Используем правильные имена столбцов из твоего скриншота базы
    query = """
        SELECT 
            s.id, 
            s.amount, 
            i.name as item_name, 
            s.seller_name, 
            s.seller_ip, 
            s.sale_date 
        FROM sales s
        JOIN items i ON s.item_id = i.id
        ORDER BY s.sale_date DESC 
        LIMIT 10
    """
    try:
        cursor.execute(query)
        solds = cursor.fetchall()
        return solds
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка БД: {str(e)}")
    finally:
        cursor.close()
        conn.close()
