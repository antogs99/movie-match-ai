"""
gets movies from supabase that don't have a movie url and tries to get it
"""
import os
import requests
from supabase import create_client
from dotenv import load_dotenv

# Load env vars
load_dotenv("../.env.local")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TMDB_BEARER_TOKEN = os.getenv("TMDB_BEARER_TOKEN")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Create posters dir
poster_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "posters"))
os.makedirs(poster_dir, exist_ok=True)

# Pull all movies from Supabase where poster_url is null
res = (
    supabase.table("movies")
    .select("imdb_id, tmdb_id, title, poster_url")
    .filter("poster_url", "is", "null")
    .limit(1000)
    .execute()
)
movies = res.data

for movie in movies:
    movie_id = movie["imdb_id"]
    tmdb_id = movie["tmdb_id"]

    # Get poster from TMDb
    headers = {"Authorization": f"Bearer {TMDB_BEARER_TOKEN}", "accept": "application/json"}
    r = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}", headers=headers)

    if r.status_code != 200:
        print(f"[✗] Failed to fetch TMDb data for {tmdb_id}")
        continue

    poster_path = r.json().get("poster_path")
    if not poster_path:
        print(f"[!] No poster found for TMDb ID {tmdb_id}")
        continue

    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
    print(f"[✓] {tmdb_id} → {poster_url}")

    # Download and save poster
    img_data = requests.get(poster_url).content
    filename = os.path.join(poster_dir, f"{tmdb_id}.jpg")
    with open(filename, "wb") as f:
        f.write(img_data)

    # Update poster_url in Supabase
    supabase.table("movies").update({
        "poster_url": poster_url
    }).eq("imdb_id", movie_id).execute()