import os
import json
from openai import OpenAI
import re
import requests
from datetime import datetime
from dotenv import load_dotenv

today_str = datetime.now().strftime("%B %d, %Y")

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

# === SUPABASE LOGGING ===
from supabase import create_client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
def log_prompt_to_supabase(prompt_text, filters, platforms, top_movies, final_response, used_fallback=False, response_time_ms=None, token_usage=None):
    try:
        supabase.table("prompts").insert({
            "prompt_text": prompt_text,
            "filters": filters,
            "platforms": platforms,
            "top_movies": top_movies,
            "final_response": final_response,
            "used_fallback": used_fallback,
            "response_time_ms": response_time_ms,
            "token_usage": token_usage
        }).execute()
        print("[LOG] Prompt logged to Supabase.")
    except Exception as e:
        print("[ERROR] Logging to Supabase failed:", e)

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
        "Use keys like with_genres (genre ID), primary_release_year, vote_average.gte, and with_keywords. "
        "If the prompt includes topics like space, war, cancer, love, or loss, consider using with_keywords. "
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

        matched_keywords = []
        if "with_keywords" not in filters:
            keyword_path = os.path.abspath(os.path.join(cache_dir, "..", "tmdb_keywords.json"))
            if os.path.exists(keyword_path):
                with open(keyword_path) as f:
                    keyword_cache = json.load(f)
                print(f"[DEBUG] Loaded {len(keyword_cache)} keywords from local cache.")
                prompt_lower = prompt.lower()
                for k, v in keyword_cache.items():
                    if k.lower() in prompt_lower:
                        matched_keywords.append((k, v))
                if matched_keywords:
                    ids = [str(kw[1]) for kw in matched_keywords]
                    filters["with_keywords"] = ",".join(ids)

        if matched_keywords:
            print(f"[INFO] Matched keywords from local cache:")
            for k, v in matched_keywords:
                print(f"    - {k} → ID {v}")
        else:
            print("[INFO] No keywords matched from local cache.")
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
    tmdb = get_tmdb_data(title)
    if not tmdb:
        return {"title": title, "note": "TMDb not found"}
    imdb_id = tmdb.get("imdb_id")
    safe_filename = imdb_id if imdb_id else re.sub(r'[^\w\-_\. ]', '_', title)
    path = os.path.join(cache_dir, f"{safe_filename}.json")
    if os.path.exists(path):
        return json.load(open(path))
    omdb = get_omdb_data(imdb_id)
    full = {**tmdb, **omdb}
    with open(path, "w") as f:
        json.dump(full, f, indent=2)
    push_movie_to_supabase(full)
    return full

def push_movie_to_supabase(movie_data):
    try:
        if not movie_data.get("imdb_id", "").startswith("tt"):
            return

        imdb_id = movie_data.get("imdb_id")

        # Safe validation for rotten_tomatoes, imdb_rating, metascore
        try:
            rt = movie_data.get("rotten_tomatoes")
            rt_value = int(rt.replace("%", "")) if rt and isinstance(rt, str) and rt.endswith("%") else None
        except Exception as e:
            print(f"[SKIP] {movie_data.get('title')} — invalid Rotten Tomatoes score: {rt}")
            rt_value = None

        try:
            imdb_rating = float(movie_data["imdb_rating"]) if movie_data.get("imdb_rating") and movie_data["imdb_rating"] != "N/A" else None
        except Exception as e:
            print(f"[SKIP] {movie_data.get('title')} — invalid IMDb rating: {movie_data.get('imdb_rating')}")
            imdb_rating = None

        try:
            metascore = int(movie_data["metascore"]) if movie_data.get("metascore") and movie_data["metascore"].isdigit() else None
        except Exception as e:
            print(f"[SKIP] {movie_data.get('title')} — invalid Metascore: {movie_data.get('metascore')}")
            metascore = None

        # Check if movie already exists
        existing = supabase.table("movies").select("imdb_id").eq("imdb_id", imdb_id).execute()
        is_new = not existing.data

        movie_payload = {
            "imdb_id": imdb_id,
            "tmdb_id": movie_data.get("tmdb_id"),
            "title": movie_data.get("title"),
            "year": movie_data.get("year"),
            "genres": movie_data.get("genres"),
            "runtime": movie_data.get("runtime"),
            "director": movie_data.get("director"),
            "main_cast": movie_data.get("cast"),
            "plot": movie_data.get("plot"),
            "streaming_services": movie_data.get("streaming_services"),
            "rotten_tomatoes": rt_value,
            "imdb_rating": imdb_rating,
            "metascore": metascore,
            "updated_at": datetime.utcnow().isoformat()
        }

        if is_new:
            movie_payload["created_at"] = datetime.utcnow().isoformat()

        result = supabase.table("movies").upsert(movie_payload, on_conflict="imdb_id").execute()

        if result and result.data:
            print(f"[SUPABASE] Upserted: {movie_data['title']} ({imdb_id}) — {'NEW' if is_new else 'UPDATED'}")
        else:
            print(f"[SUPABASE] No data returned for: {movie_data['title']} ({imdb_id})")
    except Exception as e:
        print(f"[ERROR] Failed to push {movie_data.get('title', 'Unknown')} to Supabase: {e}")

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
            prompt_lower = prompt.lower()
            matched_keywords = []
            for k, v in keyword_cache.items():
                # match whole word or phrase
                if k.lower() in prompt_lower:
                    matched_keywords.append((k, v))
            if matched_keywords:
                print(f"[INFO] Keywords matched from local cache: {[kw[0] for kw in matched_keywords]}")
                ids = [str(kw[1]) for kw in matched_keywords]
                filters["with_keywords"] = ",".join(ids)
                print(f"[INFO] Injected keywords from prompt: {[kw[0] for kw in matched_keywords]}")

    if not filters.get("with_keywords") and not filters.get("with_genres"):
        print("[INFO] No strong filters detected — skipping TMDb and going to fallback titles.")
        candidates = []
    else:
        candidates = get_movies_by_filters(filters)

        if not candidates:
            print("[INFO] No TMDb results — attempting to match from local cache...")
            for fname in os.listdir(cache_dir):
                if not fname.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(cache_dir, fname)) as f:
                        data = json.load(f)
                    title = data.get("title", "").lower()
                    year = data.get("year")
                    genres = [g.lower() for g in data.get("genres", [])]
                    if (
                        str(filters.get("primary_release_year")) == str(year)
                        and any(k.lower() in title for k in prompt.split())
                    ):
                        candidates.append({"title": data["title"]})
                except Exception as e:
                    continue
            if candidates:
                print(f"[INFO] Found {len(candidates)} matching locally cached movies.")

    if not candidates:
        print("[FALLBACK] No usable candidates found — calling GPT for fallback titles.")
        fallback_response = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful movie expert. The current date is "
                        f"{today_str}. Only suggest real, released or officially announced movies as of today. "
                        "Do not invent or guess titles that might come out in the future."
                    )
                },
                {
                    "role": "user",
                    "content": f"Suggest 10 real, existing movie titles based on this prompt: '{prompt}'."
                }
            ],
            temperature=0.7
        )
        fallback_titles = fallback_response.choices[0].message.content.split('\n')
        candidates = []
        for title in fallback_titles:
            if not title or len(title.split()) > 10 or "as an ai" in title.lower():
                continue  # Skip invalid or non-title lines
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

    if not enriched_movies and candidates:
        print("[INFO] Fallback mode — skipping scoring filter. Enriched all fallback titles based on GPT output.")
    else:
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

    top_movies = enriched_movies[:10]

    print(f"[INFO] Top {len(top_movies)} movies selected for GPT recommendation.")

    # Step 3: Use GPT to select and format top 5 recommendations
    import time
    start_time = time.time()
    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[
            {
                "role": "system",
                "content": (
                    f"You are a movie expert recommending 5 great films based on user preferences. "
                    f"Today's date is {today_str}. Only use real, released movies. Include RT, IMDb, and Metascore where possible, "
                    f"plus where to stream and a short plot summary."
                )
            },
            {"role": "user", "content": f"The user prompt was: '{prompt}'\nHere are 10 movie options:\n{json.dumps(top_movies, indent=2)}"}
        ],
        temperature=0.7
    )
    elapsed_ms = int((time.time() - start_time) * 1000)
    usage_tokens = getattr(response, "usage", None)
    if usage_tokens:
        usage_tokens = usage_tokens.total_tokens
    # Log prompt and results to Supabase
    log_prompt_to_supabase(
        prompt_text=prompt,
        filters=filters,
        platforms=filters.get("with_watch_providers", "").split(",") if filters.get("with_watch_providers") else [],
        top_movies=top_movies,
        final_response=response.choices[0].message.content,
        used_fallback=not bool(candidates),
        response_time_ms=elapsed_ms,
        token_usage=usage_tokens
    )

    print("\n====== RECOMMENDATIONS ======")
    print(response.choices[0].message.content)
if __name__ == "__main__":
    user_input = input("What kind of movie are you looking for?\n> ")
    recommend_movies_from_prompt(user_input)