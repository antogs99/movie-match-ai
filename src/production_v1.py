import time
from config import WATCH_PROVIDER_MAP
import os
import ast
import json
import re
import requests
from datetime import datetime
from dotenv import load_dotenv
from difflib import get_close_matches
VERBOSE = True  # Set to False to suppress debug prints

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
        if VERBOSE:
            print("[LOG] Prompt logged to Supabase.")
    except Exception as e:
        if VERBOSE:
            print("[ERROR] Logging to Supabase failed:", e)

# Setup cache dir
cache_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "movie_cache"))
os.makedirs(cache_dir, exist_ok=True)

import openai
openai.api_key = os.getenv("OPENAI_API_KEY")

######### API LOGGING #########
def log_api_call(service):
    today = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(cache_dir, "..", "api_usage_log.json")
    log = json.load(open(path)) if os.path.exists(path) else {}
    log.setdefault(today, {"tmdb": 0, "omdb": 0})
    log[today][service] += 1
    with open(path, "w") as f:
        json.dump(log, f, indent=2)


# === Keyword Cache for Supabase ===
_keyword_cache = None

def get_or_fetch_keyword_id(keyword: str):
    global _keyword_cache
    try:
        # Only fetch from Supabase if not already cached
        if _keyword_cache is None:
            result = supabase.table("tmdb_keywords").select("keyword_name,keyword_id").execute()
            _keyword_cache = result.data if result and result.data else []

        keyword_list = [row["keyword_name"] for row in _keyword_cache]
        match = get_close_matches(keyword, keyword_list, n=1, cutoff=0.8)
        if match:
            matched_name = match[0]
            matched_id = next((row["keyword_id"] for row in _keyword_cache if row["keyword_name"] == matched_name), None)
            if matched_id:
                if VERBOSE:
                    print(f"[FUZZY MATCH] '{keyword}' → '{matched_name}' (ID {matched_id})")
                return matched_id
        else:
            if VERBOSE:
                print(f"[INFO] No keyword match found in cache for '{keyword}'")
    except Exception as e:
        if VERBOSE:
            print(f"[ERROR] Failed during fuzzy keyword match for '{keyword}':", e)

    # Fall back to TMDb API if not found in cache
    url = "https://api.themoviedb.org/3/search/keyword"
    headers = {"accept": "application/json", "Authorization": f"Bearer {TMDB_BEARER_TOKEN}"}
    params = {"query": keyword}
    try:
        r = requests.get(url, headers=headers, params=params)
        log_api_call("tmdb")
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            if VERBOSE:
                print(f"[WARNING] No TMDb keyword found for '{keyword}'")
            return None
        keyword_id = results[0]["id"]
        # Insert into Supabase and update local cache
        try:
            supabase.table("tmdb_keywords").insert({
                "keyword_name": keyword,
                "keyword_id": keyword_id
            }).execute()
            if _keyword_cache is not None:
                _keyword_cache.append({"keyword_name": keyword, "keyword_id": keyword_id})
            if VERBOSE:
                print(f"[SUPABASE] Inserted keyword '{keyword}' with ID {keyword_id}")
        except Exception as e:
            if VERBOSE:
                print(f"[ERROR] Failed to insert keyword '{keyword}' into Supabase:", e)
        return keyword_id
    except Exception as e:
        if VERBOSE:
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
            if VERBOSE:
                print("[ERROR] Discover failed:", e)
            break
    return movies

def load_genre_map():
    try:
        result = supabase.table("tmdb_genres").select("*").execute()
        if result and result.data:
            return {str(row["genre_id"]): row["genre_name"] for row in result.data}
        else:
            return {}
    except Exception as e:
        if VERBOSE:
            print("[ERROR] Failed to load genre map from Supabase:", e)
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
    completion = openai.chat.completions.create(
        model="gpt-4",
        messages=messages,
        temperature=0
    )
    response = completion.choices[0].message.content
    try:
        filters = ast.literal_eval(response)
        if "with_keywords" in filters and isinstance(filters["with_keywords"], str):
            raw_keywords = [kw.strip() for kw in filters["with_keywords"].split(",")]
            keyword_ids = []
            for kw in raw_keywords:
                keyword_id = get_or_fetch_keyword_id(kw)
                if keyword_id:
                    keyword_ids.append(str(keyword_id))
            if keyword_ids:
                filters["with_keywords"] = ",".join(keyword_ids)
            else:
                del filters["with_keywords"]

        # Local keyword fallback disabled
        if VERBOSE:
            print("[INFO] Local keyword fallback is disabled in extract_filters_from_prompt.")

        return filters
    except Exception:
        if VERBOSE:
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
        if VERBOSE:
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
        if VERBOSE:
            print("[ERROR] OMDb fetch failed:", e)
        return {}

def get_poster_url(tmdb_id):
    try:
        headers = {"accept": "application/json"}
        if TMDB_BEARER_TOKEN:
            headers["Authorization"] = f"Bearer {TMDB_BEARER_TOKEN}"
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        poster_path = data.get("poster_path")
        if poster_path:
            return f"https://image.tmdb.org/t/p/w500{poster_path}"
        return None
    except Exception as e:
        if VERBOSE:
            print(f"[ERROR] Failed to fetch poster URL for TMDb ID {tmdb_id}: {e}")
        return None

def get_combined_data(title):
    tmdb = get_tmdb_data(title)
    if not tmdb:
        return {"title": title, "note": "TMDb not found"}
    imdb_id = tmdb.get("imdb_id")
    tmdb_id = tmdb.get("tmdb_id")
    # Retrieve poster URL after getting tmdb_id
    poster_url = get_poster_url(tmdb_id)
    if VERBOSE:
        print(f"[✓] Poster URL for {title}: {poster_url}")
    # Check Supabase first for existing movie data
    existing = supabase.table("movies").select("*").eq("imdb_id", imdb_id).execute()
    if existing and existing.data:
        if VERBOSE:
            print(f"[SUPABASE] Loaded cached data for {title} ({imdb_id}) from Supabase.")
        return existing.data[0]
    omdb = get_omdb_data(imdb_id)
    full = {**tmdb, **omdb, "poster_url": poster_url}
    # Optionally still write to local cache for debugging, but no longer used for reads
    push_movie_to_supabase(full)
    if VERBOSE:
        print(f"[SUPABASE] Pushed new data for {title} ({imdb_id}) to Supabase.")
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
            if VERBOSE:
                print(f"[SKIP] {movie_data.get('title')} — invalid Rotten Tomatoes score: {rt}")
            rt_value = None

        try:
            imdb_rating = float(movie_data["imdb_rating"]) if movie_data.get("imdb_rating") and movie_data["imdb_rating"] != "N/A" else None
        except Exception as e:
            if VERBOSE:
                print(f"[SKIP] {movie_data.get('title')} — invalid IMDb rating: {movie_data.get('imdb_rating')}")
            imdb_rating = None

        try:
            metascore = int(movie_data["metascore"]) if movie_data.get("metascore") and movie_data["metascore"].isdigit() else None
        except Exception as e:
            if VERBOSE:
                print(f"[SKIP] {movie_data.get('title')} — invalid Metascore: {movie_data.get('metascore')}")
            metascore = None

        # Check if movie already exists
        existing = supabase.table("movies").select("imdb_id").eq("imdb_id", imdb_id).execute()
        is_new = not existing.data

        # Use poster_url from movie_data if present
        poster_url = movie_data.get("poster_url")

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
            "updated_at": datetime.utcnow().isoformat(),
            "poster_url": poster_url
        }

        # Save poster locally if poster_url is present
        if poster_url:
            posters_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "posters"))
            os.makedirs(posters_dir, exist_ok=True)
            poster_file = os.path.join(posters_dir, f"{movie_data.get('tmdb_id')}.jpg")
            if not os.path.exists(poster_file):
                try:
                    img_data = requests.get(poster_url).content
                    with open(poster_file, "wb") as f:
                        f.write(img_data)
                except Exception as e:
                    if VERBOSE:
                        print(f"[ERROR] Failed to save poster locally for {movie_data.get('title')}: {e}")

        if is_new:
            movie_payload["created_at"] = datetime.utcnow().isoformat()

        result = supabase.table("movies").upsert(movie_payload, on_conflict="imdb_id").execute()

        if result and result.data:
            if VERBOSE:
                print(f"[SUPABASE] Upserted: {movie_data.get('title')} ({imdb_id}) — {'NEW' if is_new else 'UPDATED'}")
        else:
            if VERBOSE:
                print(f"[SUPABASE] No data returned for: {movie_data.get('title')} ({imdb_id})")
    except Exception as e:
        if VERBOSE:
            print(f"[ERROR] Failed to push {movie_data.get('title', 'Unknown')} to Supabase: {e}")

def get_fallback_titles_from_gpt(prompt: str) -> list:
    if VERBOSE:
        print("[FALLBACK] No usable candidates found — calling GPT for fallback titles.")
    fallback_script = (
        f"Today is {today_str}.\n"
        "The user mentioned a movie that doesn’t appear in our database, but we should never assume it's not real.\n"
        "Respond politely, acknowledge that the title isn't found, and suggest similar real movies based on name, theme, or possible genre.\n"
        "Never say it doesn’t exist. Be helpful.\n\n"
        "Use this format:\n"
        "\"While I couldn’t find detailed info on [title], here are some similar movies you might enjoy...\"\n"
        "Then give 5–10 movie suggestions with a short reason if possible."
    )
    fallback_response = openai.chat.completions.create(
        model="gpt-4",
        messages=[
            {
                "role": "system",
                "content": fallback_script
            },
            {
                "role": "user",
                "content": f"The user prompt was: '{prompt}'"
            }
        ],
        temperature=0.7
    )
    fallback_titles = fallback_response.choices[0].message.content.split('\n')
    candidates = []
    for title in fallback_titles:
        if (
            not title
            or len(title.split()) > 10
            or "as an ai" in title.lower()
            or not re.match(r"^[a-zA-Z0-9 .:'\-?!&()]+$", title)
        ):
            continue  # Skip invalid or non-title lines
        title = title.strip("- ").strip()
        if title:
            if VERBOSE:
                print(f"[FALLBACK] Getting info for: {title}")
            candidates.append({"title": title})
    return candidates

def recommend_movies_from_prompt(prompt: str):
    if VERBOSE:
        print(f"[INFO] User Prompt: {prompt}")
    
    # Step 1: Extract filters from prompt using ChatGPT
    filters = extract_filters_from_prompt(prompt)
    if VERBOSE:
        print(f"[INFO] Extracted Filters: {filters}")

    # Fallback keyword injection from local keyword list is disabled.
    if "with_keywords" not in filters:
        if VERBOSE:
            print("[INFO] Local keyword fallback is disabled in recommend_movies_from_prompt.")

    if not filters.get("with_keywords") and not filters.get("with_genres"):
        if VERBOSE:
            print("[INFO] No strong filters detected — attempting to enrich the user prompt as a movie.")

        prompt_movie_data = get_combined_data(prompt)
        if prompt_movie_data and prompt_movie_data.get("genres"):
            genres = prompt_movie_data.get("genres", [])
            genre_map = load_genre_map()
            genre_ids = [gid for gid, name in genre_map.items() if name in genres]
            if genre_ids:
                filters["with_genres"] = ",".join(genre_ids)
            if prompt_movie_data.get("year"):
                filters["primary_release_year"] = prompt_movie_data.get("year")

            if VERBOSE:
                print(f"[INFO] Extracted fallback filters from prompt movie: {filters}")
            candidates = get_movies_by_filters(filters)
        else:
            if VERBOSE:
                print("[INFO] No usable movie info found from prompt — falling back to GPT.")
            candidates = get_fallback_titles_from_gpt(prompt)
    else:
        candidates = get_movies_by_filters(filters)

        if not candidates:
            if VERBOSE:
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
                if VERBOSE:
                    print(f"[INFO] Found {len(candidates)} matching locally cached movies.")

    if not candidates:
        candidates = get_fallback_titles_from_gpt(prompt)

    enriched_movies = []
    for movie in candidates[:30]:
        title = movie.get("title")
        if VERBOSE:
            print(f"[ENRICHING] Fetching detailed info for: {title}")
        data = get_combined_data(title)
        if data and data.get("title"):
            enriched_movies.append(data)

    if not enriched_movies and candidates:
        if VERBOSE:
            print("[INFO] Fallback mode — skipping scoring filter. Enriched all fallback titles based on GPT output.")
    else:
        if VERBOSE:
            print(f"[INFO] Enriched data for {len(candidates[:30])} movies, usable: {len(enriched_movies)}")

    if not enriched_movies:
        if VERBOSE:
            print("[INFO] No enriched movies with full data — fallback formatting may be GPT-generated.")

    if len(enriched_movies) > 5:
        enriched_movies = [m for m in enriched_movies if m.get("streaming_services")]

    if filters.get("with_watch_providers"):
        provider_ids = filters["with_watch_providers"].split(",")
        allowed_platforms = [WATCH_PROVIDER_MAP.get(pid.strip()) for pid in provider_ids if pid.strip() in WATCH_PROVIDER_MAP]
        allowed_platforms = [p for p in allowed_platforms if p]

        before_count = len(enriched_movies)
        enriched_movies = [
            m for m in enriched_movies
            if any(service in allowed_platforms for service in m.get("streaming_services", []))
        ]
        if VERBOSE:
            print(f"[INFO] Streaming platform filter applied — {len(enriched_movies)} of {before_count} movies kept.")

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

    if VERBOSE:
        print(f"[INFO] Top {len(top_movies)} movies selected for GPT recommendation.")

    # Step 3: Use GPT to select and format top 5 recommendations
    start_time = time.time()
    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a movie expert recommending 5 great films based on user preferences. "
                    f"Today's date is {today_str}. Only use real, released movies. "
                    "If some data is missing (like ratings or streaming info), you may still include the movie and infer its quality based on genre, plot, or known popularity."
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