// src/app/api/landing/route.ts
import { NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_KEY!);

export async function GET() {
  const { data, error } = await supabase
    .from('movies')
    .select('*')
    .gt('imdb_rating', 6.5)
    .gt('rotten_tomatoes', 70)
    .filter('streaming_services', 'neq', '{}')
    .order('year', { ascending: false })
    .limit(20);

  if (error) {
  console.error("Supabase error:", error);
  return NextResponse.json({ error: error.message }, { status: 500 });
}
  // Pick 3 random movies from result
  console.log("Landing page movies:", data);
  const randomThree = data.sort(() => 0.5 - Math.random()).slice(0, 3);
  return NextResponse.json({ results: randomThree });
}