import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


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
        return eval(response)
    except Exception:
        print("Failed to parse GPT response:", response)
        return {}