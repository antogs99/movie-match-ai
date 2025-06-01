import axios from 'axios'
import { MovieResult } from '@/types/movie'

type TMDbDiscoverResponse = {
  results: {
    title: string
    overview: string
    poster_path: string
    release_date: string
    id: number
  }[]
}
type TMDbPersonSearchResponse = {
  results: {
    id: number
    name: string
  }[]
}
export async function searchMovies(filters: {
  genre?: string[]
  actor?: string
  decade?: string
}): Promise<MovieResult[]> {
  const { actor, genre, decade } = filters

  // Get actor ID from TMDb
  let actorId: number | undefined
  if (actor) {
const actorSearch = await axios.get<TMDbPersonSearchResponse>('https://api.themoviedb.org/3/search/person', {      params: {
        api_key: process.env.TMDB_API_KEY,
        query: actor,
      },
    })
    actorId = actorSearch.data?.results?.[0]?.id
  }

  // Discover movies with TMDb
const discoverRes = await axios.get<TMDbDiscoverResponse>('https://api.themoviedb.org/3/discover/movie', {
    params: {
      api_key: process.env.TMDB_API_KEY,
      with_cast: actorId,
      sort_by: 'popularity.desc',
      include_adult: false,
      language: 'en-US',
      primary_release_date_gte: decade ? `${decade.slice(0, 3)}0-01-01` : undefined,
      primary_release_date_lte: decade ? `${decade.slice(0, 3)}9-12-31` : undefined,
    },
  })

  const movies = discoverRes.data.results.slice(0, 3)

  // Enrich each movie with Watchmode streaming info
  const results: MovieResult[] = await Promise.all(
    movies.map(async (movie: any) => {
      const title = movie.title
      const year = parseInt(movie.release_date?.slice(0, 4)) || 0

      // Search Watchmode for the movie
      const watchSearch = await axios.get<any>('https://api.watchmode.com/v1/search/', {
        params: {
          apiKey: process.env.WATCHMODE_API_KEY,
          search_value: title,
          search_field: 'name',
        },
      })

      const match = watchSearch.data.title_results?.find(
        (r: any) => r.year === year && r.type === 'movie'
      )
      const watchmodeId = match?.id

      let streamers: string[] = []

      if (watchmodeId) {
        const sourceRes = await axios.get<any>(
          `https://api.watchmode.com/v1/title/${watchmodeId}/sources/`,
          {
            params: { apiKey: process.env.WATCHMODE_API_KEY },
          }
        )

        streamers = sourceRes.data
          .filter((s: any) => s.type === 'sub' && s.region === 'US')
          .map((s: any) => s.name)
      }

      return {
        title,
        description: movie.overview,
        image: movie.poster_path
          ? `https://image.tmdb.org/t/p/w500${movie.poster_path}`
          : '',
        year,
        streaming: [...new Set(streamers)],
      }
    })
  )

  return results
}