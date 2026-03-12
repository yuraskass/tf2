from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector
from fastapi import Body
from pydantic import BaseModel
from fastapi.responses import RedirectResponse
import requests
import threading
import time
BASE_URL = "https://vast-tools-rule.loca.lt"
current_key_price = "0.00"
current_ticket_price = "0.00"
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

        time.sleep(30)




threading.Thread(target=update_steam_price, daemon=True).start()




@app.get("/api/get-price")
async def get_price():
    return {"ticket": current_ticket_price,"key": current_key_price}


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

    if not claimed_id:
        raise HTTPException(status_code=400, detail="Ошибка входа через Steam")

   
    steam_id = claimed_id.split("/")[-1]

   
    username = "Anonymous"  # Значение по умолчанию
    try:
        api_url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={steam_id}"
        resp = requests.get(api_url)
        data = resp.json()

        # Печатаем ответ в консоль PyCharm, чтобы увидеть ошибку
        print(f"DEBUG STEAM API: {data}")

        if 'response' in data and 'players' in data['response'] and len(data['response']['players']) > 0:
            username = data['response']['players'][0].get('personaname', 'Anonymous')
    except Exception as e:
        print(f"Ошибка запроса к Steam: {e}")

   
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Теперь добавляем и username тоже!
        query = """
            INSERT INTO users (steam_id, username) 
            VALUES (%s, %s) 
            ON DUPLICATE KEY UPDATE 
                username = VALUES(username), 
                last_login = CURRENT_TIMESTAMP
        """
        cursor.execute(query, (steam_id, username))
        conn.commit()
    except Exception as e:
        print(f"Ошибка БД при сохранении юзера: {e}")
    finally:
        cursor.close()
        conn.close()

    return {
        "status": "success",
        "steam_id": steam_id,
        "username": username,
        "message": f"Привет, {username}! вы залогинились!."
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
