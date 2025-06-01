import os
import requests
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env.local")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
WATCHMODE_API_KEY = os.getenv("WATCHMODE_API_KEY")

# Step 1: Simulate a user query
user_query = "thriller or horror movie like longlegscle"

# Step 2: Ask GPT to extract a search topic
extract_topic_prompt = f"""
You are a movie assistant helping users find similar films.

User query: "{user_query}"

Extract a clear genre (pick only from this list: Action, Action & Adventure, Adult, Adventure, Animation, Anime, Biography, Comedy, Crime, Documentary, Drama, Family, Fantasy, Food, Game Show, History, Horror, Kids, Music, Musical, Mystery, Nature, News, Reality, Romance, Sci-Fi & Fantasy, Science Fiction, Soap, Sports, Supernatural, Talk, Thriller, Travel, TV Movie, War, War & Politics, Western), release year (if mentioned), and streaming platforms mentioned in the query. If the genre or year is not explicitly mentioned, infer it based on the tone, movies referenced, or themes.

Respond in JSON format like:
{{
  "topic": "Science Fiction",
  "year": 2020,
  "platforms": ["Netflix", "Peacock"]
}}

Only return a single genre as 'topic'. If year is not present in the query, omit it.
"""

print("🎯 Asking GPT to extract a topic...")
topic_response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "Extract a search topic from the user query."},
        {"role": "user", "content": extract_topic_prompt}
    ]
)

topic_raw = topic_response.choices[0].message.content
print("\n🧠 GPT Raw Topic Response:")
print(topic_raw)

import json
try:
    cleaned = topic_raw.strip().strip("```json").strip("```").strip()
    parsed = json.loads(cleaned)
    extracted_topic = parsed.get("topic")
    user_platforms = parsed.get("platforms", [])
    extracted_year = parsed.get("year")
    print(f"📅 Extracted year: {extracted_year}")
    if not user_platforms:
        print("ℹ️ No platforms mentioned. Assuming user has access to all major services.")
        user_platforms = ["Netflix", "Hulu", "Prime Video", "Max", "Disney+", "Peacock", "Paramount+"]
except Exception as e:
    print("❌ Failed to parse GPT response:", e)
    extracted_topic = None
    user_platforms = []
    extracted_year = None

if not extracted_topic:
    print("🚫 No topic extracted. Exiting.")
    exit()

print(f"\n🔍 Using topic: '{extracted_topic}'")

# Step 3: Search Watchmode for related titles
print("\n📡 Searching Watchmode for real candidates...")
discover_url = "https://api.watchmode.com/v1/list-titles/"
genre_lookup = {
    "action": 1,
    "action & adventure": 39,
    "adult": 30,
    "adventure": 2,
    "animation": 3,
    "anime": 33,
    "biography": 31,
    "comedy": 4,
    "crime": 5,
    "documentary": 6,
    "drama": 7,
    "family": 8,
    "fantasy": 9,
    "food": 34,
    "game show": 28,
    "history": 10,
    "horror": 11,
    "kids": 21,
    "music": 12,
    "musical": 32,
    "mystery": 13,
    "nature": 36,
    "news": 22,
    "reality": 23,
    "romance": 14,
    "sci-fi & fantasy": 40,
    "science fiction": 15,
    "soap": 25,
    "sports": 29,
    "supernatural": 37,
    "talk": 26,
    "thriller": 17,
    "travel": 35,
    "tv movie": 38,
    "war": 18,
    "war & politics": 41,
    "western": 19
}

service_lookup = {
    "netflix": 203,
    "hulu": 157,
    "prime video": 26,
    "disney+": 372,
    "hbo max": 387,
    "max": 387,
    "apple tv+": 371,
    "peacock": 389,
    "paramount+": 444,
    "showtime": 432
}

from difflib import get_close_matches

topic_lower = extracted_topic.lower()
genre_names = list(genre_lookup.keys())
match = get_close_matches(topic_lower, genre_names, n=1, cutoff=0.6)

params = {
    "apiKey": WATCHMODE_API_KEY,
    "types": "movie",
    "regions": "US",
    "limit": 10,
    "user_rating_low": 7,
    "sort_by": "popularity_desc"
}

if extracted_year:
    params["release_date_start"] = int(f"{extracted_year}0101")

# If platforms were mentioned, limit to source_ids
source_ids = [str(service_lookup[p.lower()]) for p in user_platforms if p.lower() in service_lookup]
if source_ids:
    params["source_ids"] = ",".join(source_ids)

if match:
    genre_id = genre_lookup[match[0]]
    print(f"✅ Matched genre '{match[0]}' → ID {genre_id}")
    params["genres"] = genre_id
else:
    print("❌ No genre match found, using topic as keyword instead.")
    params["keywords"] = extracted_topic.lower()

print(f"\n🔧 Discover Params: {params}")

print("\n📦 Enriching candidates with details...")
candidates = []
page = 1
max_pages = 10

while len(candidates) < 30 and page <= max_pages:
    params["page"] = page
    use_mock_data = True  # Set to False to use real API calls
    if use_mock_data:
        mock_dir = Path(__file__).resolve().parent.parent / "data" / "mock_data"
        mock_discover_file = mock_dir / "discover_thriller.json"
        try:
            with open(mock_discover_file) as f:
                discover_data = json.load(f)
            print(f"📁 Loaded mock discover data from {mock_discover_file.name}")
        except FileNotFoundError:
            print(f"❌ Mock discover data not found: {mock_discover_file}")
            break
    else:
        discover_res = requests.get(discover_url, params=params)
        if discover_res.status_code != 200:
            print(f"❌ Watchmode Discover Failed (page {page}):", discover_res.text)
            break
        discover_data = discover_res.json()
    candidates_raw = discover_data.get("titles", [])

    if not candidates_raw:
        if "genres" in params:
            print(f"⚠️ No titles on page {page} with genre {params['genres']}. Trying again without genre filter...")
            del params["genres"]
            page = 1
            continue
        else:
            print(f"⚠️ No titles on page {page} even without genre filter. Giving up.")
            break

    for item in candidates_raw:
        title_id = item["id"]
        print(f"🔎 Checking title ID {title_id}...")

        use_mock_data = True  # Set to False to use real API calls

        if use_mock_data:
            mock_dir = Path(__file__).resolve().parent.parent / "data" / "mock_data"
            try:
                with open(mock_dir / f"details_{title_id}.json") as f:
                    details = json.load(f)
                with open(mock_dir / f"sources_{title_id}.json") as f:
                    sources = json.load(f)
                print(f"📁 Loaded mock data for title ID {title_id}")
            except FileNotFoundError:
                print(f"⚠️ Mock data not found for title ID {title_id}, skipping...")
                continue
        else:
            details_res = requests.get(
                f"https://api.watchmode.com/v1/title/{title_id}/details/",
                params={"apiKey": WATCHMODE_API_KEY}
            )
            sources_res = requests.get(
                f"https://api.watchmode.com/v1/title/{title_id}/sources/",
                params={"apiKey": WATCHMODE_API_KEY}
            )

            if details_res.status_code != 200:
                print("⚠️ Skipped due to missing details")
                continue

            details = details_res.json()
            sources = sources_res.json() if sources_res.status_code == 200 else []

        # Log Watchmode user and critic scores for debugging
        print(f"🧪 Watchmode Scores for '{details.get('title')}': User Rating = {details.get('user_rating')}, Critic Score = {details.get('critic_score')}")

        # Extract Rotten Tomatoes scores if available
        rt_audience = None
        rt_critic = None
        for s in sources:
            if s.get("name") == "Rotten Tomatoes" and s.get("region") == "US":
                if s.get("audience_score") is not None:
                    rt_audience = s.get("audience_score")
                if s.get("critic_score") is not None:
                    rt_critic = s.get("critic_score")

        # Fallback to justwatch_rating or tmdb_score if RT scores are not found
        if rt_audience is None and rt_critic is None:
            rt_audience = details.get("justwatch_rating")
            if rt_audience is None:
                rt_audience = details.get("tmdb_score")

        # Log all scores for debugging
        print(f"📊 Scores for '{details.get('title')}': RT Audience = {rt_audience}, RT Critic = {rt_critic}, JustWatch = {details.get('justwatch_rating')}, TMDb = {details.get('tmdb_score')}")

        platforms = list({s["name"] for s in sources if s.get("region") == "US"})

        if not platforms:
            print(f"⚠️ No streaming info for '{details.get('title')}' — including anyway")

        candidates.append({
            "title": details.get("title"),
            "year": details.get("year"),
            "platforms": platforms,
            "audience_score": rt_audience if rt_audience is not None else 0,
            "critic_score": rt_critic,
            "genre": details.get("genre_names", []),
            "summary": details.get("plot_overview", ""),
            "user_rating": details.get("user_rating"),
            "wm_critic_score": details.get("critic_score"),
        })

        if len(candidates) >= 30:
            break

    page += 1

if not candidates:
    print("🚫 No usable movie candidates found.")
    exit()

# Step 5: Format and send to GPT for reasoning
print("\n🧠 Sending candidates to GPT for recommendations...")

movie_block = "\n".join([
    f"{i+1}. {c['title']} ({c['year']}) - {', '.join(c['genre'])} | {', '.join(c['platforms'])} | RT: {int(c['audience_score'])}% / Critic: {int(c['critic_score']) if c['critic_score'] is not None else 'N/A'}% | WM: {c['user_rating']}/10 / {c['wm_critic_score']}/100\n   {c['summary']}"
    for i, c in enumerate(candidates)
])

recommendation_prompt = f"""
You are MovieMatch AI, a personalized movie recommender.

The user asked: "{user_query}"
They have access to: {', '.join(user_platforms)}.
Only recommend movies with audience scores ≥ 70.

Here are movie candidates:
{movie_block}

Pick up to 2 movies from the list and explain why each would fit the user's request.
"""

final_response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "You recommend movies based on user preferences and available platforms."},
        {"role": "user", "content": recommendation_prompt}
    ]
)

print("\n🎬 Final GPT Recommendation:\n")
print(final_response.choices[0].message.content)