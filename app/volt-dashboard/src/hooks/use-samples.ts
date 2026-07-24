import { useQuery } from '@tanstack/react-query'
import { getSamples, getSampleStats, type Sample, type SampleStats } from '@/lib/api'

export function useSamples(params?: Record<string, string>) {
  return useQuery<Sample[]>({
    queryKey: ['samples', params],
    queryFn: async () => {
      try {
        const data = await getSamples(params)
        // Ensure data is always an array
        return Array.isArray(data) ? data : []
      } catch {
        return []
      }
    },
  })
}
export function useSampleStats() {
  return useQuery<SampleStats>({
    queryKey: ['sample-stats'],
    queryFn: async () => {
      try {
        return await getSampleStats()
      } catch {
        return { total: 0, by_key: {}, by_type: {}, by_directory: {} }
      }
    },
  })
}
