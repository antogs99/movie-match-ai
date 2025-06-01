import os
import json
from openai import OpenAI
import re
import requests
from datetime import datetime
from dotenv import load_dotenv

"""
from combined_movie_data:
get_combined_data
get_movies_by_filters: done

from: gpt_filters
extract_filters_from_prompt: done
"""


# Load credentials
load_dotenv("../.env.local")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
OMDB_API_KEY = os.getenv("OMDB_API_KEY")
TMDB_BEARER_TOKEN = os.getenv("TMDB_BEARER_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Setup cache dir
cache_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "movie_cache"))
os.makedirs(cache_dir, exist_ok=True)

openai = OpenAI()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

######### API LOGGING #########
def log_api_call(service):
    today = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(cache_dir, "..", "api_usage_log.json")
    log = json.load(open(path)) if os.path.exists(path) else {}
    log.setdefault(today, {"tmdb": 0, "omdb": 0})
    log[today][service] += 1
    with open(path, "w") as f:
        json.dump(log, f, indent=2)

def get_or_fetch_keyword_id(keyword: str):
    cache_path = os.path.abspath(os.path.join(cache_dir, "..", "tmdb_keywords.json"))
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            keyword_cache = json.load(f)
    else:
        keyword_cache = {}

    if keyword in keyword_cache:
        return keyword_cache[keyword]

    url = "https://api.themoviedb.org/3/search/keyword"
    headers = {"accept": "application/json", "Authorization": f"Bearer {TMDB_BEARER_TOKEN}"}
    params = {"query": keyword}
    try:
        r = requests.get(url, headers=headers, params=params)
        log_api_call("tmdb")
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            print(f"[WARNING] No TMDb keyword found for '{keyword}'")
            return None
        keyword_id = results[0]["id"]
        keyword_cache[keyword] = keyword_id
        with open(cache_path, "w") as f:
            json.dump(keyword_cache, f, indent=2)
        return keyword_id
    except Exception as e:
        print(f"[ERROR] Keyword fetch failed for '{keyword}':", e)
        return None

######### TMDb MOVIE LIST #########
def get_movies_by_filters(filters):
    url = "https://api.themoviedb.org/3/discover/movie"
    headers = {"accept": "application/json", "Authorization": f"Bearer {TMDB_BEARER_TOKEN}"}
    movies = []
    # Dynamically determine number of pages based on specificity
    base_pages = 2
    if filters.get("with_keywords") and filters.get("with_genres") and filters.get("primary_release_year"):
        base_pages = 5  # very specific prompts
    elif filters.get("with_keywords") or filters.get("with_genres"):
        base_pages = 3  # moderately specific
    else:
        base_pages = 1  # fallback or vague prompts

    for page in range(1, base_pages + 1):
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

def load_genre_map():
    genre_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "tmdb_genres.json"))
    try:
        with open(genre_path) as f:
            return json.load(f)
    except Exception:
        print("[WARNING] Could not load genre map.")
        return {}

def extract_filters_from_prompt(prompt: str) -> dict:
    genre_map = load_genre_map()
    genre_instructions = "Here are valid TMDb genres with their IDs:\n" + "\n".join(f"{k}: {v}" for k, v in genre_map.items())
    system_msg = (
        genre_instructions + "\n\n"
        "Extract a TMDb-compatible movie filter from a user prompt. "
        "Use keys like with_genres (genre ID), primary_release_year, vote_average.gte. "
        "Only output a Python dictionary."
    )
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": prompt}
    ]
    completion = client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        temperature=0
    )
    response = completion.choices[0].message.content
    try:
        filters = eval(response)
        if "with_keywords" in filters and isinstance(filters["with_keywords"], str):
            keyword_id = get_or_fetch_keyword_id(filters["with_keywords"])
            if keyword_id:
                filters["with_keywords"] = keyword_id
            else:
                del filters["with_keywords"]
        return filters
    except Exception:
        print("Failed to parse GPT response:", response)
        return {}
    
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

def recommend_movies_from_prompt(prompt: str):
    print(f"[INFO] User Prompt: {prompt}")
    
    # Step 1: Extract filters from prompt using ChatGPT
    filters = extract_filters_from_prompt(prompt)
    print(f"[INFO] Extracted Filters: {filters}")

    # Fallback keyword injection from local keyword list
    if "with_keywords" not in filters:
        keyword_path = os.path.abspath(os.path.join(cache_dir, "..", "tmdb_keywords.json"))
        if os.path.exists(keyword_path):
            with open(keyword_path) as f:
                keyword_cache = json.load(f)
            prompt_words = re.findall(r'\b\w+\b', prompt.lower())
            matched_keywords = [keyword_cache[word] for word in prompt_words if word in keyword_cache]
            if matched_keywords:
                filters["with_keywords"] = ",".join(str(k) for k in matched_keywords)
                print(f"[INFO] Injected keywords from prompt: {matched_keywords}")

    if not filters.get("with_keywords") and not filters.get("with_genres"):
        print("[INFO] No strong filters detected — skipping TMDb and going to fallback titles.")
        candidates = []
    else:
        candidates = get_movies_by_filters(filters)
    print(f"[INFO] Fetched {len(candidates)} candidates from TMDb")

    if not candidates:
        # fallback logic: ask GPT for top movies to recommend
        fallback_response = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that suggests movie titles based on a user prompt."},
                {"role": "user", "content": f"Suggest 10 movie titles based on this prompt: '{prompt}'."}
            ],
            temperature=0.7
        )
        fallback_titles = fallback_response.choices[0].message.content.split('\n')
        candidates = []
        for title in fallback_titles:
            title = title.strip("- ").strip()
            if title:
                print(f"[FALLBACK] Getting info for: {title}")
                candidates.append({"title": title})

    enriched_movies = []
    for movie in candidates[:30]:
        title = movie.get("title")
        print(f"[ENRICHING] Fetching detailed info for: {title}")
        data = get_combined_data(title)
        if data and data.get("title") and data.get("rotten_tomatoes"):
            enriched_movies.append(data)

    print(f"[INFO] Enriched data for {len(candidates[:30])} movies, usable: {len(enriched_movies)}")

    if not enriched_movies:
        print("[INFO] No enriched movies with full data — fallback formatting may be GPT-generated.")

    enriched_movies = [m for m in enriched_movies if m.get("streaming_services")]

    def sort_key(m):
        def to_float(val):
            try:
                return float(val.strip('%')) if isinstance(val, str) else float(val)
            except:
                return -1

        rt = to_float(m.get("rotten_tomatoes"))
        imdb = to_float(m.get("imdb_rating"))
        meta = to_float(m.get("metascore"))
        return (rt, imdb, meta)

    enriched_movies.sort(key=sort_key, reverse=True)

    top_movies = enriched_movies[:20]

    print(f"[INFO] Top {len(top_movies)} movies selected for GPT recommendation.")

    # Step 3: Use GPT to select and format top 10 recommendations
    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a movie expert recommending great films to users based on their preferences. Pick the best matches from the list, even if they are loosely related to the prompt. For each movie, include its Rotten Tomatoes critic score, IMDb rating, and Metascore (if available), where it's available to stream, and a short plot summary."},
            {"role": "user", "content": f"The user prompt was: '{prompt}'\nHere are 20 movie options:\n{json.dumps(top_movies, indent=2)}"}
        ],
        temperature=0.7
    )

    print("\n====== RECOMMENDATIONS ======")
    print(response.choices[0].message.content)
if __name__ == "__main__":
    user_input = input("What kind of movie are you looking for?\n> ")
    recommend_movies_from_prompt(user_input)