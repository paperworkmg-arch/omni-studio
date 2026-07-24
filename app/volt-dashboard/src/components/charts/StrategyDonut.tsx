import { useMemo, useRef, useState } from 'react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useGSAP } from '@gsap/react'
import Panel from '@/components/Panel'
import type { Track, Bucket } from '@/lib/catalog'
import { BUCKET_COLORS, bucketOf } from '@/lib/catalog'
import type { LedgerFilters } from '@/lib/filters'
import type { CrossFilter } from '@/lib/crossfilter'
import { prefersReducedMotion } from '@/lib/motion'

gsap.registerPlugin(ScrollTrigger, useGSAP)

const CX = 112
const CY = 112
const R = 78
const SW = 36
const GAP_DEG = (2 / R) * (180 / Math.PI)

const DONUT_ORDER: Bucket[] = ['PITCH', 'ANALYZE', 'ACQUIRE', 'PITCH+LICENSE', 'LICENSE']

function polar(angleDeg: number, r: number): [number, number] {
  const a = ((angleDeg - 90) * Math.PI) / 180
  return [CX + r * Math.cos(a), CY + r * Math.sin(a)]
}

function arcPath(a0: number, a1: number, r: number): string {
  const [x0, y0] = polar(a0, r)
  const [x1, y1] = polar(a1, r)
  const large = a1 - a0 > 180 ? 1 : 0
  return `M ${(x0 != null ? x0 : 0).toFixed(2)} ${(y0 != null ? y0 : 0).toFixed(2)} A ${r} ${r} 0 ${large} 1 ${(x1 != null ? x1 : 0).toFixed(2)} ${(y1 != null ? y1 : 0).toFixed(2)}`
}

interface Props {
  tracks: Track[]
  filters: LedgerFilters
  onCrossFilter: (cf: CrossFilter) => void
}

/** §3b — strategy mix donut, clockwise from 12 o'clock descending. */
export default function StrategyDonut({ tracks, filters, onCrossFilter }: Props) {
  const root = useRef<HTMLDivElement>(null)
  const centerTop = useRef<SVGTextElement>(null)
  const [hovered, setHovered] = useState<Bucket | null>(null)

  const TOTAL_TRACKS = tracks.length

  const BUCKET_COUNTS = useMemo(() => {
    const init: Record<Bucket, number> = { ACQUIRE: 0, PITCH: 0, 'PITCH+LICENSE': 0, LICENSE: 0, ANALYZE: 0 }
    return tracks.reduce((acc, t) => {
      acc[bucketOf(t.verdict)] += 1
      return acc
    }, init)
  }, [tracks])

  /* segment angles */
  const segs = useMemo(() => {
    let a = 0
    return DONUT_ORDER.map((bucket) => {
      const count = BUCKET_COUNTS[bucket]
      const frac = TOTAL_TRACKS > 0 ? count / TOTAL_TRACKS : 0
      const a0 = a * 360 + GAP_DEG / 2
      const a1 = (a + frac) * 360 - GAP_DEG / 2
      a += frac
      return { bucket, count, frac, a0, a1 }
    })
  }, [BUCKET_COUNTS, TOTAL_TRACKS])

  useGSAP(
    () => {
      const el = root.current
      if (!el) return
      if (prefersReducedMotion()) {
        if (centerTop.current) centerTop.current.textContent = String(TOTAL_TRACKS)
        return
      }
      const paths = el.querySelectorAll<SVGPathElement>('.donut-seg')
      const legend = el.querySelectorAll<HTMLLIElement>('.donut-legend-row')
      gsap.set(paths, { strokeDasharray: 1, strokeDashoffset: 1 })
      gsap.set(legend, { opacity: 0, y: 8 })
      const state = { v: 0 }
      const tl = gsap.timeline({ paused: true })
      tl.to(paths, { strokeDashoffset: 0, duration: 0.9, ease: 'expo.out', stagger: 0.08 }, 0)
        .to(state, {
          v: TOTAL_TRACKS,
          duration: 0.9,
          ease: 'expo.out',
          snap: { v: 1 },
          onUpdate: () => {
            if (centerTop.current && !hovered) centerTop.current.textContent = String(Math.round(state.v))
          },
        }, 0)
        .to(legend, { opacity: 1, y: 0, duration: 0.4, stagger: 0.05, ease: 'expo.out' }, 0.3)
      const st = ScrollTrigger.create({ trigger: el, start: 'top 75%', once: true, onEnter: () => tl.play() })
      return () => {
        st.kill()
        tl.kill()
      }
    },
    { scope: root, dependencies: [tracks] },
  )

  const activeBucket = filters.strategy !== 'ALL' ? filters.strategy : null

  return (
    <div ref={root} className="order-3 col-span-12 lg:order-2 lg:col-span-5">
      <Panel title="STRATEGY MIX" meta="5 BUCKETS" className="h-full">
        <div className="flex flex-col items-center gap-6 md:flex-row md:items-center md:gap-8">
          <svg
            viewBox="0 0 224 224"
            className="w-full max-w-[260px] shrink-0"
            role="img"
            aria-label={`Strategy mix donut; PITCH ${BUCKET_COUNTS.PITCH}, ANALYZE ${BUCKET_COUNTS.ANALYZE}, ACQUIRE ${BUCKET_COUNTS.ACQUIRE}, PITCH+LICENSE ${BUCKET_COUNTS['PITCH+LICENSE']}, LICENSE ${BUCKET_COUNTS.LICENSE}`}
          >
            {/* track ring */}
            <circle cx={CX} cy={CY} r={R} fill="none" stroke="#1C1815" strokeWidth={SW} />
            {segs.map(({ bucket, a0, a1 }) => {
              const dim = hovered && hovered !== bucket
              return (
                <path
                  key={bucket}
                  className="donut-seg cursor-pointer transition-[opacity,stroke-width] duration-150"
                  d={arcPath(a0, a1, R)}
                  fill="none"
                  stroke={BUCKET_COLORS[bucket]}
                  strokeWidth={hovered === bucket ? SW + 4 : SW}
                  strokeOpacity={dim ? 0.35 : 1}
                  pathLength={1}
                  onMouseEnter={() => setHovered(bucket)}
                  onMouseLeave={() => setHovered(null)}
                  onClick={() => onCrossFilter({ kind: 'strategy', bucket })}
                >
                  <title>{`${bucket} — ${BUCKET_COUNTS[bucket]} TRACKS (${TOTAL_TRACKS > 0 ? (BUCKET_COUNTS[bucket] / TOTAL_TRACKS * 100).toFixed(1) : '0.0'}%)`}</title>
                </path>
              )
            })}
            {/* active segment outer arc */}
            {activeBucket &&
              segs
                .filter((s) => s.bucket === activeBucket)
                .map((s) => (
                  <path
                    key={`active-${s.bucket}`}
                    d={arcPath(s.a0, s.a1, R + SW / 2 + 3)}
                    fill="none"
                    stroke="#F5C15C"
                    strokeWidth="1"
                    pointerEvents="none"
                  />
                ))}
            {/* center readout */}
            {hovered ? (
              <>
                <text x={CX} y={CY - 2} textAnchor="middle" fill={BUCKET_COLORS[hovered]} fontSize="22" fontWeight="700" fontFamily="'JetBrains Mono', monospace">
                  {TOTAL_TRACKS > 0 ? ((BUCKET_COUNTS[hovered] / TOTAL_TRACKS) * 100).toFixed(1) : '0.0'}%
                </text>
                <text x={CX} y={CY + 16} textAnchor="middle" fill="#7D7160" fontSize="8.5" fontFamily="'JetBrains Mono', monospace" letterSpacing="1.4">
                  {hovered}
                </text>
                <text x={CX} y={CY + 28} textAnchor="middle" fill="#57493A" fontSize="8.5" fontFamily="'JetBrains Mono', monospace" letterSpacing="1.4">
                  {BUCKET_COUNTS[hovered]} TRACKS
                </text>
              </>
            ) : (
              <>
                <text ref={centerTop} x={CX} y={CY + 2} textAnchor="middle" fill="#EFE6D6" fontSize="28" fontWeight="700" fontFamily="'JetBrains Mono', monospace">
                  0
                </text>
                <text x={CX} y={CY + 20} textAnchor="middle" fill="#7D7160" fontSize="9" fontFamily="'JetBrains Mono', monospace" letterSpacing="1.6">
                  TRACKS
                </text>
              </>
            )}
          </svg>
          {/* legend */}
          <ul className="w-full min-w-0 flex-1">
            {segs.map(({ bucket, count, frac }) => (
              <li key={bucket} className="donut-legend-row">
                <button
                  type="button"
                  onClick={() => onCrossFilter({ kind: 'strategy', bucket })}
                  onMouseEnter={() => setHovered(bucket)}
                  onMouseLeave={() => setHovered(null)}
                  className="flex w-full items-center gap-2.5 border-b border-line py-2 text-left transition-colors duration-150 last:border-0 hover:bg-bg-2"
                >
                  <span aria-hidden className="h-2 w-2 shrink-0 rounded-[1px]" style={{ backgroundColor: BUCKET_COLORS[bucket] }} />
                  <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-2">{bucket}</span>
                  <span className="ml-auto font-mono text-[10px] text-ink-3" style={{ fontVariantNumeric: 'tabular-nums' }}>
                    {count} · {(frac * 100).toFixed(1)}%
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </Panel>
    </div>
  )
}
