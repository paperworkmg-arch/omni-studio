const API_BASE = '/api'

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`)
  return res.json()
}

function postForm<T>(path: string, data: Record<string, string>): Promise<T> {
  const body = new URLSearchParams(data)
  return fetchJson<T>(path, { method: 'POST', body, headers: {} })
}

// === Agents ===
export interface Agent {
  id: number; name: string; role: string; model: string; status: string
  tasks_completed: number; last_active: string | null; config: string | null
}
export const getAgents = () => fetchJson<Agent[]>('/contacts/stats').then(() => fetchJson<Agent[]>('/agents'))
export const toggleAgent = (id: number) => postForm<{status:string}>(`/agents/${id}/toggle`, {})

// === Tasks ===
export interface Task {
  id: number; name: string; type: string; status: string; progress: number
  result: string | null; agent: string; created_at: string; updated_at: string
  scheduled_cron: string | null; enabled: number
}
export const getTasks = () => fetchJson<Task[]>('/tasks')
export const toggleTask = (id: number) => postForm<{status:string}>(`/tasks/${id}/toggle`, {})
export const runTask = (id: number) => postForm<{status:string}>(`/tasks/${id}/run`, {})
export const createTask = (data: {name:string;type:string;agent:string;cron:string}) =>
  postForm<{id:number}>('/tasks', data)

// === Swarm ===
export interface SwarmRun {
  id: number; objective: string; status: string; agents_used: string
  started_at: string; completed_at: string | null; result: string | null
}
export const getSwarmRuns = () => fetchJson<SwarmRun[]>('/swarm/runs')
export const runSwarm = (objective: string) => postForm<SwarmRun>('/swarm/run', { objective })

// === Activity ===
export interface Activity {
  id: number; source: string; message: string; level: string; created_at: string
}
export const getActivity = () => fetchJson<Activity[]>('/activity')

// === Contacts ===
export interface Contact {
  id: number; name: string; email: string; phone: string; company: string
  role: string; source: string; status: string; tags: string; notes: string
  last_contact: string | null; created_at: string; updated_at: string
}
export interface ContactStats { total: number; by_status: Record<string,number>; by_source: Record<string,number> }
export const getContacts = (status?: string, search?: string) =>
  fetchJson<{contacts:Contact[];total:number}>(`/contacts${status?`?status=${status}`:''}${search?`?search=${search}`:''}`)
export const getContactStats = () => fetchJson<ContactStats>('/contacts/stats')
export const createContact = (data: Record<string,string>) => postForm<{id:number}>('/contacts', data)

// === Samples ===
export interface Sample {
  id: number; path: string; filename: string; directory: string; extension: string
  size_bytes: number; sample_type: string; key: string; tempo: number; duration: number
  analyzed: number; tags: string; notes: string
}
export interface SampleStats { total: number; by_key: Record<string,number>; by_type: Record<string,number>; by_directory: Record<string,number> }
export const getSamples = (params?: Record<string,string>) => {
  const q = params ? '?' + new URLSearchParams(params).toString() : ''
  return fetchJson<Sample[]>(`/samples${q}`)
}
export const getSampleStats = () => fetchJson<SampleStats>('/samples/stats')
export const startScan = () => postForm<{scan_id:number}>('/samples/scan', {})
export const analyzeSamples = () => postForm<{status:string}>('/samples/analyze', {})

// === Vault ===
export interface VaultEntry {
  id: number; category: string; title: string; content: string
  tags: string; created_at: string
}
export interface VaultStats { total_entries: number; total_extractions: number; by_category: Record<string,number> }
export const getVaultEntries = (category?: string) =>
  fetchJson<VaultEntry[]>(`/vault/all${category?`?category=${category}`:''}`)
export const searchVault = (q: string, category?: string) =>
  fetchJson<VaultEntry[]>(`/vault/search?q=${encodeURIComponent(q)}${category?`&category=${category}`:''}`)
export const getVaultStats = () => fetchJson<VaultStats>('/vault/stats')
export const getVaultRecent = () => fetchJson<VaultEntry[]>('/vault/recent')
export const getExtractionHistory = () => fetchJson<any[]>('/kimi-daily/history')

// === System ===
export interface SystemHealth {
  status: string; timestamp: string
  disk: { usage_gb: number; limit_gb: number; percent: number }
  agents: { total: number; idle: number; working: number; paused: number }
  tasks: { total: number; pending: number; completed: number }
  databases: Record<string, {exists:boolean; size_mb:number}>
  recent_activity: Activity[]
}
export const getSystemHealth = () => fetchJson<SystemHealth>('/system/health')
export const getCleanerStatus = () => fetchJson<{usage_gb:number;limit_gb:number;percent:number}>('/cleaner/status')
export const runCleaner = () => fetchJson<any>('/cleaner/run', { method: 'POST' })

// === DAW ===
export interface DAWExport {
  file: string; path: string; size_mb: number; detected_at: string
  upload_status: string; drive_url?: string
}
export const getDAWExports = () => fetchJson<DAWExport[]>('/daw/exports')
export const getDAWStatus = () => fetchJson<{processed_files:string[];uploads:DAWExport[];last_scan:string|null}>('/daw/status')

// === Notifications ===
export const getNotifications = () => fetchJson<Activity[]>('/notifications')

// === Kimi Daily ===
export const runKimiDaily = (transcript?: string) =>
  postForm<any>('/kimi-daily/run', { transcript: transcript || '', auto_tools: 'true' })

// === Catalog (Volt Records) ===
export interface CatalogTrack {
  id: number
  track_name: string
  bpm: number | null
  key: string | null
  brightness: 'Bright/Aggressive' | 'Warm/Dark' | null
  energy_density: number | null
  alpha: number | null
  structural_velocity: number | null
  market_modularity: number | null
  hpi: number | null
  verdict: string | null
  verdict_bucket: 'ACQUIRE' | 'PITCH' | 'PITCH+LICENSE' | 'LICENSE' | 'ANALYZE'
  imported_at: string
}

export interface CatalogSummary {
  total_tracks: number | null
  avg_hpi: number | null
  avg_bpm: number | null
  min_bpm: number | null
  max_bpm: number | null
  red_zone_count: number | null
  acquire_count: number | null
  bright_count: number | null
  warm_count: number | null
}

export interface KeyDistribution { key: string; count: number }
export interface BucketDistribution { bucket: string; count: number }

export const getCatalogTracks = (params?: Record<string, string | number>) => {
  const q = params ? '?' + new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString() : ''
  return fetchJson<CatalogTrack[]>(`/catalog/tracks${q}`)
}
export const getCatalogTrack = (id: number) => fetchJson<CatalogTrack>(`/catalog/tracks/${id}`)
export const getCatalogSummary = () => fetchJson<CatalogSummary>('/catalog/summary')
export const getCatalogTopProspects = (n = 6) => fetchJson<CatalogTrack[]>(`/catalog/top-prospects?n=${n}`)
export const getCatalogKeys = () => fetchJson<KeyDistribution[]>('/catalog/keys')
export const getCatalogBuckets = () => fetchJson<BucketDistribution[]>('/catalog/buckets')
export const searchCatalog = (q: string, limit = 50) =>
  fetchJson<CatalogTrack[]>(`/catalog/search?q=${encodeURIComponent(q)}&limit=${limit}`)
