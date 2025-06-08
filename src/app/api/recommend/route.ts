// src/app/api/recommend/route.ts
import { NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';

export async function POST(req: Request) {
  const { prompt } = await req.json();
  const filters = processPrompt(prompt);

  console.log('Received prompt:', prompt);
  console.log('Parsed filters:', filters);

  const genreCapitalized = filters.genre.charAt(0).toUpperCase() + filters.genre.slice(1).toLowerCase();

  const { data, error } = await supabase
    .from('movies')
    .select('title,year,genres,streaming_services,imdb_rating,rotten_tomatoes,plot,poster_url')
    .contains('genres', [genreCapitalized])
    .contains('streaming_services', [filters.platform])
    //.gte('year', filters.year - 1)
    //.lte('year', filters.year + 1)
    .eq('year', filters.year)
    .order('imdb_rating', { ascending: false })
    .limit(3);

  if (error) {
    console.error('Supabase error:', error.message);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  console.log('Supabase returned:', data?.length ?? 0, 'results');
  console.log('Sample result:', data?.[0]);

  return NextResponse.json({ results: data });
}

export function processPrompt(prompt: string) {
  // Later we'll extract genres, platform, year, etc.
  return {
    genre: 'Horror',
    platform: 'Netflix',
    year: 2021,
  };
}

const supabase = createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_KEY!);