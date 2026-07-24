import { createContext, useContext, useMemo, type ReactNode } from 'react'
import { useCatalogTracks, useCatalogSummary, useCatalogTopProspects, useCatalogKeys, useCatalogBuckets } from '@/hooks/use-catalog'
import type { Track } from '@/lib/catalog'

interface CatalogContextValue {
  tracks: Track[]
  summary: {
    total_tracks: number
    avg_hpi: number
    avg_bpm: number
    min_bpm: number
    max_bpm: number
    red_zone_count: number
    acquire_count: number
    bright_count: number
    warm_count: number
  } | null
  topProspects: Track[]
  keys: { key: string; count: number }[]
  buckets: { bucket: string; count: number }[]
  isLoading: boolean
  isError: boolean
}

const CatalogContext = createContext<CatalogContextValue | null>(null)

export function useCatalog() {
  const ctx = useContext(CatalogContext)
  if (!ctx) throw new Error('useCatalog must be used within CatalogProvider')
  return ctx
}

interface Props {
  children: ReactNode
}

export function CatalogProvider({ children }: Props) {
  const { data: tracks = [], isLoading: tracksLoading, isError: tracksError } = useCatalogTracks()
  const { data: summary, isLoading: summaryLoading } = useCatalogSummary()
  const { data: topProspects = [], isLoading: prospectsLoading } = useCatalogTopProspects(6)
  const { data: keys = [], isLoading: keysLoading } = useCatalogKeys()
  const { data: buckets = [], isLoading: bucketsLoading } = useCatalogBuckets()

  // Ensure arrays are always arrays, never null/undefined
  const safeTopProspects = Array.isArray(topProspects) ? topProspects : []
  const safeKeys = Array.isArray(keys) ? keys : []
  const safeBuckets = Array.isArray(buckets) ? buckets : []

  const isLoading = tracksLoading || summaryLoading || prospectsLoading || keysLoading || bucketsLoading
  const isError = tracksError

  const value = useMemo(() => ({
    tracks,
    summary: summary
      ? {
          total_tracks: summary.total_tracks ?? 0,
          avg_hpi: summary.avg_hpi ?? 0,
          avg_bpm: summary.avg_bpm ?? 0,
          min_bpm: summary.min_bpm ?? 0,
          max_bpm: summary.max_bpm ?? 0,
          red_zone_count: summary.red_zone_count ?? 0,
          acquire_count: summary.acquire_count ?? 0,
          bright_count: summary.bright_count ?? 0,
          warm_count: summary.warm_count ?? 0,
        }
      : null,
    topProspects: safeTopProspects,
    keys: safeKeys,
    buckets: safeBuckets,
    isLoading,
    isError,
  }), [tracks, summary, safeTopProspects, safeKeys, safeBuckets, isLoading, isError])

  return (
    <CatalogContext.Provider value={value}>
      {children}
    </CatalogContext.Provider>
  )
}
