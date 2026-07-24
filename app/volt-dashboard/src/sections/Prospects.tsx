import { motion } from 'framer-motion'
import SectionHeader from '@/components/SectionHeader'
import VerdictBadge from '@/components/VerdictBadge'
import { useCatalog } from '@/lib/catalog-context'
import type { Track } from '@/lib/catalog'
import { METRIC_RANGES, bucketOf } from '@/lib/catalog'
import type { CrossFilter } from '@/lib/crossfilter'
import { EASE_OUT_EXPO } from '@/lib/motion'

/* ---------------- HPI dial: 64px gauge, arc −120°…+120° ---------------- */
function polar(cx: number, cy: number, r: number, deg: number): [number, number] {
  const a = (deg * Math.PI) / 180
  return [cx + r * Math.sin(a), cy - r * Math.cos(a)]
}

function gaugeArc(cx: number, cy: number, r: number, a0: number, a1: number): string {
  const [x0, y0] = polar(cx, cy, r, a0)
  const [x1, y1] = polar(cx, cy, r, a1)
  const large = a1 - a0 > 180 ? 1 : 0
  return `M ${(x0 != null ? x0 : 0).toFixed(2)} ${(y0 != null ? y0 : 0).toFixed(2)} A ${r} ${r} 0 ${large} 1 ${(x1 != null ? x1 : 0).toFixed(2)} ${(y1 != null ? y1 : 0).toFixed(2)}`
}

function HpiDial({ hpi, top, delay }: { hpi: number; top: boolean; delay: number }) {
  const CX = 32
  const CY = 34
  const R = 24
  const frac = Math.min(1, Math.max(0, (hpi - 5) / 4)) // 5–9 → 0–1
  const angle = -120 + frac * 240
  const color = top ? '#D95B33' : '#E8A33D'
  const [nx, ny] = polar(CX, CY, R - 4, angle)
  const [nx2, ny2] = polar(CX, CY, R + 3, angle)
  return (
    <svg width="64" height="64" viewBox="0 0 64 64" aria-hidden className="shrink-0 transition-[filter] duration-150 group-hover:drop-shadow-[0_0_8px_rgba(232,163,61,0.35)]">
      <path d={gaugeArc(CX, CY, R, -120, 120)} fill="none" stroke="#3D332A" strokeWidth="3" strokeLinecap="round" />
      <motion.path
        d={gaugeArc(CX, CY, R, -120, angle)}
        fill="none"
        stroke={color}
        strokeWidth="3"
        strokeLinecap="round"
        initial={{ pathLength: 0 }}
        whileInView={{ pathLength: 1 }}
        viewport={{ once: true, margin: '0px 0px -15% 0px' }}
        transition={{ type: 'spring', stiffness: 90, damping: 18, delay: delay + 0.15 }}
      />
      {/* needle tick at value */}
      <motion.line
        x1={nx}
        y1={ny}
        x2={nx2}
        y2={ny2}
        stroke={color}
        strokeWidth="2"
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true, margin: '0px 0px -15% 0px' }}
        transition={{ delay: delay + 0.7, duration: 0.2 }}
      />
      <text x={CX} y={CY + 12} textAnchor="middle" fill="#EFE6D6" fontSize="15" fontWeight="700" fontFamily="'JetBrains Mono', monospace">
        {Number.isFinite(hpi) ? hpi.toFixed(2) : '—'}
      </text>
    </svg>
  )
}

/* ---------------- metric mini bar ---------------- */
function MetricBar({ label, value, min, max, tone, delay }: { label: string; value: number; min: number; max: number; tone: 'amber' | 'copper'; delay: number }) {
  const pct = Math.min(1, Math.max(0, (value - min) / (max - min)))
  return (
    <div className="flex items-center gap-2">
      <span className="w-[44px] shrink-0 font-mono text-[9px] uppercase tracking-[0.12em] text-ink-3">{label}</span>
      <div className="h-[6px] flex-1 overflow-hidden rounded-[1px] bg-bg-3">
        <motion.div
          className="h-full rounded-[1px]"
          style={{ backgroundColor: tone === 'amber' ? '#E8A33D' : '#B87333', opacity: 0.8 }}
          initial={{ scaleX: 0 }}
          whileInView={{ scaleX: pct }}
          viewport={{ once: true, margin: '0px 0px -15% 0px' }}
          transition={{ duration: 0.5, delay, ease: EASE_OUT_EXPO }}
          // transform origin left
        />
      </div>
      <span className="w-8 shrink-0 text-right font-mono text-[10px] text-ink-2" style={{ fontVariantNumeric: 'tabular-nums' }}>
        {value != null && Number.isFinite(value) ? value.toFixed(1) : '—'}
      </span>
    </div>
  )
}

/* ---------------- prospect card ---------------- */
function ProspectCard({ track, rank, onCrossFilter }: { track: Track; rank: number; onCrossFilter: (cf: CrossFilter) => void }) {
  const top = rank === 1
  const bright = track.brightness === 'Bright/Aggressive'
  const delay = (rank - 1) * 0.08
  return (
    <motion.button
      type="button"
      onClick={() => onCrossFilter({ kind: 'track', name: track.track })}
      className="group console-panel panel-scanline relative p-5 text-left transition-[border-color,box-shadow] duration-150 hover:border-[#E8A33D66]"
      initial={{ opacity: 0, y: 32, rotateX: 5 }}
      whileInView={{ opacity: 1, y: 0, rotateX: 0 }}
      whileHover={{ y: -4 }}
      viewport={{ once: true, margin: '0px 0px -15% 0px' }}
      transition={{ duration: 0.65, ease: EASE_OUT_EXPO, delay }}
      style={{ transformPerspective: 800 }}
      aria-label={`Prospect rank ${rank}: ${track.track}, HPI ${Number.isFinite(track.hpi) ? track.hpi.toFixed(2) : '—'}. Show in ledger.`}
    >
      {/* top row: rank + badge */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`font-mono text-[12px] font-bold ${top ? 'text-vermilion' : 'text-amber'}`}>
            {String(rank).padStart(2, '0')}
          </span>
          {top && (
            <>
              <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-vermilion motion-safe:animate-rec-breathe" />
              <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-vermilion">TOP SIGNAL</span>
            </>
          )}
        </div>
        <VerdictBadge bucket={bucketOf(track.verdict)} />
      </div>
      {/* dial + title */}
      <div className="flex items-center gap-4">
        <HpiDial hpi={track.hpi} top={top} delay={delay} />
        <div className="min-w-0">
          <h4 className="line-clamp-2 text-[15px] font-semibold leading-snug text-ink-1">{track.track}</h4>
          <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
            {Number.isFinite(track.bpm) ? track.bpm.toFixed(1) : '—'} BPM · KEY {track.key} ·{' '}
            <span style={{ color: bright ? '#E8A33D' : '#B87333' }}>{track.brightness.toUpperCase()}</span>
          </p>
        </div>
      </div>
      {/* metric bars */}
      <div className="mt-4 flex flex-col gap-1.5">
        <MetricBar label="ENERGY" value={track.energy_density} min={METRIC_RANGES.energy_density.min} max={METRIC_RANGES.energy_density.max} tone={bright ? 'amber' : 'copper'} delay={delay + 0.2} />
        <MetricBar label="ALPHA" value={track.alpha} min={METRIC_RANGES.alpha.min} max={METRIC_RANGES.alpha.max} tone={bright ? 'amber' : 'copper'} delay={delay + 0.26} />
        <MetricBar label="STRUCT" value={track.structural_velocity} min={METRIC_RANGES.structural_velocity.min} max={METRIC_RANGES.structural_velocity.max} tone={bright ? 'amber' : 'copper'} delay={delay + 0.32} />
        <MetricBar label="MOD" value={track.market_modularity} min={METRIC_RANGES.market_modularity.min} max={METRIC_RANGES.market_modularity.max} tone={bright ? 'amber' : 'copper'} delay={delay + 0.38} />
      </div>
      {/* verdict excerpt */}
      <p className="mt-4 line-clamp-2 border-t border-line pt-3 text-[12.5px] leading-relaxed text-ink-3">
        {track.verdict}
      </p>
    </motion.button>
  )
}

/* ---------------- section ---------------- */
interface Props {
  onCrossFilter: (cf: CrossFilter) => void
}

export default function Prospects({ onCrossFilter }: Props) {
  const { topProspects, isLoading } = useCatalog()

  if (isLoading) {
    return (
      <section id="prospects" aria-label="Top prospects" className="scroll-mt-20">
        <SectionHeader overline="03 / TOP PROSPECTS" title="HIGHEST HPI — SPOTLIGHT" descriptor="Loading top signals…" />
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="console-panel panel-scanline h-[280px] animate-pulse p-5">
              <div className="h-4 w-20 rounded bg-bg-3" />
            </div>
          ))}
        </div>
      </section>
    )
  }

  return (
    <section id="prospects" aria-label="Top prospects" className="scroll-mt-20">
      <SectionHeader
        overline="03 / TOP PROSPECTS"
        title="HIGHEST HPI — SPOTLIGHT"
        descriptor="The six strongest signals in the vault, ranked by Hit Potential Index. Ties broken by market modularity, then alpha."
      />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {topProspects.map((t, i) => (
          <ProspectCard key={t.track} track={t} rank={i + 1} onCrossFilter={onCrossFilter} />
        ))}
      </div>
    </section>
  )
}
