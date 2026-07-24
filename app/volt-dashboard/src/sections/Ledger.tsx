import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import ChartTip from '@/components/ChartTip'
import FilterChip from '@/components/FilterChip'
import Panel from '@/components/Panel'
import SectionHeader from '@/components/SectionHeader'
import VerdictBadge from '@/components/VerdictBadge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Slider } from '@/components/ui/slider'
import { useCatalog } from '@/lib/catalog-context'
import type { Bucket, KeyName } from '@/lib/catalog'
import { METRIC_RANGES, bucketOf } from '@/lib/catalog'
import type { LedgerFilters, SortDir, SortKey, ToneFilter } from '@/lib/filters'
import { DEFAULT_FILTERS, applyFilters, filtersActive, sortTracks } from '@/lib/filters'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 25

interface Col {
  key: SortKey | null
  label: string
  width: string
  align: 'left' | 'right' | 'center'
  tip?: string
}

const COLS: Col[] = [
  { key: null, label: '#', width: 'w-[44px]', align: 'right' },
  { key: 'track', label: 'TRACK', width: 'min-w-[220px]', align: 'left' },
  { key: 'bpm', label: 'BPM', width: 'w-[72px]', align: 'right' },
  { key: 'key', label: 'KEY', width: 'w-[56px]', align: 'center' },
  { key: 'brightness', label: 'TONE', width: 'w-[96px]', align: 'center' },
  { key: 'energy_density', label: 'ENERGY', width: 'w-[76px]', align: 'right', tip: 'Energy density — loudness-per-time 1.0–7.5' },
  { key: 'alpha', label: 'ALPHA', width: 'w-[64px]', align: 'right', tip: 'Hit-potential alpha score 7.2–8.5' },
  { key: 'structural_velocity', label: 'STRUCT', width: 'w-[72px]', align: 'right', tip: 'Structural velocity — arrangement momentum 1–10' },
  { key: 'market_modularity', label: 'MOD', width: 'w-[64px]', align: 'right', tip: 'Market modularity — playlist/sync fit 6.5–8.5' },
  { key: 'hpi', label: 'HPI', width: 'w-[72px]', align: 'right' },
  { key: 'verdict', label: 'VERDICT', width: 'w-[132px]', align: 'left' },
]

const GHOST_BTN =
  'inline-flex h-7 items-center rounded-[3px] border border-line-strong px-2 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-2 transition-colors duration-150 hover:border-amber hover:text-amber disabled:pointer-events-none disabled:opacity-40'

interface Props {
  filters: LedgerFilters
  onFiltersChange: (f: LedgerFilters) => void
}

export default function Ledger({ filters, onFiltersChange }: Props) {
  const { tracks, isLoading } = useCatalog()
  const [sortKey, setSortKey] = useState<SortKey>('hpi')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [page, setPage] = useState(1)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [searchText, setSearchText] = useState(filters.search)
  const firstRender = useRef(true)
  const toolbarRef = useRef<HTMLDivElement>(null)
  const [toolbarH, setToolbarH] = useState(52)

  /* ---- derived catalog stats from live tracks ---- */
  const TOTAL_TRACKS = tracks.length
  const BRIGHT_COUNT = useMemo(() => tracks.filter((t) => t.brightness === 'Bright/Aggressive').length, [tracks])
  const WARM_COUNT = TOTAL_TRACKS - BRIGHT_COUNT

  const BUCKETS: Bucket[] = ['ACQUIRE', 'PITCH', 'PITCH+LICENSE', 'LICENSE', 'ANALYZE']
  const BUCKET_COUNTS = useMemo(() => {
    const init: Record<Bucket, number> = { ACQUIRE: 0, PITCH: 0, 'PITCH+LICENSE': 0, LICENSE: 0, ANALYZE: 0 }
    return tracks.reduce((acc, t) => {
      acc[bucketOf(t.verdict)] += 1
      return acc
    }, init)
  }, [tracks])

  const KEYS: KeyName[] = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
  const KEY_COUNTS = useMemo(() => KEYS.map((k) => ({ key: k, count: tracks.filter((t) => t.key === k).length })), [tracks])

  /* ---- derived list ---- */
  const filtered = useMemo(() => applyFilters(tracks, filters), [tracks, filters])
  const sorted = useMemo(() => sortTracks(filtered, sortKey, sortDir), [filtered, sortKey, sortDir])
  const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE))
  const pageRows = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  /* ---- search debounce (150ms) ---- */
  useEffect(() => {
    setSearchText(filters.search)
  }, [filters.search])
  useEffect(() => {
    const t = setTimeout(() => {
      if (searchText !== filters.search) onFiltersChange({ ...filters, search: searchText })
    }, 150)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchText])

  /* ---- page resets on filter/sort change (not on highlight) ---- */
  useEffect(() => {
    setPage(1)
  }, [filters.search, filters.tone, filters.strategy, filters.key, filters.hpiRange, filters.source, sortKey, sortDir])

  /* ---- deep-link highlight: jump to the row's page ---- */
  useEffect(() => {
    if (!filters.highlight) return
    const idx = sorted.findIndex((t) => t.track === filters.highlight)
    if (idx >= 0) setPage(Math.floor(idx / PAGE_SIZE) + 1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.highlight, sorted])

  /* ---- toolbar height for sticky thead offset ---- */
  useEffect(() => {
    const el = toolbarRef.current
    if (!el) return
    const obs = new ResizeObserver((entries) => {
      setToolbarH(entries[0].contentRect.height)
    })
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  useEffect(() => {
    firstRender.current = false
  }, [])

  const update = (patch: Partial<LedgerFilters>) => onFiltersChange({ ...filters, ...patch })

  const clearCrossFilter = () =>
    onFiltersChange({ ...filters, tone: 'ALL', strategy: 'ALL', key: 'ALL', hpiRange: [5, 9], source: null })

  const reset = () => onFiltersChange({ ...DEFAULT_FILTERS })

  const headerClick = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir(key === 'track' || key === 'key' || key === 'verdict' || key === 'brightness' ? 'asc' : 'desc')
    }
  }

  const rangeLabel =
    filters.hpiRange[0] <= 5 && filters.hpiRange[1] >= 9
      ? '5.0–9.0'
      : filters.hpiRange[1] >= 9
        ? `≥ ${filters.hpiRange[0].toFixed(1)}`
        : filters.hpiRange[0] <= 5
          ? `≤ ${filters.hpiRange[1].toFixed(1)}`
          : `${filters.hpiRange[0].toFixed(1)}–${filters.hpiRange[1].toFixed(1)}`

  const active = filtersActive(filters)

  return (
    <section id="ledger" aria-label="Catalog ledger" className="scroll-mt-20">
      <SectionHeader
        overline="04 / CATALOG LEDGER"
        title={`ALL ${TOTAL_TRACKS} RECORDS`}
        descriptor="Every analyzed metric, sortable and filterable. Click a row for the full A&R verdict."
      />
      <Panel className="!px-0 !pb-0" contentClassName="!px-0 !pb-0">
        {/* ---------------- toolbar ---------------- */}
        <div
          ref={toolbarRef}
          className="sticky top-14 z-30 flex flex-wrap items-center gap-2 border-b border-line bg-bg-1 px-4 py-3 md:px-6"
        >
          {/* search */}
          <div className="relative min-w-[220px] flex-1">
            <span aria-hidden className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 font-mono text-[12px] text-ink-3">
              ⌕
            </span>
            <input
              type="text"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              placeholder="SEARCH TITLE OR VERDICT…"
              aria-label="Search title or verdict"
              className="h-8 w-full rounded-[3px] border border-line-strong bg-bg-0 pl-7 pr-7 font-mono text-[12px] text-ink-1 placeholder:text-ink-4 focus:border-amber"
            />
            {searchText && (
              <button
                type="button"
                aria-label="Clear search"
                onClick={() => setSearchText('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 font-mono text-[12px] text-ink-3 hover:text-amber"
              >
                ×
              </button>
            )}
          </div>
          {/* tone chips */}
          <div className="flex items-center gap-1.5" role="group" aria-label="Tone filter">
            <FilterChip active={filters.tone === 'ALL'} onClick={() => update({ tone: 'ALL' })}>
              ALL
            </FilterChip>
            <FilterChip
              active={filters.tone === 'Bright/Aggressive'}
              onClick={() => update({ tone: 'Bright/Aggressive' as ToneFilter })}
              count={BRIGHT_COUNT}
            >
              BRIGHT/AGGR
            </FilterChip>
            <FilterChip
              active={filters.tone === 'Warm/Dark'}
              onClick={() => update({ tone: 'Warm/Dark' as ToneFilter })}
              count={WARM_COUNT}
            >
              WARM/DARK
            </FilterChip>
          </div>
          {/* strategy select */}
          <Select value={filters.strategy} onValueChange={(v) => update({ strategy: v as LedgerFilters['strategy'] })}>
            <SelectTrigger
              aria-label="Strategy filter"
              className="h-8 w-[158px] rounded-[3px] border-line-strong bg-bg-0 px-2 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-2 hover:border-[#E8A33D66] focus-visible:ring-amber/40"
            >
              <SelectValue placeholder="ALL STRATEGIES" />
            </SelectTrigger>
            <SelectContent className="rounded-[3px] border-line-strong bg-bg-2">
              <SelectItem value="ALL" className="font-mono text-[11px] uppercase text-ink-2 focus:bg-bg-3 focus:text-ink-1">
                ALL STRATEGIES
              </SelectItem>
              {BUCKETS.map((b: Bucket) => (
                <SelectItem key={b} value={b} className="font-mono text-[11px] uppercase text-ink-2 focus:bg-bg-3 focus:text-ink-1">
                  {b} · {BUCKET_COUNTS[b]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {/* key select */}
          <Select value={filters.key} onValueChange={(v) => update({ key: v as LedgerFilters['key'] })}>
            <SelectTrigger
              aria-label="Key filter"
              className="h-8 w-[112px] rounded-[3px] border-line-strong bg-bg-0 px-2 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-2 hover:border-[#E8A33D66] focus-visible:ring-amber/40"
            >
              <SelectValue placeholder="ALL KEYS" />
            </SelectTrigger>
            <SelectContent className="rounded-[3px] border-line-strong bg-bg-2">
              <SelectItem value="ALL" className="font-mono text-[11px] uppercase text-ink-2 focus:bg-bg-3 focus:text-ink-1">
                ALL KEYS
              </SelectItem>
              {KEYS.map((k: KeyName) => (
                <SelectItem key={k} value={k} className="font-mono text-[11px] uppercase text-ink-2 focus:bg-bg-3 focus:text-ink-1">
                  {k} · {KEY_COUNTS.find((c) => c.key === k)?.count ?? 0}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {/* HPI range slider */}
          <div className="flex min-w-[190px] items-center gap-2">
            <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-ink-4">HPI</span>
            <Slider
              value={filters.hpiRange}
              min={5}
              max={9}
              step={0.1}
              minStepsBetweenThumbs={1}
              onValueChange={(v) => update({ hpiRange: [v[0], v[1]] })}
              aria-label="HPI range"
              className="w-28"
            />
            <span className="w-[52px] text-right font-mono text-[10px] text-ink-2" style={{ fontVariantNumeric: 'tabular-nums' }}>
              {rangeLabel}
            </span>
          </div>
          {/* cross-filter source chip */}
          <AnimatePresence>
            {filters.source && (
              <motion.span
                key="source-chip"
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                transition={{ duration: 0.15 }}
              >
                <FilterChip active clearable onClick={clearCrossFilter} ariaLabel={`Clear cross filter ${filters.source}`}>
                  {filters.source}
                </FilterChip>
              </motion.span>
            )}
          </AnimatePresence>
          {/* reset */}
          <AnimatePresence>
            {active && (
              <motion.button
                key="reset"
                type="button"
                onClick={reset}
                className={GHOST_BTN}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                transition={{ duration: 0.15 }}
              >
                RESET
              </motion.button>
            )}
          </AnimatePresence>
          {/* result count */}
          <span
            className="ml-auto font-mono text-[10px] uppercase tracking-[0.12em] text-ink-3"
            aria-live="polite"
            aria-label={`Showing ${sorted.length} of ${TOTAL_TRACKS} tracks`}
          >
            SHOWING {sorted.length} / {TOTAL_TRACKS}
          </span>
        </div>

        {/* ---------------- table ---------------- */}
        <div className="overflow-x-auto">
          {isLoading ? (
            <div className="flex flex-col items-center gap-3 px-6 py-16">
              <p className="font-mono text-[12px] uppercase tracking-[0.14em] text-ink-3">LOADING CATALOG…</p>
            </div>
          ) : pageRows.length === 0 ? (
            <div className="flex flex-col items-center gap-3 px-6 py-16">
              <p className="font-mono text-[12px] uppercase tracking-[0.14em] text-ink-3">NO SIGNAL — ADJUST FILTERS</p>
              <button type="button" className={GHOST_BTN} onClick={reset}>
                Reset filters
              </button>
            </div>
          ) : (
            <table className="w-full min-w-[1100px] border-collapse">
              <thead className="sticky z-20 bg-bg-1" style={{ top: 56 + toolbarH }}>
                <tr className="border-b border-line-strong">
                  {COLS.map((c) => (
                    <th
                      key={c.label}
                      scope="col"
                      aria-sort={c.key && sortKey === c.key ? (sortDir === 'asc' ? 'ascending' : 'descending') : undefined}
                      className={cn(
                        'h-9 px-2 font-mono text-[10.5px] font-medium uppercase tracking-[0.12em] text-ink-3',
                        c.width,
                        c.align === 'right' ? 'text-right' : c.align === 'center' ? 'text-center' : 'text-left',
                      )}
                    >
                      {c.key ? (
                        <ChartTip label={c.tip ?? c.label}>
                          <button
                            type="button"
                            onClick={() => headerClick(c.key as SortKey)}
                            className="group inline-flex items-center gap-1 uppercase tracking-[0.12em] transition-colors duration-150 hover:text-amber"
                          >
                            {c.label}
                            <span aria-hidden className="text-[8px] text-ink-4">
                              <span className={sortKey === c.key && sortDir === 'asc' ? 'text-amber' : ''}>▲</span>
                              <span className={sortKey === c.key && sortDir === 'desc' ? 'text-amber' : ''}>▼</span>
                            </span>
                          </button>
                        </ChartTip>
                      ) : (
                        c.label
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pageRows.map((t, idx) => {
                  const rank = (page - 1) * PAGE_SIZE + idx + 1
                  const bright = t.brightness === 'Bright/Aggressive'
                  const bucket = bucketOf(t.verdict)
                  const isExpanded = expanded === t.track
                  const isHighlight = filters.highlight === t.track
                  return (
                    <Fragment key={t.track}>
                      <motion.tr
                        layout="position"
                        initial={{ opacity: 0, y: firstRender.current ? 8 : 0 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{
                          opacity: { duration: 0.18, delay: firstRender.current ? idx * 0.02 : 0 },
                          layout: { type: 'spring', stiffness: 210, damping: 26 },
                        }}
                        onClick={() => setExpanded(isExpanded ? null : t.track)}
                        className={cn(
                          'h-10 cursor-pointer border-b border-line transition-colors duration-150 hover:bg-bg-3 hover:shadow-[inset_2px_0_0_#E8A33D]',
                          idx % 2 === 1 && 'bg-bg-0/50',
                          isExpanded && 'bg-bg-2',
                          isHighlight && 'animate-row-flash',
                        )}
                        data-track={t.track}
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            setExpanded(isExpanded ? null : t.track)
                          }
                        }}
                        aria-expanded={isExpanded}
                      >
                        <td className="px-2 text-right font-mono text-[11px] text-ink-4" style={{ fontVariantNumeric: 'tabular-nums' }}>
                          {rank}
                        </td>
                        <td className="max-w-[320px] truncate px-2 text-[13px] font-medium text-ink-1">{t.track}</td>
                        <td className="px-2 text-right font-mono text-[12.5px] text-ink-2" style={{ fontVariantNumeric: 'tabular-nums' }}>
                          {t.bpm != null ? t.bpm.toFixed(1) : '—'}
                        </td>
                        <td className="px-2 text-center font-mono text-[12px] text-ink-2">{t.key}</td>
                        <td className="px-2">
                          <span className="flex items-center justify-center gap-1.5">
                            <span aria-hidden className="h-2 w-2 rounded-full" style={{ backgroundColor: bright ? '#E8A33D' : '#B87333' }} />
                            <span className="font-mono text-[10px] uppercase" style={{ color: bright ? '#E8A33D' : '#B87333' }}>
                              {bright ? 'BRIGHT' : 'WARM'}
                            </span>
                          </span>
                        </td>
                        <td className="px-2 text-right">
                          <span className="inline-flex items-center justify-end gap-1.5">
                            <span className="font-mono text-[12.5px] text-ink-2" style={{ fontVariantNumeric: 'tabular-nums' }}>
                              {t.energy_density != null ? t.energy_density.toFixed(1) : '—'}
                            </span>
                            <span aria-hidden className="inline-block h-[4px] w-[24px] overflow-hidden rounded-[1px] bg-bg-3">
                              <span
                                className="block h-full bg-amber/70"
                                style={{
                                  width: `${(t.energy_density != null
                                    ? (((t.energy_density - METRIC_RANGES.energy_density.min) / (METRIC_RANGES.energy_density.max - METRIC_RANGES.energy_density.min)) * 100).toFixed(0)
                                    : '0') }%`,
                                }}
                              />
                            </span>
                          </span>
                        </td>
                        <td className="px-2 text-right font-mono text-[12.5px] text-ink-2" style={{ fontVariantNumeric: 'tabular-nums' }}>
                          {t.alpha != null ? t.alpha.toFixed(1) : '—'}
                        </td>
                        <td className="px-2 text-right font-mono text-[12.5px] text-ink-2" style={{ fontVariantNumeric: 'tabular-nums' }}>
                          {t.structural_velocity != null ? t.structural_velocity.toFixed(1) : '—'}
                        </td>
                        <td className="px-2 text-right font-mono text-[12.5px] text-ink-2" style={{ fontVariantNumeric: 'tabular-nums' }}>
                          {t.market_modularity != null ? t.market_modularity.toFixed(1) : '—'}
                        </td>
                        <td
                          className="px-2 text-right font-mono text-[13px] font-bold"
                          style={{
                            fontVariantNumeric: 'tabular-nums',
                            color: t.hpi >= 8.8 ? '#F5C15C' : '#E8A33D',
                            textShadow: t.hpi >= 8.8 ? '0 0 8px rgba(232,163,61,0.45)' : 'none',
                          }}
                        >
                          {t.hpi != null ? t.hpi.toFixed(2) : '—'}
                        </td>
                        <td className="px-2">
                          <VerdictBadge bucket={bucket} />
                        </td>
                      </motion.tr>
                      <AnimatePresence>
                        {isExpanded && (
                          <motion.tr key={`${t.track}-drawer`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
                            <td colSpan={COLS.length} className="p-0">
                              <motion.div
                                initial={{ height: 0 }}
                                animate={{ height: 'auto' }}
                                exit={{ height: 0 }}
                                transition={{ duration: 0.25 }}
                                className="overflow-hidden"
                              >
                                <div className="border-b border-line bg-bg-0 px-4 py-3 md:px-6">
                                  <ScrollArea className="max-h-[140px]">
                                    <p className="label-micro mb-1.5">A&amp;R VERDICT</p>
                                    <p className="max-w-[72ch] text-[13px] leading-relaxed text-ink-2">{t.verdict}</p>
                                    <div className="mt-2.5 flex flex-wrap gap-1.5">
                                      {[
                                        `BPM ${t.bpm != null ? t.bpm.toFixed(1) : '—'}`,
                                        `KEY ${t.key}`,
                                        t.brightness.toUpperCase(),
                                        `ENERGY ${t.energy_density != null ? t.energy_density.toFixed(1) : '—'}`,
                                        `ALPHA ${t.alpha != null ? t.alpha.toFixed(1) : '—'}`,
                                        `STRUCT ${t.structural_velocity != null ? t.structural_velocity.toFixed(1) : '—'}`,
                                        `MOD ${t.market_modularity != null ? t.market_modularity.toFixed(1) : '—'}`,
                                        `HPI ${t.hpi != null ? t.hpi.toFixed(2) : '—'}`,
                                      ].map((chip) => (
                                        <span key={chip} className="rounded-[2px] border border-line px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] text-ink-3">
                                          {chip}
                                        </span>
                                      ))}
                                    </div>
                                  </ScrollArea>
                                </div>
                              </motion.div>
                            </td>
                          </motion.tr>
                        )}
                      </AnimatePresence>
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* ---------------- pagination footer ---------------- */}
        {pageRows.length > 0 && (
          <div className="flex flex-wrap items-center gap-3 border-t border-line px-4 py-3 md:px-6">
            <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-3" style={{ fontVariantNumeric: 'tabular-nums' }}>
              PAGE {page} / {pageCount} · ROWS {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, sorted.length)}
            </span>
            <div className="ml-auto flex items-center gap-1.5">
              <button type="button" className={GHOST_BTN} disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))} aria-label="Previous page">
                ← PREV
              </button>
              {Array.from({ length: pageCount }, (_, i) => i + 1).map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPage(p)}
                  aria-current={p === page ? 'page' : undefined}
                  className={cn(
                    'h-7 w-7 font-mono text-[10px] transition-colors duration-150',
                    p === page ? 'text-amber underline underline-offset-4' : 'text-ink-3 hover:text-amber',
                  )}
                >
                  {p}
                </button>
              ))}
              <button type="button" className={GHOST_BTN} disabled={page >= pageCount} onClick={() => setPage((p) => Math.min(pageCount, p + 1))} aria-label="Next page">
                NEXT →
              </button>
            </div>
          </div>
        )}
      </Panel>
    </section>
  )
}
