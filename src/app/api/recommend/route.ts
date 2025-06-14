// src/app/api/recommend/route.ts
import { NextResponse } from 'next/server';
import { recommendFromPrompt } from '@/lib/recommendFromPrompt';


export async function POST(req: Request) {
  const { prompt } = await req.json();
  const movies = await recommendFromPrompt(prompt);

  console.log('Received prompt:', prompt);
  console.log('Returning recommended movies:', movies?.length ?? 0);

  return NextResponse.json({ results: movies });
}