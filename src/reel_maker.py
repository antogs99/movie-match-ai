from moviepy.editor import *
from PIL import ImageColor
import os

# --- Movie Info (sample) ---
movie = {
    "title": "The Dark Knight",
    "year": 2008,
    "imdb_rating": 9.0,
    "rotten_tomatoes": 94,
}

# --- Paths ---
poster_path = "../data/posters/11.jpg"  # Local poster image
logo_path = "../data/templates/logo.PNG"
output_path = "data/output/the-dark-knight-reel.mp4"
bg_color = "#0F1C2E"
font = "Arial-Bold"  # Adjust if this fails to render

# --- Video Constants ---
W, H = 768, 1152
duration = 6

# --- Background ---
bg = ColorClip(size=(W, H), color=ImageColor.getrgb(bg_color), duration=duration)

# --- Title ---
title_text = TextClip(
    f"{movie['title']} ({movie['year']})",
    fontsize=48,
    font=font,
    color="white",
    method="caption",
    size=(W - 100, None),
).set_position(("center", 80)).set_start(0).set_duration(2.5).fadein(0.5)

# --- Poster ---
poster = ImageClip(poster_path).resize(width=500)
poster = poster.set_position(lambda t: ("center", int(180 + 100 * (1 - min(t / 0.7, 1)))))
poster = poster.set_start(1.2).set_duration(3.5).fadein(0.7)

# --- Ratings ---
rt = TextClip(f"🍅 {movie['rotten_tomatoes']}%", fontsize=40, font=font, color="white")
imdb = TextClip(f"⭐ {movie['imdb_rating']}", fontsize=40, font=font, color="white")
rt = rt.set_position((W//2 - 150, 1000)).set_start(3.5).set_duration(duration - 3.5).fadein(0.5)
imdb = imdb.set_position((W//2 + 50, 1000)).set_start(3.5).set_duration(duration - 3.5).fadein(0.5)

# --- Logo ---
logo = ImageClip(logo_path).resize(width=130)
logo = logo.set_position((W - 140, 30)).set_start(0).set_duration(duration)

# --- Final Composite ---
final = CompositeVideoClip([bg, title_text, poster, rt, imdb, logo])
final.write_videofile(output_path, fps=24)