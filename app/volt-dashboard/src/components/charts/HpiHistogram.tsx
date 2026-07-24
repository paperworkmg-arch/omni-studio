import { useMemo, useRef } from 'react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useGSAP } from '@gsap/react'
import ChartTip from '@/components/ChartTip'
import Panel from '@/components/Panel'
import type { Track } from '@/lib/catalog'
import type { LedgerFilters } from '@/lib/filters'
import type { CrossFilter } from '@/lib/crossfilter'
import { prefersReducedMotion } from '@/lib/motion'

gsap.registerPlugin(ScrollTrigger, useGSAP)

const W = 640
const H = 300
const ML = 36
const MR = 14
const MT = 30
const MB = 28
const PW = W - ML - MR
const PH = H - MT - MB
const Y_MAX = 160

interface Props {
  tracks: Track[]
  filters: LedgerFilters
  onCrossFilter: (cf: CrossFilter) => void
}

/** §3a — HPI distribution histogram, 8 bins over 5.0–9.0 with red-zone cap. */
export default function HpiHistogram({ tracks, filters, onCrossFilter }: Props) {
  const root = useRef<HTMLDivElement>(null)

  const TOTAL_TRACKS = tracks.length
  const RED_ZONE_MIN = 8.5
  const RED_ZONE_COUNT = useMemo(() => tracks.filter((t) => t.hpi >= RED_ZONE_MIN).length, [tracks])
  const RED_ZONE_PCT = TOTAL_TRACKS > 0 ? (RED_ZONE_COUNT / TOTAL_TRACKS) * 100 : 0

  const HIST_BINS = useMemo(() => {
    const bins = Array.from({ length: 8 }, (_, i) => {
      const lo = 5.0 + i * 0.5
      return { lo, hi: lo + 0.5, count: 0 }
    })
    for (const t of tracks) {
      const idx = Math.min(7, Math.max(0, Math.floor((t.hpi - 5.0) / 0.5)))
      bins[idx].count += 1
    }
    return bins
  }, [tracks])

  useGSAP(
    () => {
      const el = root.current
      if (!el) return
      const bars = el.querySelectorAll<SVGRectElement>('.hist-bar')
      const caps = el.querySelectorAll<SVGRectElement>('.hist-cap')
      const labels = el.querySelectorAll<SVGTextElement>('.hist-count')
      const rule = el.querySelector<SVGLineElement>('.hist-rule')
      const ruleLabel = el.querySelector<SVGTextElement>('.hist-rule-label')
      const callout = el.querySelector<HTMLDivElement>('.hist-callout')
      if (prefersReducedMotion()) return
      gsap.set(bars, { scaleY: 0, transformOrigin: '50% 100%' })
      gsap.set(caps, { scaleY: 0, transformOrigin: '50% 100%' })
      gsap.set(labels, { opacity: 0 })
      if (rule) gsap.set(rule, { scaleY: 0, transformOrigin: '50% 100%' })
      if (ruleLabel) gsap.set(ruleLabel, { opacity: 0 })
      if (callout) gsap.set(callout, { opacity: 0, y: 12 })
      const tl = gsap.timeline({ paused: true })
      tl.to(bars, { scaleY: 1, duration: 0.7, ease: 'expo.out', stagger: 0.06 }, 0)
        .to(caps, { scaleY: 1, duration: 0.7, ease: 'expo.out' }, 0.42)
        .to(labels, { opacity: 1, duration: 0.3, stagger: 0.06 }, 0.2)
      if (rule) tl.to(rule, { scaleY: 1, duration: 0.4, ease: 'expo.out' }, 0.55)
      if (ruleLabel) tl.to(ruleLabel, { opacity: 1, duration: 0.3 }, 0.85)
      if (callout) tl.to(callout, { opacity: 1, y: 0, duration: 0.5, ease: 'expo.out' }, 0.9)
      const st = ScrollTrigger.create({ trigger: el, start: 'top 75%', once: true, onEnter: () => tl.play() })
      return () => {
        st.kill()
        tl.kill()
      }
    },
    { scope: root, dependencies: [tracks] },
  )

  const binW = PW / HIST_BINS.length
  const barW = binW * 0.62
  const yFor = (c: number) => MT + PH - (c / Y_MAX) * PH
  const activeLo = filters.source?.startsWith('HPI ') ? filters.hpiRange[0] : null

  return (
    <div ref={root} className="order-1 col-span-12 lg:order-1 lg:col-span-7">
    <Panel
      title="HPI DISTRIBUTION"
      meta={`N=${TOTAL_TRACKS} · BIN 0.5`}
      className="h-full"
      contentClassName="relative"
    >
      {/* callout */}
      <div className="hist-callout pointer-events-none absolute right-6 top-0 z-10 max-w-[200px] text-right font-mono text-[11px] leading-snug text-ink-1">
        <span className="font-bold text-amber-hi">{RED_ZONE_PCT != null ? RED_ZONE_PCT.toFixed(1) : '0.0'}%</span> of the catalog sits in the red zone
      </div>
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="min-w-[560px]"
          role="img"
          aria-label={`Histogram of HPI scores; ${RED_ZONE_COUNT} of ${TOTAL_TRACKS} tracks score ${RED_ZONE_MIN} or higher`}
        >
          {/* gridlines */}
          {[0, 40, 80, 120, 160].map((v) => {
            const y = yFor(v)
            return (
              <g key={v}>
                <line x1={ML} x2={W - MR} y1={y} y2={y} stroke="#57493A" strokeOpacity="0.35" strokeWidth="1" />
                <text x={ML - 6} y={y + 3} textAnchor="end" fill="#7D7160" fontSize="9" fontFamily="'JetBrains Mono', monospace">
                  {v}
                </text>
              </g>
            )
          })}
          {/* bars */}
          {HIST_BINS.map((b, i) => {
            const x = ML + i * binW + (binW - barW) / 2
            const h = Math.max(2, (b.count / Y_MAX) * PH)
            const y = MT + PH - h
            const isRed = b.lo >= RED_ZONE_MIN - 1e-9
            const isActive = activeLo !== null && Math.abs(activeLo - b.lo) < 1e-9
            const pct = TOTAL_TRACKS > 0 ? ((b.count / TOTAL_TRACKS) * 100).toFixed(1) : '0.0'
            const bar = (
              <g
                key={b.lo}
                className="cursor-pointer"
                onClick={() => onCrossFilter({ kind: 'hpi', lo: b.lo, hi: b.hi, label: `HPI ${b.lo != null ? b.lo.toFixed(1) : '0.0'}–${b.hi != null ? b.hi.toFixed(1) : '0.0'}` })}
              >
                <title>{`${b.lo != null ? b.lo.toFixed(1) : '0.0'}–${b.hi != null ? b.hi.toFixed(1) : '0.0'} — ${b.count} TRACKS (${pct}%)`}</title>
                <rect
                  className="hist-bar transition-[fill] duration-150 hover:fill-amber-hi"
                  x={x}
                  y={y}
                  width={barW}
                  height={h}
                  fill="#E8A33D"
                  fillOpacity={isRed ? 1 : 0.7}
                  stroke={isActive ? '#F5C15C' : 'none'}
                  strokeWidth={isActive ? 1 : 0}
                />
                {isRed && (
                  <rect
                    className="hist-cap"
                    x={x}
                    y={y}
                    width={barW}
                    height="6"
                    fill="#D95B33"
                    style={{ filter: 'drop-shadow(0 0 6px rgba(232,163,61,0.45))' }}
                  />
                )}
                <text
                  className="hist-count"
                  x={x + barW / 2}
                  y={y - 5}
                  textAnchor="middle"
                  fill="#7D7160"
                  fontSize="9"
                  fontFamily="'JetBrains Mono', monospace"
                >
                  {b.count}
                </text>
                <text
                  x={x + barW / 2}
                  y={MT + PH + 14}
                  textAnchor="middle"
                  fill="#57493A"
                  fontSize="9"
                  fontFamily="'JetBrains Mono', monospace"
                >
                  {b.lo != null ? b.lo.toFixed(1) : '0.0'}
                </text>
              </g>
            )
            return (
              <ChartTip key={b.lo} label={`${b.lo != null ? b.lo.toFixed(1) : '0.0'}–${b.hi != null ? b.hi.toFixed(1) : '0.0'} — ${b.count} TRACKS (${pct}%)`}>
                {bar}
              </ChartTip>
            )
          })}
          {/* red-zone rule at HPI 8.5 */}
          <line
            className="hist-rule"
            x1={ML + 7 * binW}
            x2={ML + 7 * binW}
            y1={MT}
            y2={MT + PH}
            stroke="#D95B33"
            strokeWidth="1"
            strokeDasharray="4 4"
          />
          <text
            className="hist-rule-label"
            x={ML + 7 * binW - 6}
            y={MT + 10}
            textAnchor="end"
            fill="#D95B33"
            fontSize="9"
            fontFamily="'JetBrains Mono', monospace"
            letterSpacing="1"
          >
            RED ZONE ≥8.5
          </text>
        </svg>
      </div>
      <p className="mt-2 text-right font-mono text-[9px] uppercase tracking-[0.12em] text-ink-4 md:hidden">⇆ SCROLL PLOT</p>
    </Panel>
    </div>
  )
}
