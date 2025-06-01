import requests
import os
from dotenv import load_dotenv
import json
import re
from datetime import datetime

cache_dir = os.path.join(os.path.dirname(__file__), "..", "data", "movie_cache")
cache_dir = os.path.abspath(cache_dir)
os.makedirs(cache_dir, exist_ok=True)

# On-demand TMDb keyword ID lookup with local cache
def get_or_fetch_keyword_id(keyword: str):
    keyword_cache_path = os.path.abspath(os.path.join(cache_dir, "..", "tmdb_keywords.json"))
    if os.path.exists(keyword_cache_path):
        with open(keyword_cache_path, "r") as f:
            keyword_cache = json.load(f)
    else:
        keyword_cache = {}

    if keyword in keyword_cache:
        return keyword_cache[keyword]

    # Query TMDb for keyword
    search_url = "https://api.themoviedb.org/3/search/keyword"
    headers = {"accept": "application/json"}
    params = {"query": keyword}
    if TMDB_BEARER_TOKEN:
        headers["Authorization"] = f"Bearer {TMDB_BEARER_TOKEN}"
    elif TMDB_API_KEY:
        params["api_key"] = TMDB_API_KEY
    else:
        raise ValueError("No TMDb API credentials found.")

    try:
        response = requests.get(search_url, headers=headers, params=params)
        log_api_call("tmdb")
        response.raise_for_status()
        results = response.json().get("results", [])
        if not results:
            print(f"[WARNING] No TMDb keyword found for '{keyword}'")
            return None
        keyword_id = results[0]["id"]
        keyword_cache[keyword] = keyword_id
        with open(keyword_cache_path, "w") as f:
            json.dump(keyword_cache, f, indent=2)
        print(f"[INFO] Fetched and cached TMDb keyword ID for '{keyword}': {keyword_id}")
        return keyword_id
    except Exception as e:
        print(f"[ERROR] Failed to fetch TMDb keyword for '{keyword}':", e)
        return None

# Load API keys from .env.local
load_dotenv(dotenv_path="../.env.local")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
OMDB_API_KEY = os.getenv("OMDB_API_KEY")
TMDB_BEARER_TOKEN = os.getenv("TMDB_BEARER_TOKEN")

print("TMDB_BEARER_TOKEN loaded:", bool(TMDB_BEARER_TOKEN))
print("TMDB_API_KEY loaded:", bool(TMDB_API_KEY))


# Log API usage
def log_api_call(service_name):
    today = datetime.now().strftime("%Y-%m-%d")
    data_dir = os.path.abspath(os.path.join(cache_dir, ".."))
    log_file = os.path.join(data_dir, "api_usage_log.json")
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            log_data = json.load(f)
    else:
        log_data = {}

    if today not in log_data:
        log_data[today] = {"tmdb": 0, "omdb": 0}

    log_data[today][service_name] += 1

    with open(log_file, "w") as f:
        json.dump(log_data, f, indent=2)

def get_tmdb_data(title):
    search_url = "https://api.themoviedb.org/3/search/movie"
    headers = {
        "accept": "application/json"
    }
    params = {
        "query": title,
        "include_adult": "false",
        "language": "en-US",
        "page": 1
    }
    if TMDB_BEARER_TOKEN:
        headers["Authorization"] = f"Bearer {TMDB_BEARER_TOKEN}"
    elif TMDB_API_KEY:
        params["api_key"] = TMDB_API_KEY
    else:
        raise ValueError("No TMDb API credentials found.")

    try:
        search_resp = requests.get(search_url, params=params, headers=headers)
        log_api_call("tmdb")
        search_resp.raise_for_status()
    except Exception as e:
        print("TMDb search request failed:", e)
        return None

    results = search_resp.json().get("results", [])
    if not results:
        return None

    movie = results[0]
    movie_id = movie["id"]

    # Get details
    details_url = f"https://api.themoviedb.org/3/movie/{movie_id}"
    credits_url = f"https://api.themoviedb.org/3/movie/{movie_id}/credits"
    detail_resp = requests.get(details_url, headers=headers)
    credit_resp = requests.get(credits_url, headers=headers)

    detail_data = detail_resp.json()
    credit_data = credit_resp.json()

    director = next((p["name"] for p in credit_data["crew"] if p["job"] == "Director"), "Unknown")
    cast = [actor["name"] for actor in credit_data["cast"][:5]]

    # Get streaming services (US region)
    watch_url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers"
    watch_resp = requests.get(watch_url, headers=headers)
    watch_data = watch_resp.json()
    us_watch_info = watch_data.get("results", {}).get("US", {})
    streaming_sources = us_watch_info.get("flatrate", [])
    streaming_services = [s.get("provider_name") for s in streaming_sources] if streaming_sources else []

    return {
        "tmdb_id": movie_id,
        "imdb_id": detail_data.get("imdb_id"),
        "title": detail_data.get("title"),
        "year": detail_data.get("release_date", "")[:4],
        "genres": [g["name"] for g in detail_data.get("genres", [])],
        "runtime": detail_data.get("runtime"),
        "director": director,
        "cast": cast,
        "plot": detail_data.get("overview"),
        "streaming_services": streaming_services
    }

def get_omdb_data(imdb_id):
    url = "http://www.omdbapi.com/"
    params = {
        "apikey": OMDB_API_KEY,
        "i": imdb_id
    }
    response = requests.get(url, params=params)
    log_api_call("omdb")
    response.raise_for_status()
    data = response.json()

    ratings = {r["Source"]: r["Value"] for r in data.get("Ratings", [])}
    return {
        "imdb_rating": data.get("imdbRating"),
        "metascore": data.get("Metascore"),
        "rotten_tomatoes": ratings.get("Rotten Tomatoes")
    }

def get_combined_data(title):
    # Normalize filename
    safe_title = re.sub(r'[^\w\-_\. ]', '_', title)
    cache_file = os.path.join(cache_dir, f"{safe_title}.json")
    if os.path.exists(cache_file):
        print(f"[CACHE] Loaded cached data for '{title}' from {cache_file}")
        with open(cache_file, 'r') as f:
            cached_data = json.load(f)

        # Always update streaming services from TMDb
        tmdb_id = cached_data.get("tmdb_id")
        if tmdb_id:
            headers = {"accept": "application/json"}
            if TMDB_BEARER_TOKEN:
                headers["Authorization"] = f"Bearer {TMDB_BEARER_TOKEN}"
            watch_url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/watch/providers"
            try:
                watch_resp = requests.get(watch_url, headers=headers)
                watch_data = watch_resp.json()
                us_watch_info = watch_data.get("results", {}).get("US", {})
                streaming_sources = us_watch_info.get("flatrate", [])
                streaming_services = [s.get("provider_name") for s in streaming_sources] if streaming_sources else []
                cached_data["streaming_services"] = streaming_services
                print(f"[CACHE] Updated streaming info for '{title}'")
                with open(cache_file, 'w') as f:
                    json.dump(cached_data, f, indent=2)
            except Exception as e:
                print(f"[ERROR] Failed to refresh streaming info for TMDb ID {tmdb_id}:", e)

        return cached_data

    tmdb_data = get_tmdb_data(title)
    if not tmdb_data:
        print(f"[WARNING] '{title}' not found on TMDb. Skipping enrichment.")
        return {
            "title": title,
            "streaming_services": [],
            "note": "GPT-generated recommendation; verified data not available"
        }
    print(f"[API] Fetching data from TMDb for '{title}'...")

    if tmdb_data.get("imdb_id"):
        imdb_id = tmdb_data["imdb_id"]
        reused_omdb_data = None

        for file_name in os.listdir(cache_dir):
            file_path = os.path.join(cache_dir, file_name)
            if file_name.endswith(".json"):
                with open(file_path, "r") as f:
                    cached_data = json.load(f)
                    if cached_data.get("imdb_id") == imdb_id:
                        reused_omdb_data = {
                            "imdb_rating": cached_data.get("imdb_rating"),
                            "metascore": cached_data.get("metascore"),
                            "rotten_tomatoes": cached_data.get("rotten_tomatoes")
                        }
                        print(f"[CACHE] Reused OMDb data from {file_name}")
                        break

        if reused_omdb_data:
            omdb_data = reused_omdb_data
        else:
            print(f"[API] Fetching OMDb data for IMDB ID: {imdb_id}")
            omdb_data = get_omdb_data(imdb_id)
    else:
        omdb_data = {}

    combined = {**tmdb_data, **omdb_data}
    print(f"[CACHE] Saving combined data to {cache_file}")
    with open(cache_file, 'w') as f:
        json.dump(combined, f, indent=2)
    return combined


# New function: get_movies_by_filters
def get_movies_by_filters(filters: dict):
    discover_url = "https://api.themoviedb.org/3/discover/movie"
    headers = {"accept": "application/json"}
    if TMDB_BEARER_TOKEN:
        headers["Authorization"] = f"Bearer {TMDB_BEARER_TOKEN}"
    elif TMDB_API_KEY:
        filters["api_key"] = TMDB_API_KEY
    else:
        raise ValueError("No TMDb API credentials found.")

    all_movies = []
    for page in range(1, 4):  # Get up to 3 pages (about 60 movies)
        params = {"language": "en-US", "page": page, "include_adult": "false", **filters}
        try:
            response = requests.get(discover_url, headers=headers, params=params)
            log_api_call("tmdb")
            response.raise_for_status()
            results = response.json().get("results", [])
            for movie in results:
                all_movies.append({
                    "title": movie.get("title"),
                    "year": movie.get("release_date", "")[:4],
                    "tmdb_id": movie.get("id")
                })
        except Exception as e:
            print(f"TMDb discover request failed on page {page}:", e)
            break

    return all_movies
def fetch_and_store_tmdb_genres():
    genre_url = "https://api.themoviedb.org/3/genre/movie/list"
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {TMDB_BEARER_TOKEN}"
    }

    try:
        response = requests.get(genre_url, headers=headers)
        log_api_call("tmdb")
        response.raise_for_status()
        genres = response.json().get("genres", [])
        genre_map = {g["id"]: g["name"] for g in genres}

        data_dir = os.path.abspath(os.path.join(cache_dir, ".."))
        genre_file = os.path.join(data_dir, "tmdb_genres.json")
        with open(genre_file, "w") as f:
            json.dump(genre_map, f, indent=2)
        print(f"[SUCCESS] Stored TMDb genres to {genre_file}")
    except Exception as e:
        print("[ERROR] Failed to fetch genres:", e)
# Manual test for get_movies_by_filters
if __name__ == "__main__":
    """
    filters = {
        "with_genres": "27",  # Horror
        "primary_release_year": 2023,
        "vote_average.gte": 6
    }
    movies = get_movies_by_filters(filters)
    print("\n--- Filtered Movies ---")
    for m in movies:
        print(f"{m['title']} ({m['year']}) [TMDb ID: {m['tmdb_id']}]")
    """
    """
    title = input("Enter a movie title: ")
    data = get_combined_data(title)
    for k, v in data.items():
        print(f"{k}: {v}")
    """
    # Uncomment to fetch and save TMDb genres
    fetch_and_store_tmdb_genres()
