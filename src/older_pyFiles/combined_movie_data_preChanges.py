# This is a cleaned version of your two main scripts before the cancer prompt fallback logic.
# 1. GPT filter extraction
# 2. TMDb/OMDb fetch and enrichment
# Everything is combined and simplified for clarity.

import os
import json
import re
import requests
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

# Load credentials
load_dotenv("../.env.local")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
OMDB_API_KEY = os.getenv("OMDB_API_KEY")
TMDB_BEARER_TOKEN = os.getenv("TMDB_BEARER_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Setup cache dir
cache_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "movie_cache"))
os.makedirs(cache_dir, exist_ok=True)

######### API LOGGING #########
def log_api_call(service):
    today = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(cache_dir, "..", "api_usage_log.json")
    log = json.load(open(path)) if os.path.exists(path) else {}
    log.setdefault(today, {"tmdb": 0, "omdb": 0})
    log[today][service] += 1
    with open(path, "w") as f:
        json.dump(log, f, indent=2)

######### GPT FILTERS #########
def extract_filters(prompt):
    client = OpenAI(api_key=OPENAI_API_KEY)
    system_prompt = """
    You are a movie filter extractor. Return only valid JSON dictionary of TMDb filters. No markdown.
    Example: {"with_genres": [53], "primary_release_year.gte": 2023}
    """
    res = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )
    try:
        return json.loads(res.choices[0].message.content)
    except Exception as e:
        print("[ERROR] Could not parse GPT response:", e)
        return {}

######### TMDb MOVIE LIST #########
def get_movies_by_filters(filters):
    url = "https://api.themoviedb.org/3/discover/movie"
    headers = {"accept": "application/json", "Authorization": f"Bearer {TMDB_BEARER_TOKEN}"}
    movies = []
    for page in range(1, 4):
        params = {"language": "en-US", "page": page, "include_adult": "false", **filters}
        try:
            r = requests.get(url, headers=headers, params=params)
            log_api_call("tmdb")
            r.raise_for_status()
            for m in r.json().get("results", []):
                movies.append({"title": m["title"], "year": m["release_date"][:4]})
        except Exception as e:
            print("[ERROR] Discover failed:", e)
            break
    return movies

######### TMDb & OMDb DETAILS #########
def get_tmdb_data(title):
    headers = {"accept": "application/json"}
    params = {"query": title, "include_adult": "false", "language": "en-US", "page": 1}
    if TMDB_BEARER_TOKEN:
        headers["Authorization"] = f"Bearer {TMDB_BEARER_TOKEN}"
    elif TMDB_API_KEY:
        params["api_key"] = TMDB_API_KEY
    else:
        raise ValueError("Missing TMDb credentials.")

    try:
        r = requests.get("https://api.themoviedb.org/3/search/movie", headers=headers, params=params)
        log_api_call("tmdb")
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return None
        movie_id = results[0]["id"]
        details = requests.get(f"https://api.themoviedb.org/3/movie/{movie_id}", headers=headers).json()
        credits = requests.get(f"https://api.themoviedb.org/3/movie/{movie_id}/credits", headers=headers).json()
        providers = requests.get(f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers", headers=headers).json()
        us_sources = providers.get("results", {}).get("US", {}).get("flatrate", [])
        return {
            "tmdb_id": movie_id,
            "imdb_id": details.get("imdb_id"),
            "title": details.get("title"),
            "year": details.get("release_date", "")[:4],
            "genres": [g["name"] for g in details.get("genres", [])],
            "runtime": details.get("runtime"),
            "director": next((c["name"] for c in credits.get("crew", []) if c["job"] == "Director"), "Unknown"),
            "cast": [a["name"] for a in credits.get("cast", [])[:5]],
            "plot": details.get("overview"),
            "streaming_services": [s["provider_name"] for s in us_sources]
        }
    except Exception as e:
        print("[ERROR] TMDb fetch failed:", e)
        return None

def get_omdb_data(imdb_id):
    try:
        r = requests.get("http://www.omdbapi.com/", params={"apikey": OMDB_API_KEY, "i": imdb_id})
        log_api_call("omdb")
        r.raise_for_status()
        data = r.json()
        ratings = {r["Source"]: r["Value"] for r in data.get("Ratings", [])}
        return {
            "imdb_rating": data.get("imdbRating"),
            "metascore": data.get("Metascore"),
            "rotten_tomatoes": ratings.get("Rotten Tomatoes")
        }
    except Exception as e:
        print("[ERROR] OMDb fetch failed:", e)
        return {}

def get_combined_data(title):
    safe = re.sub(r'[^\w\-_\. ]', '_', title)
    path = os.path.join(cache_dir, f"{safe}.json")
    if os.path.exists(path):
        return json.load(open(path))
    tmdb = get_tmdb_data(title)
    if not tmdb:
        return {"title": title, "note": "TMDb not found"}
    omdb = get_omdb_data(tmdb.get("imdb_id"))
    full = {**tmdb, **omdb}
    with open(path, "w") as f:
        json.dump(full, f, indent=2)
    return full

######### MAIN #########
def main():
    prompt = input("What kind of movie are you looking for?\n> ")
    filters = extract_filters(prompt)
    print("[INFO] Filters:", filters)
    movies = get_movies_by_filters(filters)
    print(f"[INFO] Found {len(movies)} movies")
    enriched = [get_combined_data(m['title']) for m in movies[:20]]
    for m in enriched[:5]:
        print(f"\n== {m['title']} ({m['year']}) ==")
        print(f"Plot: {m.get('plot')}")
        print(f"IMDB: {m.get('imdb_rating')} | Metascore: {m.get('metascore')} | RT: {m.get('rotten_tomatoes')}")
        print(f"Streaming: {', '.join(m.get('streaming_services', []))}")

if __name__ == "__main__":
    main()
