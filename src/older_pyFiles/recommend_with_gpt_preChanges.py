import os
import json
from openai import OpenAI
#from combined_movie_data import get_combined_data,get_movies_by_filters
from combined_movie_data_preChanges import get_combined_data,get_movies_by_filters

from gpt_filters import extract_filters_from_prompt


openai = OpenAI()

def recommend_movies_from_prompt(prompt: str):
    print(f"[INFO] User Prompt: {prompt}")
    
    # Step 1: Extract filters from prompt using ChatGPT
    filters = extract_filters_from_prompt(prompt)
    print(f"[INFO] Extracted Filters: {filters}")

    # Step 2: Get candidate movies using filters
    candidates = get_movies_by_filters(filters)
    print(f"[INFO] Fetched {len(candidates)} candidates from TMDb")

    enriched_movies = []
    for movie in candidates[:30]:
        title = movie.get("title")
        data = get_combined_data(title)
        if data:
            enriched_movies.append(data)

    print(f"[INFO] Enriched data for {len(enriched_movies)} movies")

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

    # Step 3: Use GPT to select and format top 10 recommendations
    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a movie expert recommending great films to users based on their preferences. Pick the best matches from the list, and for each movie, include its Rotten Tomatoes critic score, IMDb rating, and Metascore (if available), where it's available to stream, and a short plot summary."},
            {"role": "user", "content": f"The user prompt was: '{prompt}'\nHere are 20 movie options:\n{json.dumps(top_movies, indent=2)}"}
        ],
        temperature=0.7
    )

    print("\n====== RECOMMENDATIONS ======")
    print(response.choices[0].message.content)
if __name__ == "__main__":
    user_input = input("What kind of movie are you looking for?\n> ")
    recommend_movies_from_prompt(user_input)