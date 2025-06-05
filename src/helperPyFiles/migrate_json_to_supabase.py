import json
import os
from supabase import create_client, Client
from dotenv import load_dotenv
load_dotenv("../.env.local")

# Supabase config from environment
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Paths
api_log_path = "../data/api_usage_log.json"
keywords_path = "../data/tmdb_keywords.json"
genres_path = "../data/tmdb_genres.json"
# Push API usage log
"""
if os.path.exists(api_log_path):
    with open(api_log_path, "r") as f:
        api_log = json.load(f)
    for date_str, counts in api_log.items():
        supabase.table("api_usage_log").upsert({
            "date": date_str,
            "tmdb_count": counts.get("tmdb", 0),
            "omdb_count": counts.get("omdb", 0)
        }).execute()
    print("[✓] api_usage_log.json pushed")

# Push keywords
if os.path.exists(keywords_path):
    with open(keywords_path, "r") as f:
        keywords = json.load(f)
    for name, kid in keywords.items():
        supabase.table("tmdb_keywords").upsert({
            "keyword_name": name,
            "keyword_id": kid
        }).execute()
    print("[✓] tmdb_keywords.json pushed")
"""
# Push genres
if os.path.exists(genres_path):
    with open(genres_path, "r") as f:
        genres = json.load(f)
    for genre_id, genre_name in genres.items():
        supabase.table("tmdb_genres").upsert({
            "genre_id": int(genre_id),
            "genre_name": genre_name
        }).execute()
    print("[✓] tmdb_genres.json pushed")