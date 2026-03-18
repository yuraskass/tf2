from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector
from fastapi import Body
from pydantic import BaseModel
from fastapi.responses import RedirectResponse
import requests
import threading
import time
from yookassa import Configuration, Payment
import uuid
Configuration.account_id = '1303074'
Configuration.secret_key = 'test_OiewiLMBt-oAz7nzN08eegZ27OqqQabvbrJlptWevfw'
BASE_URL = "http://127.0.0.1:8000"
current_key_price = "0.0"
current_ticket_price = "0.0"

class PurchaseRequest(BaseModel):
    amount: int

class SaleRequest(BaseModel):
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
        port=3307,
        connect_timeout=5
    )


def update_steam_price():
    global current_key_price
    global current_ticket_price
    # Убедись, что KEY_ID определен в начале файла (обычно это 1)
    url = "https://steamcommunity.com/market/priceoverview/?appid=440&currency=5&market_hash_name=Mann%20Co.%20Supply%20Crate%20Key"

    while True:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "lowest_price" in data:
                    raw_price = data["lowest_price"]
                    clean_price = "".join(c for c in raw_price if c.isdigit() or c == ',').replace(',', '.')
                    current_key_price = float(clean_price)

                    # --- ОБНОВЛЕНИЕ БАЗЫ ДАННЫХ ---
                    conn = get_db()
                    cursor = conn.cursor()
                    try:
                        # Обновляем колонку price для предмета с KEY_ID
                        query = "UPDATE items SET price = %s WHERE id = %s"
                        cursor.execute(query, (current_key_price, KEY_ID))
                        conn.commit()
                        print(f"--- [БАЗА] Цена ключа в БД обновлена: {current_key_price} ---")
                    except Exception as db_err:
                        print(f"Ошибка записи в БД: {db_err}")
                    finally:
                        cursor.close()
                        conn.close()
                    # ------------------------------

            else:
                print(f"--- [ОШИБКА] Steam ответил кодом: {response.status_code} ---")

        except Exception as e:
            print(f"Ошибка обновления цены: {e}")
        urll = "https://steamcommunity.com/market/priceoverview/?appid=440&currency=5&market_hash_name=Tour%20of%20Duty%20Ticket"

        try:
            response = requests.get(urll, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "lowest_price" in data:
                    raw_price = data["lowest_price"]
                    clean_price = "".join(c for c in raw_price if c.isdigit() or c == ',').replace(',', '.')
                    current_ticket_price = float(clean_price)

                    # --- ОБНОВЛЕНИЕ БАЗЫ ДАННЫХ ---
                    conn = get_db()
                    cursor = conn.cursor()
                    try:
                        # Обновляем колонку price для предмета с KEY_ID
                        query = "UPDATE items SET price = %s WHERE id = %s"
                        cursor.execute(query, (current_ticket_price, TICKET_ID))
                        conn.commit()
                        print(f"--- [БАЗА] Цена билета в БД обновлена: {current_ticket_price} ---")
                    except Exception as db_err:
                        print(f"Ошибка записи в БД: {db_err}")
                    finally:
                        cursor.close()
                        conn.close()
                    # ------------------------------

            else:
                print(f"--- [ОШИБКА] Steam ответил кодом: {response.status_code} ---")

        except Exception as e:
            print(f"Ошибка обновления цены: {e}")

        time.sleep(60)




threading.Thread(target=update_steam_price, daemon=True).start()



@app.post("/api/create-payment")
async def create_payment(request: PurchaseRequest):
    # Рассчитываем сумму (например, количество ключей * цену из твоей переменной)
    # Используем цену покупки (key-buy), которую ты считал ранее
    total_amount = round(float(current_key_price * 0.74) * request.amount, 2)

    if total_amount < 1.0:
        raise HTTPException(status_code=400, detail="Слишком маленькая сумма")

    idempotence_key = str(uuid.uuid4()) # Ключ защиты от повторных списаний

    try:
        payment = Payment.create({
            "amount": {
                "value": str(total_amount),
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": f"{BASE_URL}" # Куда вернуть юзера после оплаты
            },
            "capture": True, # Списать деньги сразу
            "description": f"Покупка ключей TF2 ({request.amount} шт.)"
        }, idempotence_key)

        # Возвращаем ссылку на оплату фронтенду
        return {
            "payment_id": payment.id,
            "confirmation_url": payment.confirmation.confirmation_url
        }

    except Exception as e:
        print(f"Ошибка ЮKassa: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при создании платежа")


@app.get("/api/check-payment/{payment_id}")
async def check_payment(payment_id: str):
    try:
        # Запрашиваем данные о платеже у ЮKassa
        payment = Payment.find_one(payment_id)

        if payment.status == 'succeeded':
            # ТУТ ЛОГИКА: Деньги пришли!
            # Можно обновить баланс в БД или выдать товар
            return {
                "status": "paid",
                "message": "Оплата прошла успешно!",
                "amount": payment.amount.value
            }

        elif payment.status == 'pending':
            return {"status": "pending", "message": "Ожидаем оплату от пользователя..."}

        elif payment.status == 'canceled':
            return {"status": "canceled", "message": "Платеж отменен или произошла ошибка."}

        else:
            return {"status": payment.status, "message": "Платеж в обработке."}

    except Exception as e:
        print(f"Ошибка проверки платежа: {e}")
        raise HTTPException(status_code=500, detail="Не удалось проверить статус")

@app.get("/api/get-price")
async def get_price():

    return {
        "ticket-SELL": round(current_ticket_price * 0.79, 2),
        "key-SELL": round(current_key_price * 0.79, 2),
        "ticket-buy": round(current_ticket_price * 0.74, 2),
        "key-buy": round(current_key_price * 0.74, 2)
    }


@app.get("/api/auth/login")
async def steam_login():
    from urllib.parse import urlencode

    steam_openid_url = "https://steamcommunity.com/openid/login"

    
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": f"{BASE_URL}/api/auth/callback",
        "openid.realm": BASE_URL,
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select"
    }

    
    query_string = urlencode(params)
    auth_url = f"{steam_openid_url}?{query_string}"

    return RedirectResponse(auth_url)


STEAM_API_KEY = "0C382E6F13B23067DAFF84CD09F7027C"


@app.get("/api/auth/callback")
async def steam_callback(request: Request):
    params = dict(request.query_params)
    claimed_id = params.get("openid.claimed_id")

    # Получаем IP напрямую из объекта запроса
    client_ip = request.client.host

    if not claimed_id:
        raise HTTPException(status_code=400, detail="Ошибка входа через Steam")

    steam_id = claimed_id.split("/")[-1]
    username = "Anonymous"

    try:
        api_url = f"https://api.steampowered.com{STEAM_API_KEY}&steamids={steam_id}"
        resp = requests.get(api_url)
        data = resp.json()
        if 'response' in data and 'players' in data['response'] and len(data['response']['players']) > 0:
            username = data['response']['players'][0].get('personaname', 'Anonymous')
    except Exception as e:
        print(f"Ошибка запроса к Steam: {e}")

    conn = get_db()
    cursor = conn.cursor()
    try:
        # Добавляем last_ip в INSERT и в UPDATE
        query = """
            INSERT INTO users (steam_id, username, last_ip) 
            VALUES (%s, %s, %s) 
            ON DUPLICATE KEY UPDATE 
                username = VALUES(username), 
                last_ip = VALUES(last_ip),
                last_login = CURRENT_TIMESTAMP
        """
        cursor.execute(query, (steam_id, username, client_ip))
        conn.commit()
    except Exception as e:
        print(f"Ошибка БД при сохранении IP ({client_ip}): {e}")
    finally:
        cursor.close()
        conn.close()

    return {
        "status": "success",
        "steam_id": steam_id,
        "username": username,
        "ip": client_ip,
        "message": f"Привет, {username}! Вы залогинились с IP {client_ip}."
    }


# Общая логика покупки
async def process_purchase(item_id: int, amount: int, request: Request):
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Количество должно быть больше 0")

    client_ip = request.client.host
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
  
        cursor.execute("SELECT quantity FROM items WHERE id = %s", (item_id,))
        item = cursor.fetchone()

        if not item:
            raise HTTPException(status_code=404, detail="Товар не найден")

        if item['quantity'] < amount:
            raise HTTPException(status_code=400, detail=f"Недостаточно товара! Осталось: {item['quantity']}")

        
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
async def process_sale(item_id: int, amount: int,  request: Request):
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Количество должно быть больше 0")

    client_ip = request.client.host
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
      
        cursor.execute("SELECT sold_count FROM items WHERE id = %s", (item_id,))
        item = cursor.fetchone()

        if not item:
            raise HTTPException(status_code=404, detail="Товар не найден")

        if item['sold_count'] < amount:
            raise HTTPException(status_code=400, detail=f"Недостаточно проданных товаров для возврата! В базе всего: {item['sold_count']}")

        
        cursor.execute("""
            UPDATE items 
            SET quantity = quantity + %s, sold_count = sold_count - %s 
            WHERE id = %s
        """, (amount, amount, item_id))

       
        cursor.execute("""
            INSERT INTO sales (item_id, seller_ip, amount) 
            VALUES (%s, %s, %s)
        """, (item_id,  client_ip,  amount))

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

@app.get("/api/items-count")
async def get_items_count():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT name,quantity,sold_count FROM items ")
    items = cursor.fetchall()
    cursor.close()
    conn.close()
    return(items)



@app.post("/api/buy/tickets")
async def buy_tickets(request: Request, data: PurchaseRequest): # Теперь берем данные из модели
    return await process_purchase(TICKET_ID, data.amount, request)
@app.post("/api/sale/tickets")
async def sale_tickets(request: Request, data: SaleRequest): # Теперь берем данные из модели
    return await process_sale(TICKET_ID, data.amount, request)



@app.post("/api/sale/keys")
async def sale_keys(request: Request, data: SaleRequest): # Теперь берем данные из модели
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
