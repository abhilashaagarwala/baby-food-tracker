from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import psycopg2
import os
import hmac
import hashlib

app = FastAPI()

DB_URL = os.getenv("DATABASE_URL", "postgresql://babyapp:babypass@postgres:5432/babyfoods")
ADMIN_USER = "ruhibaby"
ADMIN_PASS = "ruhibaby"
SECRET_KEY = os.getenv("SECRET_KEY", "changeme-secret-key-abc123")

FOODS_BY_CATEGORY = {
    "Fruits": [
        "Banana", "Apple", "Pear", "Mango", "Peach", "Prune", "Blueberry",
        "Strawberry", "Raspberry", "Watermelon", "Papaya", "Plum", "Pomegranate",
        "Kiwi", "Pineapple", "Coconut", "Cherry", "Grape", "Fig", "Date",
        "Apricot", "Nectarine", "Avocado"
    ],
    "Vegetables": [
        "Sweet Potato", "Carrot", "Pea Puree", "Butternut Squash", "Green Bean",
        "Broccoli", "Spinach", "Zucchini", "Pumpkin", "Beet", "Cauliflower",
        "Kale", "Corn", "Asparagus", "Cucumber", "Bell Pepper", "Tomato",
        "Mushroom", "Celery", "Parsnip", "Turnip", "Leek", "Onion", "Garlic",
        "Ginger", "Fennel", "Potato", "Yam"
    ],
    "Grains and Starches": [
        "Oatmeal", "Rice Cereal", "Barley Cereal", "Quinoa", "Pasta", "Bread",
        "Pita", "Polenta", "Couscous", "Brown Rice", "White Rice", "Sweet Corn"
    ],
    "Protein": [
        "Chicken", "Turkey", "Salmon", "Tuna", "Beef", "Lamb", "Egg Yolk",
        "Whole Egg", "Soft Tofu", "Tempeh", "White Fish", "Beef Liver", "Sardines", "Shrimp"
    ],
    "Legumes, Nuts and Seeds": [
        "Lentils", "Chickpeas", "Black Beans", "Edamame", "Tofu", "Peanut Butter",
        "Almond Butter", "Sunflower Seed Butter", "Tahini", "Hummus", "Chia Seeds",
        "Flaxseed", "Hemp Seeds", "Lentil Soup"
    ],
    "Dairy and Dairy Alternatives": [
        "Greek Yogurt", "Cottage Cheese", "Cheese", "Whole Milk", "Butter",
        "Cream Cheese", "Ricotta", "Goat Cheese", "Cheddar", "Mozzarella",
        "Bone Broth", "Nutritional Yeast", "Seaweed"
    ]
}

bearer_scheme = HTTPBearer(auto_error=False)

def make_token(username: str) -> str:
    return hmac.new(SECRET_KEY.encode(), username.encode(), hashlib.sha256).hexdigest()

def require_auth(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    if not credentials or not hmac.compare_digest(credentials.credentials, make_token(ADMIN_USER)):
        raise HTTPException(status_code=401, detail="Unauthorized")

def get_conn():
    return psycopg2.connect(DB_URL)

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS food_log (
            id SERIAL PRIMARY KEY,
            food TEXT NOT NULL,
            category TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('tried', 'liked', 'not_liked')),
            is_custom BOOLEAN DEFAULT FALSE,
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(food)
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

@app.on_event("startup")
def startup():
    init_db()

@app.get("/", response_class=HTMLResponse)
def index():
    with open("static/index.html") as f:
        return f.read()

# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/login")
def login(body: LoginRequest):
    valid_user = hmac.compare_digest(body.username, ADMIN_USER)
    valid_pass = hmac.compare_digest(body.password, ADMIN_PASS)
    if not (valid_user and valid_pass):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": make_token(ADMIN_USER)}

@app.get("/auth/check")
def auth_check(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    if credentials and hmac.compare_digest(credentials.credentials, make_token(ADMIN_USER)):
        return {"authenticated": True}
    return {"authenticated": False}

# ── Foods (read — public) ─────────────────────────────────────────────────────

@app.get("/foods")
def get_foods():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT food, category, status, is_custom FROM food_log")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    logged = {r[0]: {"category": r[1], "status": r[2], "is_custom": r[3]} for r in rows}

    result = {}
    for category, foods in FOODS_BY_CATEGORY.items():
        result[category] = []
        for food in foods:
            entry = logged.get(food)
            result[category].append({
                "food": food,
                "status": entry["status"] if entry else None,
                "is_custom": False
            })

    for food, data in logged.items():
        if data["is_custom"]:
            cat = data["category"]
            if cat not in result:
                result[cat] = []
            result[cat].append({"food": food, "status": data["status"], "is_custom": True})

    return result

# ── Foods (write — requires auth) ─────────────────────────────────────────────

class StatusUpdate(BaseModel):
    status: str
    category: str

class CustomFood(BaseModel):
    food: str
    category: str

@app.post("/foods/{food}/status", dependencies=[Depends(require_auth)])
def set_status(food: str, body: StatusUpdate):
    if body.status not in ("tried", "liked", "not_liked"):
        raise HTTPException(status_code=400, detail="Invalid status")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO food_log (food, category, status)
        VALUES (%s, %s, %s)
        ON CONFLICT (food) DO UPDATE SET status = EXCLUDED.status, updated_at = NOW()
    """, (food, body.category, body.status))
    conn.commit()
    cur.close()
    conn.close()
    return {"food": food, "status": body.status}

@app.delete("/foods/{food}/status", dependencies=[Depends(require_auth)])
def remove_status(food: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT is_custom FROM food_log WHERE food = %s", (food,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    cur.execute("DELETE FROM food_log WHERE food = %s", (food,))
    conn.commit()
    cur.close()
    conn.close()
    return {"food": food, "removed": True}

@app.post("/foods/custom", dependencies=[Depends(require_auth)])
def add_custom(body: CustomFood):
    food = body.food.strip()
    if not food:
        raise HTTPException(status_code=400, detail="Food name cannot be empty")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO food_log (food, category, status, is_custom)
        VALUES (%s, %s, 'tried', TRUE)
        ON CONFLICT (food) DO NOTHING
    """, (food, body.category))
    conn.commit()
    cur.close()
    conn.close()
    return {"food": food, "category": body.category}
