

import os
import json

# Set up paths
cache_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "movie_cache"))
renamed_count = 0
skipped_count = 0

# Rename all JSON files in the cache
for filename in os.listdir(cache_dir):
    if not filename.endswith(".json"):
        continue

    original_path = os.path.join(cache_dir, filename)

    try:
        with open(original_path, "r") as f:
            data = json.load(f)
        imdb_id = data.get("imdb_id")

        if not imdb_id:
            print(f"[SKIP] No IMDb ID found in {filename}")
            skipped_count += 1
            continue

        new_filename = f"{imdb_id}.json"
        new_path = os.path.join(cache_dir, new_filename)

        if filename != new_filename:
            if not os.path.exists(new_path):
                os.rename(original_path, new_path)
                print(f"[RENAME] {filename} -> {new_filename}")
                renamed_count += 1
            else:
                print(f"[SKIP] Target name {new_filename} already exists.")
        else:
            print(f"[SKIP] {filename} already matches target format.")
    except Exception as e:
        print(f"[ERROR] Could not process {filename}: {e}")
        skipped_count += 1

print(f"\n[SUMMARY] Renamed: {renamed_count}, Skipped: {skipped_count}")