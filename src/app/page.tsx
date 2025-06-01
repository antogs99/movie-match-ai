'use client'

import { useState } from 'react'

export default function Home() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  const handleSearch = async () => {
    if (!query) return
    setLoading(true)
    const res = await fetch('/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    })
    const data = await res.json()
    setResults(data.results)
    setLoading(false)
  }

  return (
    <main className="min-h-screen p-6 max-w-xl mx-auto flex flex-col gap-6">
      <h1 className="text-3xl font-bold text-center">MovieMatch AI</h1>
      <input
        className="border p-2 rounded text-lg"
        placeholder="e.g. dark thriller with Jake Gyllenhaal"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <button
        className="bg-blue-600 text-white p-2 rounded hover:bg-blue-700"
        onClick={handleSearch}
      >
        {loading ? 'Searching...' : 'Find Something'}
      </button>

      {results.length > 0 && (
        <div className="space-y-4">
          {results.map((item, i) => (
            <div key={i} className="border p-3 rounded">
              <h2 className="text-xl font-semibold">{item.title}</h2>
              <p>{item.overview}</p>
              {item.streaming && (
                <p className="mt-2 text-sm text-gray-600">
                  Available on: {item.streaming.join(', ')}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </main>
  )
}