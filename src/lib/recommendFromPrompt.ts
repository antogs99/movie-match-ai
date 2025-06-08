// src/lib/recommendFromPrompt.ts
import { createClient } from '@supabase/supabase-js';
import OpenAI from 'openai';
import { ChatCompletionMessageParam } from 'openai/resources';

const supabase = createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_KEY!);

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY
});

async function extractFilters(prompt: string): Promise<Record<string, string>> {
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

// TODO: integrate OpenAI, genre lookup, Supabase, TMDb/OMDb calls, etc.

export async function recommendFromPrompt(prompt: string) {
  console.log('[INFO] Prompt received:', prompt);

  const filters = await extractFilters(prompt);
  console.log('[DEBUG] Extracted filters:', filters);

  const { with_genres, primary_release_year, with_keywords } = filters;

  const baseParams = new URLSearchParams({
    api_key: process.env.TMDB_API_KEY!,
    sort_by: 'popularity.desc',
  });

  if (with_genres) baseParams.append('with_genres', with_genres.toString());
  if (primary_release_year) baseParams.append('primary_release_year', String(primary_release_year));
  if (with_keywords && with_keywords.trim().length > 0) {
    baseParams.append('with_keywords', with_keywords);
  }

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

  const filtered = allResults.filter(m =>
    m.poster_path &&
    m.vote_average > 5 &&
    m.title &&
    m.release_date
  );

  console.log('[API] Raw TMDb titles fetched:', filtered.map(m => m.title));

  const moviesToEnrich = filtered.slice(0, 30);

  const enriched = await Promise.all(moviesToEnrich.map(async (movie: any) => {
    const omdbRes = await fetch(`https://www.omdbapi.com/?apikey=${process.env.OMDB_API_KEY}&t=${encodeURIComponent(movie.title)}&y=${movie.release_date?.split('-')[0] || ''}`);
    const omdbData = await omdbRes.json();

    // Replace this with real streaming data logic later
    const streaming_services = await getStreamingPlatforms(movie.title, movie.release_date);

    return {
      title: movie.title,
      year: parseInt(movie.release_date?.split('-')[0] || '0'),
      genres: movie.genre_ids,
      streaming_services,
      imdb_rating: parseFloat(omdbData.imdbRating) || null,
      rotten_tomatoes: parseInt(omdbData.Ratings?.find((r: any) => r.Source === 'Rotten Tomatoes')?.Value?.replace('%', '') || '') || null,
      plot: omdbData.Plot,
      poster_url: `https://image.tmdb.org/t/p/w500${movie.poster_path}`
    };
  }));

  const highQuality = enriched.filter(m =>
    m.plot && m.plot.length > 30 && m.imdb_rating
  );

  console.log('📋 Movie titles to be sent to GPT:');
  highQuality.forEach(movie => console.log('-', movie.title));

  if (highQuality.length === 0) {
    console.warn('[FALLBACK] No movies found in TMDb — asking GPT for direct titles...');

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

    const fallbackList = JSON.parse(completion.choices[0].message.content || '[]');
    console.log('[FALLBACK GPT LIST]', fallbackList);

    const enriched = await Promise.all(
      fallbackList.map(async (item: { title: string; year: number }) => {
        const omdbRes = await fetch(`https://www.omdbapi.com/?apikey=${process.env.OMDB_API_KEY}&t=${encodeURIComponent(item.title)}&y=${item.year}`);
        const omdbData = await omdbRes.json();

        const streaming_services = await getStreamingPlatforms(item.title, String(item.year));

        return {
          title: item.title,
          year: item.year,
          genres: [],
          streaming_services,
          imdb_rating: parseFloat(omdbData.imdbRating) || null,
          rotten_tomatoes: parseInt(omdbData.Ratings?.find((r: any) => r.Source === 'Rotten Tomatoes')?.Value?.replace('%', '') || '') || null,
          plot: omdbData.Plot,
          poster_url: omdbData.Poster && omdbData.Poster !== 'N/A' ? omdbData.Poster : ''
        };
      })
    );

    return enriched.filter(Boolean);
  }

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

async function getStreamingPlatforms(title: string, releaseDate: string) {
  // Placeholder: return empty or simulate platforms for testing
  return ['Netflix', 'Hulu']; // mock
}