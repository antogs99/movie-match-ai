// src/app/page.tsx
'use client';

import { useState, useEffect } from 'react';




export default function Home() {
  const [prompt, setPrompt] = useState('');
  const [recommendations, setRecommendations] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [landingRecommendations, setLandingRecommendations] = useState<any[]>([]);

  useEffect(() => {
    const fetchLanding = async () => {
      try {
        const res = await fetch('/api/landing');
        const data = await res.json();
        setLandingRecommendations(data.results || []);
      } catch (error) {
        console.error('Error fetching landing recommendations:', error);
      }
    };

    fetchLanding();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    const res = await fetch('/api/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt }),
    });

    const data = await res.json();
    setRecommendations(data.results || []);
    setLoading(false);
  };

  return (
    <main className="min-h-screen bg-[#0F1C2E] text-[#F4F1E8] px-4 py-6 sm:py-5">
      <div className="max-w-6xl mx-auto space-y-10 px-4">
        {/* Header */}
        <header className="flex items-center justify-between w-full">
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">
            Pick<span className="text-[#00C876]">Your</span>Binge
          </h1>
          <img
            src="/logo.png"
            alt="PickYourBinge Logo"
            className="w-20 sm:w-28 md:w-36 h-auto object-contain"
          />
        </header>

        {/* Hero Prompt */}
        <section className="space-y-4 text-center">
          <h2 className="text-2xl sm:text-4xl md:text-5xl font-bold leading-snug">
            What do you feel like watching?
          </h2>
          <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row justify-center items-center gap-4">
            <input
              type="text"
              placeholder="e.g. sci-fi thriller, only Netflix"
              className="w-full sm:w-[400px] h-[52px] px-4 text-[#0F1C2E] bg-[#F4F1E8] placeholder:text-[#0F1C2E] rounded focus:outline-none focus:ring-2 focus:ring-[#00C876]"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
            />
            <button
              type="submit"
              className="h-[52px] px-6 bg-[#00C876] text-[#0F1C2E] rounded font-semibold hover:bg-[#00b06a] transition"
            >
              Search
            </button>
          </form>
        </section>

        {/* Default state before search */}
        {!loading && recommendations.length === 0 && (
          <section>
            <h3 className="text-xl sm:text-2xl font-semibold mb-4 text-center">Recommended for you</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {landingRecommendations.map((movie, idx) => (
                <div key={idx} className="bg-[#152033] rounded-lg p-4 shadow">
                  <img
                    src={movie.poster_url}
                    alt={movie.title}
                    className="w-full aspect-[2/3] object-cover rounded mb-3 bg-[#0F1C2E]"
                  />
                  <h3 className="text-lg font-bold mb-1">{movie.title} ({movie.year})</h3>
                  <p className="text-sm text-[#66D1CC] mb-1">Stream on: {movie.streaming_services?.join(', ')}</p>
                  <p className="text-sm mb-1">
                    <img src="/imdb.png" alt="IMDb" className="inline h-4 mr-1" /> {movie.imdb_rating}
                    <img src="/rt.png" alt="Rotten Tomatoes" className="inline h-4 mx-1" /> {movie.rotten_tomatoes}%
                  </p>
                  <p className="text-sm text-[#ccc]">{movie.plot}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Loading State */}
        {loading && (
          <div className="text-center">
            <p>Fetching movies...</p>
          </div>
        )}

        {/* Recommendations Results */}
        {recommendations.length > 0 && (
          <section className="space-y-4">
            <h3 className="text-2xl font-semibold">We recommend these movies:</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {recommendations.map((movie, idx) => (
                <div key={idx} className="bg-[#152033] rounded-lg p-4 shadow">
                  <img
                    src={movie.poster_url}
                    alt={movie.title}
                    className="w-full aspect-[2/3] object-cover rounded mb-3 bg-[#0F1C2E]"
                  />
                  <h3 className="text-lg font-bold mb-1">{movie.title} ({movie.year})</h3>
                  <p className="text-sm text-[#66D1CC] mb-1">
                    Stream on: {(movie.streaming_services || movie.sources || []).join(', ')}
                  </p>
                  <p className="text-sm mb-1">
                    <img src="/imdb.png" alt="IMDb" className="inline h-4 mr-1" /> {movie.imdb_rating}
                    <img src="/rt.png" alt="Rotten Tomatoes" className="inline h-4 mx-1" /> {movie.rotten_tomatoes}%
                  </p>
                  <p className="text-sm text-[#ccc]">{movie.plot || movie.summary}</p>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
      {/* Attribution */}
      <footer className="mt-10 text-center text-xs text-[#888]">
        <p>
          This website uses TMDB and the TMDB APIs but is not endorsed, certified, or otherwise approved by TMDB.
        </p>
        <p className="mt-2">
          Contact us: <a href="mailto:contact@pickyourbinge.com" className="underline text-[#F4F1E8] hover:text-[#00C876]">contact@pickyourbinge.com</a>
        </p>
        <img src="/tmdb.png.svg" alt="TMDB Logo" className="mx-auto mt-2 h-6" />
      </footer>
      <p className="text-sm text-gray-500 text-center mt-10">
        <a href="/privacy" className="underline hover:text-white">Privacy Policy</a>
      </p>
    </main>
  );
}