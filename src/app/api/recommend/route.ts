// src/app/api/recommend/route.ts
import { NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { recommendFromPrompt } from '@/lib/recommendFromPrompt';


export async function POST(req: Request) {
  const { prompt } = await req.json();
  const movies = await processPrompt(prompt);

  console.log('Received prompt:', prompt);
  console.log('Returning recommended movies:', movies?.length ?? 0);

  return NextResponse.json({ results: movies });
}

export async function processPrompt(prompt: string): Promise<any[]> {
  const movies = await recommendFromPrompt(prompt);
  return movies;
}

const supabase = createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_KEY!);