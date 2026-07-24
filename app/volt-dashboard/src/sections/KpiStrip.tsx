import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import CountUp from '@/components/CountUp'
import SectionHeader from '@/components/SectionHeader'
import { useCatalog } from '@/lib/catalog-context'
import { BUCKET_COLORS, BUCKETS, HIST_BINS } from '@/lib/catalog'
import { EASE_OUT_EXPO } from '@/lib/motion'

/* ---------------- fader accent (right edge) ---------------- */
function Fader({ pct, delay }: { pct: number; delay: number }) {
  const H = 96
  const y = (1 - pct) * H
  return (
    <div aria-hidden className="absolute bottom-6 right-0 top-6 hidden w-[3px] md:block">
      <div className="absolute inset-y-0 right-0 w-[3px] rounded-full bg-line-strong" />
      <motion.div
        className="absolute right-[-2.5px] h-2 w-2 rounded-[2px] bg-amber transition-shadow duration-150 group-hover:shadow-glow"
        initial={{ y: H }}
        whileInView={{ y }}
        viewport={{ once: true, margin: '0px 0px -15% 0px' }}
        transition={{ type: 'spring', stiffness: 90, damping: 18, delay }}
        style={{ top: 0 }}
      />
    </div>
  )
}

/* ---------------- sparklines ---------------- */
function DotMatrix() {
  return (
    <svg width="88" height="24" viewBox="0 0 88 24" aria-hidden className="opacity-60 transition-opacity duration-150 group-hover:opacity-100">
      {Array.from({ length: 33 }, (_, i) => {
        const col = i % 11
        const row = Math.floor(i / 11)
        return <circle key={i} cx={4 + col * 8} cy={4 + row * 8} r="1.6" fill="#E8A33D" opacity="0.4" />
      })}
    </svg>
  )
}

function HpiSpark() {
  const max = Math.max(...HIST_BINS.map((b) => b.count))
  return (
    <svg width="96" height="28" viewBox="0 0 96 28" aria-hidden className="opacity-60 transition-opacity duration-150 group-hover:opacity-100">
      {HIST_BINS.map((b, i) => {
        const h = Math.max(2, (b.count / max) * 24)
        const last = i === HIST_BINS.length - 1
        return (
          <motion.rect
            key={b.lo}
            x={2 + i * 12}
            width="8"
            rx="1"
            fill={last ? '#D95B33' : '#E8A33D'}
            opacity={last ? 0.8 : 0.6}
            initial={{ y: 26, height: 0 }}
            whileInView={{ y: 26 - h, height: h }}
            viewport={{ once: true, margin: '0px 0px -15% 0px' }}
            transition={{ duration: 0.8, delay: 0.3 + i * 0.05, ease: EASE_OUT_EXPO }}
          />
        )
      })}
    </svg>
  )
}

function StrategySpark({ buckets }: { buckets: { bucket: string; count: number }[] }) {
  const total = buckets.reduce((s, b) => s + b.count, 0) || 1
  const map = Object.fromEntries(buckets.map((b) => [b.bucket, b.count]))
  let x = 2
  return (
    <svg width="96" height="28" viewBox="0 0 96 28" aria-hidden className="opacity-60 transition-opacity duration-150 group-hover:opacity-100">
      {BUCKETS.map((bucket) => {
        const count = map[bucket] || 0
        const w = Math.max(2, (count / total) * 92)
        const seg = (
          <motion.rect
            key={bucket}
            x={x}
            y="10"
            width={w}
            height="8"
            rx="1"
            fill={BUCKET_COLORS[bucket]}
            opacity={bucket === 'ACQUIRE' ? 1 : 0.6}
            initial={{ scaleX: 0 }}
            whileInView={{ scaleX: 1 }}
            viewport={{ once: true, margin: '0px 0px -15% 0px' }}
            transition={{ duration: 0.6, delay: 0.35, ease: EASE_OUT_EXPO }}
            style={{ transformOrigin: `${x}px 14px` }}
          />
        )
        x += w + 1.5
        return seg
      })}
    </svg>
  )
}

function BpmSpark({ tracks }: { tracks: { bpm: number }[] }) {
  const bins = Array.from({ length: 12 }, () => 0)
  for (const t of tracks) {
    const idx = Math.min(11, Math.max(0, Math.floor(((t.bpm - 60) / 130) * 12)))
    bins[idx] += 1
  }
  const max = Math.max(...bins)
  const pts = bins.map((c, i) => [2 + (i * 92) / 11, 24 - (c / max) * 20] as const)
  const d = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const [ex, ey] = pts[pts.length - 1]
  return (
    <svg width="96" height="28" viewBox="0 0 96 28" aria-hidden className="opacity-60 transition-opacity duration-150 group-hover:opacity-100">
      <motion.path
        d={d}
        fill="none"
        stroke="#B87333"
        strokeWidth="1.5"
        initial={{ pathLength: 0 }}
        whileInView={{ pathLength: 1 }}
        viewport={{ once: true, margin: '0px 0px -15% 0px' }}
        transition={{ duration: 0.8, delay: 0.35, ease: 'easeOut' }}
      />
      <motion.circle
        cx={ex}
        cy={ey}
        r="2.2"
        fill="#E8A33D"
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true, margin: '0px 0px -15% 0px' }}
        transition={{ delay: 1.1, duration: 0.2 }}
      />
    </svg>
  )
}

/* ---------------- KPI card ---------------- */
interface KpiCardProps {
  name: string
  value: ReactNode
  unit: string
  context: ReactNode
  spark: ReactNode
  faderPct: number
  delay: number
}

function KpiCard({ name, value, unit, context, spark, faderPct, delay }: KpiCardProps) {
  return (
    <motion.div
      className="group console-panel panel-scanline relative p-5 pr-8 transition-colors duration-150 hover:border-line-strong"
      initial={{ opacity: 0, y: 32 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '0px 0px -15% 0px' }}
      transition={{ duration: 0.6, ease: EASE_OUT_EXPO, delay }}
    >
      <p className="label-micro">{name}</p>
      <p className="mt-3 font-mono font-bold leading-none text-amber" style={{ fontSize: 'clamp(36px, 4.5vw, 56px)', fontVariantNumeric: 'tabular-nums' }}>
        {value}
      </p>
      <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">{unit}</p>
      <div className="mt-3 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">{context}</div>
      <div className="mt-4">{spark}</div>
      <Fader pct={faderPct} delay={delay + 0.3} />
    </motion.div>
  )
}

/* ---------------- strip ---------------- */
export default function KpiStrip() {
  const { summary, tracks, buckets, isLoading } = useCatalog()

  if (isLoading || !summary) {
    return (
      <section id="metrics" aria-label="Signal metrics" className="scroll-mt-20">
        <SectionHeader overline="01 / SIGNAL METRICS" title="MASTER OUTPUT" descriptor="Loading catalog telemetry…" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="console-panel panel-scanline p-5 pr-8">
              <div className="label-micro opacity-40">LOADING</div>
              <div className="mt-3 h-10 w-24 animate-pulse rounded bg-bg-3" />
            </div>
          ))}
        </div>
      </section>
    )
  }

  const total = summary.total_tracks || 0
  const redZoneCount = summary.red_zone_count ?? 0
  const redZonePct = total > 0 ? (redZoneCount / total) * 100 : 0
  const acquireCount = summary.acquire_count ?? 0
  const avgHpi = summary.avg_hpi ?? 0
  const avgBpm = summary.avg_bpm ?? 0
  const minBpm = summary.min_bpm ?? 0
  const maxBpm = summary.max_bpm ?? 0

  return (
    <section id="metrics" aria-label="Signal metrics" className="scroll-mt-20">
      <SectionHeader
        overline="01 / SIGNAL METRICS"
        title="MASTER OUTPUT"
        descriptor="Headline telemetry for the current catalog analysis."
      />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          name="CATALOG SIZE"
          value={<CountUp value={total} delay={0.2} />}
          unit="TRACKS ANALYZED"
          context={<span>FULL VAULT · 100% COVERAGE</span>}
          spark={<DotMatrix />}
          faderPct={1}
          delay={0}
        />
        <KpiCard
          name="AVG HIT POTENTIAL"
          value={<CountUp value={avgHpi} decimals={2} delay={0.3} />}
          unit="MEAN HPI / 10"
          context={
            <span>
              RED ZONE ≥8.5 — <span className="text-amber">{redZoneCount} TRACKS</span> · {redZonePct.toFixed(1)}%
            </span>
          }
          spark={<HpiSpark />}
          faderPct={avgHpi / 10}
          delay={0.09}
        />
        <KpiCard
          name="ACQUISITION-READY"
          value={<CountUp value={acquireCount} delay={0.4} />}
          unit="TRACKS FLAGGED ACQUIRE"
          context={<span>{total > 0 ? ((acquireCount / total) * 100).toFixed(1) : '0.0'}% OF CATALOG</span>}
          spark={<StrategySpark buckets={buckets} />}
          faderPct={total > 0 ? acquireCount / total : 0}
          delay={0.18}
        />
        <KpiCard
          name="AVG TEMPO"
          value={<CountUp value={avgBpm} decimals={1} delay={0.5} />}
          unit="MEAN BPM"
          context={
            <span>
              RANGE {minBpm.toFixed(1)} — {maxBpm.toFixed(1)} BPM
            </span>
          }
          spark={<BpmSpark tracks={tracks} />}
          faderPct={maxBpm - minBpm > 0 ? (avgBpm - minBpm) / (maxBpm - minBpm) : 0}
          delay={0.27}
        />
      </div>
    </section>
  )
}
