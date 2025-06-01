import { NextRequest, NextResponse } from 'next/server';
import axios from 'axios';

const TMDB_API_KEY = process.env.TMDB_API_KEY;
const WATCHMODE_API_KEY = process.env.WATCHMODE_API_KEY;

const genreMap: Record<string, number> = {
  action: 28,
  adventure: 12,
  animation: 16,
  comedy: 35,
  crime: 80,
  documentary: 99,
  drama: 18,
  family: 10751,
  fantasy: 14,
  history: 36,
  horror: 27,
  music: 10402,
  mystery: 9648,
  romance: 10749,
  sciencefiction: 878,
  scifi: 878,
  thriller: 53,
  war: 10752,
  western: 37
};

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const userQuery = body.query;

    if (!userQuery || typeof userQuery !== 'string') {
      console.error('❌ Invalid query:', userQuery);
      return NextResponse.json({ results: [] });
    }

    console.log('📝 Received query:', userQuery);

    // STEP 1: Use GPT to extract topic and optional year
    const chat = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: 'gpt-4o',
        messages: [
          {
            role: 'system',
            content: `You are a movie search assistant helping users find content using the TMDb API. 
Return structured JSON like this:
{ "topic": "Marvel Cinematic Universe", "year": 2023 }
If no year is mentioned, omit it. Use simple values. Do not explain.`
          },
          {
            role: 'user',
            content: userQuery,
          },
        ],
        temperature: 0,
      }),
    });

    const gpt = await chat.json();
    const { topic, year } = JSON.parse(gpt.choices[0].message.content || '{}');

    console.log('🧠 GPT topic:', { topic, year });

    // Match genre
    const matchedGenre = Object.keys(genreMap).find(g => topic?.toLowerCase().includes(g));
    console.log('🎯 Matched genre:', matchedGenre);
console.log('Parsed GPT topic:', topic);
console.log('Matched genre:', matchedGenre);
console.log('Parsed year:', year);
    let keywordId;
    if (topic) {
      const keywordSearch = await axios.get<any>('https://api.themoviedb.org/3/search/keyword', {
        params: {
          api_key: TMDB_API_KEY,
          query: topic,
        },
      });

      console.log('🔍 Raw TMDb keyword results:', keywordSearch.data);

      const keywordMatch = keywordSearch.data?.results?.find((k: any) =>
        k.name.toLowerCase().includes(topic.toLowerCase())
      );

      if (keywordMatch) {
        keywordId = keywordMatch.id;
        console.log('🔑 TMDb Keyword found:', keywordMatch);
      } else {
        console.warn('⚠️ No keyword ID found from TMDb search');
      }
    }

    // STEP 2: Discover movies with filters
    const discoverRes = await axios.get<any>('https://api.themoviedb.org/3/discover/movie', {
      params: {
        api_key: TMDB_API_KEY,
        sort_by: 'popularity.desc',
        include_adult: false,
        with_keywords: keywordId || undefined,
        with_genres: !keywordId && matchedGenre ? genreMap[matchedGenre] : undefined,
        primary_release_year: year || undefined,
      },
    });

    const discoverResults = Array.isArray(discoverRes.data?.results) ? discoverRes.data.results.slice(0, 3) : [];
    console.log('🎬 Final discover results count:', discoverResults.length);

    const results = await Promise.all(
      discoverResults.map(async (movie: any) => {
        const watchSearch = await axios.get<any>('https://api.watchmode.com/v1/search/', {
          params: {
            apiKey: WATCHMODE_API_KEY,
            search_value: movie.title,
            search_field: 'name',
          },
        });

        const wmId = watchSearch.data?.title_results?.[0]?.id;

        let streaming: string[] = [];
        if (wmId) {
          const wmSources = await axios.get<any>(`https://api.watchmode.com/v1/title/${wmId}/sources/`, {
            params: { apiKey: WATCHMODE_API_KEY },
          });

          streaming = wmSources.data?.filter((s: any) => s.type === 'sub' && s.region === 'US')?.map((s: any) => s.name) || [];
        }

        return {
          title: movie.title,
          description: movie.overview,
          image: movie.poster_path
            ? `https://image.tmdb.org/t/p/w500${movie.poster_path}`
            : '',
          year: movie.release_date?.slice(0, 4),
          streaming,
        };
      })
    );

    return NextResponse.json({ results });
  } catch (err: any) {
    console.error('❌ Error:', err.message);
    return NextResponse.json({ results: [] });
  }
}