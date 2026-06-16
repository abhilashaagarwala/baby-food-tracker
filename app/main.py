from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import psycopg2
import os
from datetime import date

app = FastAPI()

DB_URL = os.getenv("DATABASE_URL", "postgresql://babyapp:babypass@postgres:5432/babyfoods")

def get_conn():
    return psycopg2.connect(DB_URL)

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS meals (
            id SERIAL PRIMARY KEY,
            meal_date DATE NOT NULL,
            item TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

@app.on_event("startup")
def startup():
    init_db()

class MealEntry(BaseModel):
    meal_date: date
    item: str

@app.get("/", response_class=HTMLResponse)
def index():
    with open("static/index.html") as f:
        return f.read()

@app.post("/meals")
def add_meal(entry: MealEntry):
    item = entry.item.strip().lower()
    if not item:
        raise HTTPException(status_code=400, detail="Item cannot be empty")

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM meals WHERE LOWER(item) = %s", (item,))
    already_eaten = cur.fetchone()[0] > 0

    cur.execute("INSERT INTO meals (meal_date, item) VALUES (%s, %s) RETURNING id",
                (entry.meal_date, item))
    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    return {"id": new_id, "meal_date": entry.meal_date, "item": item, "already_eaten": already_eaten}

@app.get("/meals")
def list_meals():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, meal_date, item, created_at FROM meals ORDER BY meal_date DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"id": r[0], "meal_date": r[1], "item": r[2], "created_at": r[3]} for r in rows]

@app.get("/meals/count")
def count_unique():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(DISTINCT LOWER(item)) FROM meals")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return {"unique_foods": count}

@app.delete("/meals/{meal_id}")
def delete_meal(meal_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM meals WHERE id = %s", (meal_id,))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Not found")
    conn.commit()
    cur.close()
    conn.close()
    return {"deleted": meal_id}
