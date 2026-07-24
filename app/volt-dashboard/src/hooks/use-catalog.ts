import { useQuery } from '@tanstack/react-query'
import {
  getCatalogTracks,
  getCatalogSummary,
  getCatalogTopProspects,
  getCatalogKeys,
  getCatalogBuckets,
  type CatalogTrack,
  type CatalogSummary,
  type KeyDistribution,
  type BucketDistribution,
} from '@/lib/api'
import type { Track } from '@/lib/catalog'

// Transform DB track_name -> track for compatibility
function transformTrack(ct: CatalogTrack): Track {
  return {
    track: ct.track_name,
    bpm: ct.bpm ?? 0,
    key: ct.key ?? 'N/A',
    brightness: ct.brightness ?? 'Warm/Dark',
    energy_density: ct.energy_density ?? 0,
    alpha: ct.alpha ?? 0,
    structural_velocity: ct.structural_velocity ?? 0,
    market_modularity: ct.market_modularity ?? 0,
    hpi: ct.hpi ?? 0,
    verdict: ct.verdict ?? 'ANALYZE',
  }
}

export function useCatalogTracks(
  bucket?: string,
  key?: string,
  brightness?: string,
  hpiMin?: number,
  hpiMax?: number,
  bpmMin?: number,
  bpmMax?: number,
  search?: string,
  limit = 200,
) {
  const params: Record<string, string> = { limit: String(limit) }
  if (bucket && bucket !== 'ALL') params.bucket = bucket
  if (key && key !== 'ALL') params.key = key
  if (brightness && brightness !== 'ALL') params.brightness = brightness
  if (hpiMin !== undefined) params.hpi_min = String(hpiMin)
  if (hpiMax !== undefined) params.hpi_max = String(hpiMax)
  if (bpmMin !== undefined) params.bpm_min = String(bpmMin)
  if (bpmMax !== undefined) params.bpm_max = String(bpmMax)
  if (search) params.search = search

  return useQuery<Track[]>({
    queryKey: ['catalog-tracks', params],
    queryFn: () => getCatalogTracks(params).then((tracks) => tracks.map(transformTrack)),
  })
}

export function useCatalogSummary() {
  return useQuery<CatalogSummary>({
    queryKey: ['catalog-summary'],
    queryFn: getCatalogSummary,
  })
}

export function useCatalogTopProspects(n = 6) {
  return useQuery<Track[]>({
    queryKey: ['catalog-top-prospects', n],
    queryFn: () => getCatalogTopProspects(n).then((tracks) => tracks.map(transformTrack)),
  })
}

export function useCatalogKeys() {
  return useQuery<KeyDistribution[]>({
    queryKey: ['catalog-keys'],
    queryFn: getCatalogKeys,
  })
}

export function useCatalogBuckets() {
  return useQuery<BucketDistribution[]>({
    queryKey: ['catalog-buckets'],
    queryFn: getCatalogBuckets,
  })
}
