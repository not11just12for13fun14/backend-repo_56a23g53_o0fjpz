import os
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

from database import create_document

app = FastAPI(title="Kollny EXPRESS API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RecipeRequest(BaseModel):
    ingredients: List[str]
    healthy_only: bool = False
    difficulty: Optional[str] = None  # "easy" | "medium" | "hard"

class Recipe(BaseModel):
    title: str
    ingredients: List[str]
    missing_ingredients: List[str]
    steps: List[str]
    cooking_time_minutes: int
    difficulty: str
    is_healthy: bool


def simple_recipe_engine(pantry: List[str]) -> List[Recipe]:
    """
    A lightweight, deterministic rules-based recipe engine using common pantry items.
    In a production app, you'd replace this with a model or external API + DB of recipes.
    """
    pantry_set = {i.strip().lower() for i in pantry if i.strip()}

    catalog = [
        {
            "title": "Veggie Omelette",
            "ingredients": ["eggs", "onion", "tomato", "spinach", "olive oil", "salt", "pepper"],
            "steps": [
                "Whisk eggs with salt and pepper",
                "Saute onion, tomato, spinach in olive oil",
                "Pour eggs and cook until set"
            ],
            "time": 10,
            "difficulty": "easy",
            "healthy": True
        },
        {
            "title": "Garlic Butter Pasta",
            "ingredients": ["pasta", "garlic", "butter", "olive oil", "salt", "pepper", "parsley"],
            "steps": [
                "Boil pasta until al dente",
                "Saute garlic in butter and olive oil",
                "Toss pasta with sauce and parsley"
            ],
            "time": 15,
            "difficulty": "easy",
            "healthy": False
        },
        {
            "title": "Chickpea Salad",
            "ingredients": ["chickpeas", "cucumber", "tomato", "onion", "lemon", "olive oil", "salt", "pepper"],
            "steps": [
                "Chop vegetables",
                "Mix with chickpeas, lemon juice and olive oil",
                "Season and serve"
            ],
            "time": 8,
            "difficulty": "easy",
            "healthy": True
        },
        {
            "title": "One-Pan Chicken & Rice",
            "ingredients": ["chicken", "rice", "onion", "garlic", "paprika", "salt", "pepper", "olive oil"],
            "steps": [
                "Brown chicken",
                "Saute aromatics",
                "Add rice and water, simmer until cooked"
            ],
            "time": 35,
            "difficulty": "medium",
            "healthy": True
        },
        {
            "title": "Peanut Stir-Fry",
            "ingredients": ["noodles", "soy sauce", "garlic", "ginger", "peanut butter", "mixed vegetables", "oil"],
            "steps": [
                "Stir-fry vegetables with garlic and ginger",
                "Add cooked noodles, soy sauce and peanut butter",
                "Toss to coat"
            ],
            "time": 15,
            "difficulty": "medium",
            "healthy": False
        },
        {
            "title": "Baked Oats",
            "ingredients": ["oats", "banana", "milk", "honey", "baking powder", "cinnamon"],
            "steps": [
                "Blend ingredients",
                "Bake until set"
            ],
            "time": 20,
            "difficulty": "easy",
            "healthy": True
        }
    ]

    results: List[Recipe] = []
    for item in catalog:
        ing = item["ingredients"]
        missing = [x for x in ing if x.lower() not in pantry_set]
        # simple relevance: require at least half of ingredients available
        if len(missing) <= len(ing) // 2:
            results.append(Recipe(
                title=item["title"],
                ingredients=ing,
                missing_ingredients=missing,
                steps=item["steps"],
                cooking_time_minutes=item["time"],
                difficulty=item["difficulty"],
                is_healthy=item["healthy"],
            ))
    # sort by fewest missing ingredients then time
    results.sort(key=lambda r: (len(r.missing_ingredients), r.cooking_time_minutes))
    return results


@app.post("/api/recipes", response_model=List[Recipe])
async def get_recipes(payload: RecipeRequest, request: Request):
    pantry = payload.ingredients or []
    difficulty = payload.difficulty
    healthy_only = payload.healthy_only

    if not isinstance(pantry, list) or any(not isinstance(i, str) for i in pantry):
        raise HTTPException(status_code=400, detail="ingredients must be a list of strings")

    all_results = simple_recipe_engine(pantry)

    if difficulty:
        allowed = {"easy", "medium", "hard"}
        if difficulty not in allowed:
            raise HTTPException(status_code=400, detail="difficulty must be easy|medium|hard")
        all_results = [r for r in all_results if r.difficulty == difficulty]

    if healthy_only:
        all_results = [r for r in all_results if r.is_healthy]

    # Log the search to DB (best-effort)
    try:
        from schemas import SearchLog
        log_doc = SearchLog(
            ingredients=[i.strip().lower() for i in pantry if i.strip()],
            healthy_only=healthy_only,
            difficulty=difficulty,
            results_count=len(all_results),
            client=request.headers.get("User-Agent")
        )
        create_document("searchlog", log_doc)
    except Exception:
        pass

    return all_results


@app.get("/")
def read_root():
    return {"name": "Kollny EXPRESS API", "status": "ok"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        from database import db

        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"

            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
