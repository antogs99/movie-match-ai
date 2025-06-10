// Type for extracted filters from prompt
type FilterResult = {
  genres: string[];
  year: number | null;
  keywords: string[];
  tone: string | null;
  platforms: string[];
};
// Helper to extract mentioned streaming platforms from a prompt.
function extractMentionedPlatforms(prompt: string): string[] {
  const knownPlatforms = [
    "Netflix",
    "Hulu",
    "Amazon Prime Video",
    "Prime Video",
    "Disney Plus",
    "Disney+",
    "Max",
    "HBO Max",
    "Peacock",
    "Apple TV+",
    "Paramount+",
    "Paramount Plus",
    "Starz",
    "Showtime",
    "AMC+",
    "Crunchyroll",
    "Tubi",
    "Pluto TV",
    "Freevee"
  ];

  const normalizedPrompt = prompt.toLowerCase();
  return knownPlatforms.filter(platform =>
    normalizedPrompt.includes(platform.toLowerCase())
  ).map(name =>
    // Normalize aliases
    name === "Disney+" ? "Disney Plus"
    : name === "Prime Video" ? "Amazon Prime Video"
    : name === "Paramount Plus" ? "Paramount+"
    : name === "HBO Max" ? "Max"
    : name
  );
}
// src/lib/recommendFromPrompt.ts

// ✅ Summary of Functionality (based on Antonio's rules):
// - Extracts filters from the user's prompt using GPT-4.
// - Fetches movies from TMDb using extracted filters.
// - Filters out incomplete or low-rated results.
// - Enriches each movie with OMDb data and Watchmode platforms.
// - ⏺️ If OMDb enrichment fails, the movie is skipped (logged).
// - ✅ Valid enriched movies are checked against Supabase:
//    - If found → update platform info
//    - If not found → insert full record
// - ⏺️ If no movies are found from TMDb → fallback to GPT-4 direct suggestions
// - ✅ Final step: GPT re-ranks the enriched list and returns top picks.
// - 🔁 Every step includes logging for debugging.
// - ✅ All new logic must be:
//    - Well-commented
//    - Matched to Python logic block-by-block
//    - Faithful to the flow from `production_v1.py`

// Other rules:
// ✅ Always print movie titles being processed.
// ✅ Enforce enrichment checks for plot, poster, and platforms.
// ✅ Print enrichment and Supabase issues with detail.
// ✅ Show JSON from fallback GPT for traceability.
// ✅ Preserve prompt content and genre/keyword accuracy.
// ✅ Explicitly print the Python block we are replicating when adding new TS logic.

import { createClient } from '@supabase/supabase-js';
import OpenAI from 'openai';
import { ChatCompletionMessageParam } from 'openai/resources';

// More flexible filter map for prompt filters
type FilterMap = {
  [key: string]: string | string[] | number | null;
};

const supabase = createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_KEY!);

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY
});

// Step 1: Extract filters from the prompt using OpenAI
async function extractFilters(prompt: string): Promise<FilterMap> {
  const genreMap = {
    '28': 'Action',
    '12': 'Adventure',
    '16': 'Animation',
    '35': 'Comedy',
    '80': 'Crime',
    '99': 'Documentary',
    '18': 'Drama',
    '10751': 'Family',
    '14': 'Fantasy',
    '36': 'History',
    '27': 'Horror',
    '10402': 'Music',
    '9648': 'Mystery',
    '10749': 'Romance',
    '878': 'Science Fiction',
    '10770': 'TV Movie',
    '53': 'Thriller',
    '10752': 'War',
    '37': 'Western'
  };

  const genreList = Object.entries(genreMap).map(([id, name]) => `${id}: ${name}`).join('\n');
  const systemPrompt = `Here are valid TMDb genres:\n${genreList}\n\nExtract a TMDb-compatible filter from a user prompt. Only output a JSON object with keys like with_genres (genre ID), primary_release_year, vote_average.gte, and with_keywords (comma-separated terms).`;

  const completion = await openai.chat.completions.create({
    model: 'gpt-4',
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: prompt }
    ],
    temperature: 0
  });

  const raw = completion.choices[0].message.content || '{}';

  try {
    return JSON.parse(raw);
  } catch {
    console.warn('[WARN] Failed to parse GPT filter output:', raw);
    return {};
  }
}


// Helper: extract filters from prompt (genres, year, keywords, tone, platforms)
export async function extractFiltersFromPrompt(prompt: string): Promise<FilterResult> {
  // Dummy extraction logic; you should replace this with your actual extraction logic
  // For now, let's just extract mentioned platforms and leave others as empty/default.
  const mentionedPlatforms = extractMentionedPlatforms(prompt);
  console.log("[INFO] Detected platform mentions in prompt:", mentionedPlatforms);
  return {
    genres: [],
    year: null,
    keywords: [],
    tone: null,
    platforms: mentionedPlatforms
  };
}

// Step 2: Extract filters from the prompt
// Step 3: Build the TMDb query with those filters
// Step 4: Fetch movie results from TMDb
// Step 5: Filter out low-quality or incomplete results
// Step 6: Enrich each movie with OMDb + platform info
// Step 7: If enrichment fails for all, fallback to OpenAI
// Step 8: Re-rank the enriched movies using OpenAI
export async function recommendFromPrompt(prompt: string) {
  console.log('[INFO] Prompt received:', prompt);

  // Step 2: Extract filters from the prompt using GPT-4
  const filters: FilterMap = await extractFilters(prompt);
  console.log('[DEBUG] Extracted filters:', filters);

  // Detect platforms mentioned in the user's prompt (manual override for GPT misses)
  const mentionedPlatforms = extractMentionedPlatforms(prompt);
  console.log("[INFO] Detected platform mentions in prompt:", mentionedPlatforms);

  const { with_genres, primary_release_year, with_keywords } = filters as { [key: string]: any };

  // Merge detected platforms into filters for downstream usage
  if (mentionedPlatforms.length > 0) {
    filters.platforms = mentionedPlatforms;
    console.log("[INFO] Overriding GPT-detected platforms with:", filters.platforms);
  }

  // Before passing filters to enrichment logic, print debug info
  console.log("[DEBUG] Final filters passed to enrichment:", filters);

  // Step 3: Build the TMDb query with those filters
  const baseParams = new URLSearchParams({
    api_key: process.env.TMDB_API_KEY!,
    sort_by: 'popularity.desc',
  });

  if (with_genres) baseParams.append('with_genres', with_genres.toString());
  if (primary_release_year) baseParams.append('primary_release_year', String(primary_release_year));
  if (with_keywords && with_keywords.trim().length > 0) {
    baseParams.append('with_keywords', with_keywords);
  }

  // Step 4: Fetch movie results from TMDb (pages 1 to 3)
  let allResults: any[] = [];
  for (let page = 1; page <= 3; page++) {
    const pageParams = new URLSearchParams(baseParams);
    pageParams.set('page', String(page));
    const res = await fetch(`https://api.themoviedb.org/3/discover/movie?${pageParams}`);
    const json = await res.json();
    if (json.results) {
      allResults.push(...json.results);
    }
  }

  // Step 5: Filter out low-quality or incomplete results
  const filtered = allResults.filter(m =>
    m.poster_path &&
    m.vote_average > 5 &&
    m.title &&
    m.release_date
  );

  console.log('[API] Raw TMDb titles fetched:', filtered.map(m => m.title));

  const moviesToEnrich = filtered.slice(0, 30);

  // Step 6: Enrich each movie with OMDb + TMDb metadata + platform info
  // Python block replicated: enrichment with checks for plot, poster, platforms
  const enriched = await Promise.all(moviesToEnrich.map(async (movie: any) => {
    try {
      const title = movie.title;
      const year = movie.release_date?.split('-')[0] || '';
      const poster_url = `https://image.tmdb.org/t/p/w500${movie.poster_path}`;

      // Enforce essential fields presence
      if (!title || !year || !poster_url) {
        console.warn(`[SKIP] Missing essential fields for movie: ${title} (${year})`);
        return null;
      }

      // Fetch OMDb data for enrichment
      const omdbData = await getOMDbData(title, year);
      if (!omdbData) {
        console.warn(`[OMDB FAIL] Could not enrich: ${title} (${year})`);
        return null;
      }

      // Fetch TMDb metadata for enrichment (genre names, runtime, etc)
      const tmdbMeta = await getTMDbMetadataFromTitleYear(title, year);
      if (!tmdbMeta) {
        console.warn(`[TMDb Meta FAIL] Could not enrich: ${title} (${year})`);
        return null;
      }

      // Fetch streaming platforms via Watchmode or mock function
      const streaming_services = await getStreamingPlatforms(title, movie.release_date);
      // Logging for streaming platform filtering (simulate filterMoviesByStreamingServices)
      if (filters.platforms) {
        console.log("[INFO] Filtering movies for platforms:", filters.platforms);
        console.log("[INFO] Movie", title, "has services:", streaming_services);
      }

      // Enforce presence of plot and streaming platforms
      if (!omdbData.plot || omdbData.plot === 'N/A' || !streaming_services || streaming_services.length === 0) {
        console.warn(`[SKIP] Plot/platform missing: ${title} (${year})`);
        return null;
      }

      // Return enriched movie object
      return {
        title,
        year: parseInt(year),
        genres: tmdbMeta.genres,
        streaming_services,
        imdb_id: omdbData.imdb_id,
        tmdb_id: tmdbMeta.tmdb_id,
        imdb_rating: omdbData.imdb_rating,
        metascore: omdbData.metascore,
        rotten_tomatoes: omdbData.rotten_tomatoes,
        plot: omdbData.plot,
        director: omdbData.director,
        runtime: tmdbMeta.runtime ?? omdbData.runtime,
        main_cast: omdbData.main_cast,
        poster_url: omdbData.poster_url || poster_url
      };
    } catch (err) {
      console.error('[ENRICH ERROR]', err);
      return null;
    }
  }));

  // Filter out nulls from enrichment
  const highQuality = enriched.filter(Boolean);

  console.log('📋 Movie titles to be sent to GPT:');
  highQuality.forEach(movie => {
    if (movie) {
      console.log('-', movie.title);
    }
  });

  // Step 6.5: Sync enriched movies with Supabase
  // Python block replicated: check if movie exists, update or insert accordingly
  for (const movie of highQuality) {
    if (!movie) continue;

    // Check if movie already exists in Supabase by title and year
    const { data: existing, error } = await supabase
      .from('movies')
      .select('*')
      .eq('title', movie.title)
      .eq('year', movie.year)
      .maybeSingle();

    if (error) {
      console.warn(`[SUPABASE CHECK ERROR] ${movie.title}:`, error.message);
      continue;
    }

    if (existing) {
      // Update streaming platforms for existing movie record using composite keys
      const { error: updateError } = await supabase
        .from('movies')
        .update({ streaming_services: movie.streaming_services })
        .eq('title', movie.title)
        .eq('year', movie.year);

      if (updateError) {
        console.error(`[SUPABASE UPDATE ERROR] ${movie.title}:`, updateError.message);
      } else {
        console.log(`[SUPABASE] Updated platforms for: ${movie.title}`);
      }
    } else {
      // Insert new movie record into Supabase with error logging
      const { error: insertError } = await supabase.from('movies').insert([movie]);
      if (insertError) {
        console.error(`[SUPABASE INSERT ERROR] ${movie.title}:`, insertError.message);
      } else {
        console.log(`[SUPABASE] Inserted new movie: ${movie.title}`);
      }
    }
  }

  // Step 7: If enrichment fails for all movies, fallback to OpenAI direct suggestions
  // Python block replicated: fallback GPT call for direct movie titles + enrichment
  if (highQuality.length === 0) {
    console.warn('[FALLBACK] No movies found in TMDb — asking GPT for direct titles...');

    // Prompt GPT-4 to suggest 15 movie titles (title + year) as JSON array
    const systemPrompt = `You are a movie recommendation engine. Based on the user prompt, suggest 15 movie titles (just title and year). Respond ONLY with a JSON array of objects like this:
    [
      { "title": "The Fault in Our Stars", "year": 2014 },
      { "title": "Me and Earl and the Dying Girl", "year": 2015 }
    ]`;

    const completion = await openai.chat.completions.create({
      model: 'gpt-4',
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: prompt }
      ],
      temperature: 0.7
    });

    // Parse fallback GPT JSON list and log for traceability
    const fallbackList = JSON.parse(completion.choices[0].message.content || '[]');
    console.log('[FALLBACK GPT LIST]', fallbackList);

    // Enrich fallback list with OMDb + streaming platforms + TMDb meta
    const enriched = await Promise.all(
      fallbackList.map(async (item: { title: string; year: number }) => {
        const omdbRes = await fetch(`https://www.omdbapi.com/?apikey=${process.env.OMDB_API_KEY}&t=${encodeURIComponent(item.title)}&y=${item.year}`);
        const omdbData = await omdbRes.json();

        const streaming_services = await getStreamingPlatforms(item.title, String(item.year));
        const tmdbMeta = await getTMDbMetadataFromTitleYear(item.title, String(item.year));

        return {
          title: item.title,
          year: item.year,
          genres: tmdbMeta?.genres || [],
          streaming_services,
          imdb_id: omdbData.imdbID || null,
          tmdb_id: tmdbMeta?.tmdb_id || null,
          imdb_rating: omdbData.imdbRating && omdbData.imdbRating !== 'N/A' ? parseFloat(omdbData.imdbRating) : null,
          metascore: omdbData.Metascore && omdbData.Metascore !== 'N/A' ? parseInt(omdbData.Metascore) : null,
          rotten_tomatoes: parseInt(
            omdbData.Ratings?.find((r: any) => r.Source === 'Rotten Tomatoes')?.Value?.replace('%', '') || ''
          ) || null,
          plot: omdbData.Plot && omdbData.Plot !== 'N/A' ? omdbData.Plot : '',
          poster_url: omdbData.Poster && omdbData.Poster !== 'N/A' ? omdbData.Poster : '',
          runtime: tmdbMeta?.runtime ?? (
            omdbData.Runtime && omdbData.Runtime.includes('min')
              ? parseInt(omdbData.Runtime.match(/\d+/)?.[0] || '')
              : null
          ),
          director: omdbData.Director || '',
          main_cast: omdbData.Actors ? omdbData.Actors.split(',').map((a: string) => a.trim()) : []
        };
      })
    );

    // Python block replicated: fallback OMDb/platform enrichment + Supabase upsert
    // Insert Supabase sync logic for fallback movies
    for (const movie of enriched.filter(Boolean)) {
      const { data: existing, error } = await supabase
        .from('movies')
        .select('*')
        .eq('title', movie.title)
        .eq('year', movie.year)
        .maybeSingle();

      if (error) {
        console.warn(`[SUPABASE CHECK ERROR] ${movie.title}:`, error.message);
        continue;
      }

      if (existing) {
        const { error: updateError } = await supabase
          .from('movies')
          .update({ streaming_services: movie.streaming_services })
          .eq('title', movie.title)
          .eq('year', movie.year);

        if (updateError) {
          console.error(`[SUPABASE UPDATE ERROR] ${movie.title}:`, updateError.message);
        } else {
          console.log(`[SUPABASE] Updated fallback platforms for: ${movie.title}`);
        }
      } else {
        const { error: insertError } = await supabase.from('movies').insert([movie]);
        if (insertError) {
          console.error(`[SUPABASE INSERT ERROR] ${movie.title}:`, insertError.message);
        } else {
          console.log(`[SUPABASE] Inserted fallback movie: ${movie.title}`);
        }
      }
    }

    // Return enriched fallback movies, filtering out nulls if any
    return enriched.filter(Boolean);
  }

  // Step 8: Re-rank the enriched movies using OpenAI GPT-4
  // Python block replicated: send movies + prompt to GPT for top picks selection
  const finalPrompt: ChatCompletionMessageParam[] = [
    {
      role: 'system',
      content: `You are a movie expert. From the list of movie objects, select the 5–10 best ones based on the user's preferences. Return a valid JSON array of full movie objects exactly as provided — do not summarize or change the format.`,
    },
    {
      role: 'user',
      content: `Prompt: ${prompt}\n\nMovies:\n${JSON.stringify(highQuality, null, 2)}`,
    }
  ];

  let clean = '[]';
  try {
    const chatRes = await openai.chat.completions.create({
      model: 'gpt-4',
      messages: finalPrompt,
      temperature: 0.4
    });
    clean = chatRes.choices[0].message.content || '[]';
    console.log('📥 Raw GPT response:', clean);
    const parsed = JSON.parse(clean);
    console.log('📦 Parsed GPT results:', parsed);
    return parsed;
  } catch (err) {
    console.error('[ERROR] Failed to parse GPT re-rank response:', err);
    // Fallback: return top 5 enriched movies if GPT re-rank fails
    return highQuality.slice(0, 5);
  }
}

async function getFallbackRecommendations(prompt: string) {
  console.log('[FALLBACK] No results from Supabase — fetching from TMDb/OMDb');

  // TODO: Step 1 — call OpenAI to extract filters
  // TODO: Step 2 — use those filters to fetch from TMDb
  // TODO: Step 3 — enrich each result with OMDb + poster URL
  // TODO: Step 4 — format into top 5–10 recommendations
  // TODO: (Optional) call OpenAI to summarize final picks

  return [];
}

// Mirrors Python logic: fetches streaming platforms for a movie via TMDb /watch/providers
async function getStreamingPlatforms(title: string, releaseDate: string): Promise<string[]> {
  try {
    // Step 1: Search TMDb for the movie by title and year
    const searchUrl = `https://api.themoviedb.org/3/search/movie?api_key=${process.env.TMDB_API_KEY}&query=${encodeURIComponent(title)}&year=${releaseDate.split('-')[0]}`;
    const tmdbRes = await fetch(searchUrl);
    const tmdbData = await tmdbRes.json();

    const movieId = tmdbData.results?.[0]?.id;
    if (!movieId) {
      console.warn(`[TMDb] No TMDb ID found for: ${title}`);
      return [];
    }

    // Step 2: Use the movie ID to get watch providers
    const providerUrl = `https://api.themoviedb.org/3/movie/${movieId}/watch/providers?api_key=${process.env.TMDB_API_KEY}`;
    const providerRes = await fetch(providerUrl);
    const providerData = await providerRes.json();

    const usSources = providerData?.results?.US?.flatrate || [];
    const streamingServices = usSources.map((s: any) => s.provider_name);

    console.log(`[TMDb] Streaming platforms for ${title}:`, streamingServices);
    return streamingServices;
  } catch (err) {
    console.error(`[ERROR] Failed to fetch streaming platforms for ${title}:`, err);
    return [];
  }
}
// Fetches detailed OMDb data for a movie given a title and year.
async function getOMDbData(title: string, year: string): Promise<{
  imdb_id: string | null;
  imdb_rating: number | null;
  metascore: number | null;
  rotten_tomatoes: number | null;
  plot: string;
  director: string;
  runtime: number | null;
  main_cast: string[];
  poster_url: string | null;
} | null> {
  try {
    const url = `https://www.omdbapi.com/?apikey=${process.env.OMDB_API_KEY}&t=${encodeURIComponent(title)}&y=${year}`;
    const res = await fetch(url);
    const data = await res.json();
    if (!data || data.Response === 'False') return null;
    const imdb_id = data.imdbID || null;
    const imdb_rating = data.imdbRating && data.imdbRating !== 'N/A' ? parseFloat(data.imdbRating) : null;
    const metascore = data.Metascore && data.Metascore !== 'N/A' ? parseInt(data.Metascore) : null;
    const rotten_tomatoes = data.Ratings?.find((r: any) => r.Source === 'Rotten Tomatoes')
      ? parseInt(data.Ratings.find((r: any) => r.Source === 'Rotten Tomatoes').Value.replace('%', ''))
      : null;
    const plot = data.Plot && data.Plot !== 'N/A' ? data.Plot : '';
    const director = data.Director && data.Director !== 'N/A' ? data.Director : '';
    const runtime = data.Runtime && data.Runtime.includes('min')
      ? parseInt(data.Runtime.match(/\d+/)?.[0] || '')
      : null;
    const main_cast = data.Actors && data.Actors !== 'N/A' ? data.Actors.split(',').map((a: string) => a.trim()) : [];
    const poster_url = data.Poster && data.Poster !== 'N/A' ? data.Poster : null;
    return {
      imdb_id,
      imdb_rating,
      metascore,
      rotten_tomatoes,
      plot,
      director,
      runtime,
      main_cast,
      poster_url
    };
  } catch (err) {
    console.error('[OMDb ERROR]', err);
    return null;
  }
}

// Fetches TMDb metadata for a movie by title and year, returning genre names, tmdb_id, and runtime.
async function getTMDbMetadataFromTitleYear(title: string, year: string): Promise<{
  tmdb_id: number | null,
  genres: string[],
  runtime: number | null
} | null> {
  try {
    // 1. Search TMDb for the movie by title and year
    const searchUrl = `https://api.themoviedb.org/3/search/movie?api_key=${process.env.TMDB_API_KEY}&query=${encodeURIComponent(title)}&year=${year}`;
    const searchRes = await fetch(searchUrl);
    const searchData = await searchRes.json();
    const result = searchData.results?.[0];
    if (!result) return null;
    const tmdb_id = result.id;
    // 2. Fetch movie details to get genres and runtime
    const detailsUrl = `https://api.themoviedb.org/3/movie/${tmdb_id}?api_key=${process.env.TMDB_API_KEY}`;
    const detailsRes = await fetch(detailsUrl);
    const details = await detailsRes.json();
    if (!details) return null;
    const genres = Array.isArray(details.genres) ? details.genres.map((g: any) => g.name) : [];
    const runtime = details.runtime ?? null;
    return {
      tmdb_id,
      genres,
      runtime
    };
  } catch (err) {
    console.error('[TMDb Meta ERROR]', err);
    return null;
  }
}