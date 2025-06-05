import os
import json
from datetime import datetime
from supabase import create_client
from dotenv import load_dotenv

# Load Supabase creds
load_dotenv("../.env.local")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Directory containing movie .json files
CACHE_DIR = "../data/movie_cache"

def clean_percent(val):
    if isinstance(val, str) and val.endswith("%"):
        return int(val.replace("%", ""))
    return None

def push_movie(movie_data):
    try:
        if not movie_data.get("imdb_id", "").startswith("tt"):
            return

        supabase.table("movies").upsert({
            "imdb_id": movie_data.get("imdb_id"),
            "tmdb_id": movie_data.get("tmdb_id"),
            "title": movie_data.get("title"),
            "year": movie_data.get("year"),
            "genres": movie_data.get("genres"),
            "runtime": movie_data.get("runtime"),
            "director": movie_data.get("director"),
            "main_cast": movie_data.get("cast"),
            "plot": movie_data.get("plot"),
            "streaming_services": movie_data.get("streaming_services"),
            "imdb_rating": float(movie_data["imdb_rating"]) if movie_data.get("imdb_rating") else None,
            "metascore": int(movie_data["metascore"]) if movie_data.get("metascore") and movie_data["metascore"].isdigit() else None,
            "rotten_tomatoes": clean_percent(movie_data.get("rotten_tomatoes")),
            "updated_at": datetime.utcnow().isoformat()
        }).execute()

        print(f"[PUSHED] {movie_data['title']} ({movie_data['imdb_id']})")
    except Exception as e:
        print(f"[ERROR] {movie_data.get('title', 'Unknown')}: {e}")

def main():
    for file_name in os.listdir(CACHE_DIR):
        if not file_name.startswith("tt") or not file_name.endswith(".json"):
            continue

        file_path = os.path.join(CACHE_DIR, file_name)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                movie = json.load(f)
                push_movie(movie)
        except Exception as e:
            print(f"[SKIP] Failed to load {file_name}: {e}")

if __name__ == "__main__":
    main()