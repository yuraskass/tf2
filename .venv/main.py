from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector
from fastapi import Body
from pydantic import BaseModel
from fastapi.responses import RedirectResponse
import requests
BASE_URL = "https://mean-vans-laugh.loca.lt"
class PurchaseRequest(BaseModel):
    amount: int
    buyer_name: str = "Anonymous"
    steam_id: str = None
class SaleRequest(BaseModel):
    amount: int
    buyer_name: str = "Anonymous"
    steam_id: str = None
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Настройки ID предметов (посмотри их в своей таблице items)
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


@app.get("/api/auth/login")
async def steam_login():
    from urllib.parse import urlencode

    steam_openid_url = "https://steamcommunity.com/openid/login"

    # ПРОВЕРЬ КАЖДУЮ БУКВУ ТУТ:
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": f"{BASE_URL}/api/auth/callback",
        "openid.realm": BASE_URL,
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select"
    }

    # Используем urlencode, чтобы спецсимволы в BASE_URL не ломали ссылку
    query_string = urlencode(params)
    auth_url = f"{steam_openid_url}?{query_string}"

    return RedirectResponse(auth_url)


STEAM_API_KEY = "0C382E6F13B23067DAFF84CD09F7027C"  # Вставь свой ключ сюда


@app.get("/api/auth/callback")
async def steam_callback(request: Request):
    params = dict(request.query_params)
    claimed_id = params.get("openid.claimed_id")

    if not claimed_id:
        raise HTTPException(status_code=400, detail="Ошибка входа через Steam")

    # 1. Получаем SteamID64
    steam_id = claimed_id.split("/")[-1]

    # 2. Получаем данные профиля (Имя и Аватарку) через Steam API
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

    # 3. СОХРАНЯЕМ В БАЗУ ДАННЫХ
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
        # 1. Проверяем, сколько товара числится как "проданное"
        cursor.execute("SELECT sold_count FROM items WHERE id = %s", (item_id,))
        item = cursor.fetchone()

        if not item:
            raise HTTPException(status_code=404, detail="Товар не найден")

        if item['sold_count'] < amount:
            raise HTTPException(status_code=400, detail=f"Недостаточно проданных товаров для возврата! В базе всего: {item['sold_count']}")

        # 2. Обновляем таблицу предметов (возвращаем на склад, убираем из проданных)
        cursor.execute("""
            UPDATE items 
            SET quantity = quantity + %s, sold_count = sold_count - %s 
            WHERE id = %s
        """, (amount, amount, item_id))

        # 3. Логируем продажу (возврат) в таблицу sales со всеми данными
        # ВАЖНО: используем твое имя колонки seller_name
        cursor.execute("""
            INSERT INTO sales (item_id, seller_name, seller_ip, steam_id, amount) 
            VALUES (%s, %s, %s, %s, %s)
        """, (item_id, seller_name, client_ip, steam_id, amount))

        conn.commit()
        return {
            "status": "success",
            "message": f"Товар успешно возвращен: {amount} шт.",
            "seller": seller_name,
            "steam_id": steam_id
        }

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
async def buy_tickets(request: Request, data: PurchaseRequest): # Теперь берем данные из модели
    return await process_purchase(TICKET_ID, data.amount, request)
@app.post("/api/sale/tickets")
async def sale_tickets(request: Request, data: SaleRequest): # Теперь берем данные из модели
    return await process_sale(TICKET_ID, data.amount, request)


# Кнопка 2: Купить ключи
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