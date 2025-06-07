// src/app/api/recommend/route.ts
import { NextResponse } from 'next/server';

export async function POST(req: Request) {
  const { prompt } = await req.json();

  // TEMP: Return mock data (replace with real logic later)
  return NextResponse.json({
    results: [
      {
        title: 'The Matrix',
        year: 1999,
        sources: ['Netflix'],
        imdb_rating: 8.7,
        rotten_tomatoes: 83,
        summary: 'A hacker discovers the truth about reality.',
      },
      {
        title: 'Arrival',
        year: 2016,
        sources: ['Paramount+'],
        imdb_rating: 7.9,
        rotten_tomatoes: 94,
        summary: 'A linguist deciphers alien language to save humanity.',
      },
    ],
  });
}