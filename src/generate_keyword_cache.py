# generate_keyword_cache.py

import requests
import json
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path="../.env.local")

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BEARER_TOKEN = os.getenv("TMDB_BEARER_TOKEN")

headers = {
    "accept": "application/json"
}
if TMDB_BEARER_TOKEN:
    headers["Authorization"] = f"Bearer {TMDB_BEARER_TOKEN}"


def fetch_keyword_id(keyword):
    url = "https://api.themoviedb.org/3/search/keyword"
    params = {"query": keyword}
    if not TMDB_BEARER_TOKEN:
        params["api_key"] = TMDB_API_KEY
    try:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            return results[0]["id"]
    except Exception as e:
        print(f"[ERROR] Failed to fetch keyword for '{keyword}': {e}")
    return None


def main():
    keywords_to_fetch = [
        "incest", "amputation", "bipolar", "alzheimer's", "paranoia", "child abuse",
        "ptsd", "dementia", "euthanasia", "bullying", "cheating", "homelessness",
        "loner", "depression", "cannibal", "anorexia", "autism", "blindness", "deafness",
        "heist", "abduction", "blackmail", "grief counseling", "parenthood", "midlife crisis",
        "identity theft", "obsession", "jealousy", "ritual", "witch", "paranormal", "superstition",
        "urban legend", "time loop", "possession", "exorcism", "curse", "telekinesis", "telepathy",
        "coma", "psych ward", "lobotomy", "hallucination", "doppelganger", "stalker", "runaway",
        "revenge porn", "sex trafficking", "priest", "nun", "ex-con", "mobster", "witness protection",
        "undercover", "nuclear war", "famine", "plague", "bioweapon", "body horror", "splatter",
        "hallucinogen", "drug trip", "drunk", "hangover", "rehab", "marriage crisis", "divorce",
        "arranged marriage", "open relationship", "polyamory", "infidelity", "adoption", "surrogate",
        "ivf", "bounty hunter", "fugitive", "immigrant", "refugee", "language barrier", "cross-cultural",
        "race relations", "segregation", "civil rights", "activism", "revolution", "class struggle",
        "capitalism", "socialism", "anarchy", "concentration camp", "genocide", "interrogation",
        "brainwashing", "totalitarianism", "surveillance", "mass hysteria", "suicide pact","cartel","narco","history","war","hitler","jew"
        "missing child", "child soldier", "forensic", "criminology", "espionage", "sleeper agent",
        "narcissist", "panic attack", "gaslighting", "cult", "serial rapist", "cyberbullying", "police brutality", "prison escape", "wrongful conviction", "trauma", "nightmare", "child neglect", "sexual repression", "religious fanatic", "grifter", "catfishing", "military experiment", "mental breakdown", "parapsychology", "repressed memory", "estranged siblings", "sibling rivalry", "unwanted pregnancy", "school shooting", "school bullying", "missing persons", "toxic friendship", "incel", "femme fatale", "quiet quitting", "disfigurement", "psychosis", "panic disorder", "gas leak", "hypnosis", "extinction", "mass extinction", "animal cruelty", "panic room", "digital addiction"
    ]

    cache = {}
    for keyword in keywords_to_fetch:
        keyword_id = fetch_keyword_id(keyword)
        if keyword_id:
            print(f"[INFO] {keyword}: {keyword_id}")
            cache[keyword] = keyword_id

    os.makedirs("../data", exist_ok=True)
    with open("../data/tmdb_keywords.json", "w") as f:
        json.dump(cache, f, indent=2)
    print("[SUCCESS] Saved keyword cache to data/tmdb_keywords.json")


if __name__ == "__main__":
    main()