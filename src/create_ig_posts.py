"""
FINAL WORKING VERSION FOR IG POSTS GENERATION
"""
from dotenv import load_dotenv
import os
from supabase import create_client
import requests
import asyncio
from playwright.async_api import async_playwright
from slugify import slugify
from PIL import Image
from io import BytesIO
from pathlib import Path

load_dotenv("../.env.local")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

OUTPUT_DIR = "data/output"
POSTER_TEMP_PATH = "poster.jpg"
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

# Query 5 high-rated movies with both RT and IMDb scores
response = (
    supabase.table("movies")
    .select("*")
    .filter("imdb_rating", "not.is", "null")
    .filter("rotten_tomatoes", "not.is", "null")
    .contains("genres", ["Horror"])
    .order("imdb_rating", desc=True)
    .limit(5)
    .execute()
)
movies = response.data

for movie in movies:
    title = movie["title"]
    year = movie["year"]
    imdb_score = str(movie["imdb_rating"])
    rt_score = f"{movie['rotten_tomatoes']}%"
    poster_url = movie["poster_url"]

    # Download the poster
    try:
        r = requests.get(poster_url)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content)).convert("RGB")
        img.save(POSTER_TEMP_PATH)
    except Exception as e:
        print(f"❌ Failed to download poster for {title}: {e}")
        continue

    safe_title = slugify(title)
    output_path = os.path.join(OUTPUT_DIR, f"{safe_title}.png")

    async def render_template_to_image(output_path, title, year, imdb_rating, rt_score, poster_path):
        template_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data/templates/ig_card_template.html"))
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": 768, "height": 1152})
            await page.goto(f"file://{template_path}")
            await page.evaluate(f'''
                () => {{
                    document.getElementById("title").textContent = "{title} ({year})";
                    document.getElementById("imdb-score").textContent = "{imdb_rating}";
                    document.getElementById("rt-score").textContent = "{rt_score}";
                    document.getElementById("poster").src = "file://{os.path.abspath(poster_path)}";
                }}
            ''')
            await page.wait_for_timeout(1000)  # wait for images to load
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            await page.screenshot(path=output_path)
            await browser.close()

    asyncio.run(render_template_to_image(
        output_path=output_path,
        title=title,
        year=year,
        imdb_rating=imdb_score,
        rt_score=rt_score,
        poster_path=POSTER_TEMP_PATH
    ))

    print(f"[✓] Saved IG post for: {title} -> {output_path}")