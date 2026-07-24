import { useMemo, useRef, useState } from 'react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useGSAP } from '@gsap/react'
import Panel from '@/components/Panel'
import type { Track } from '@/lib/catalog'
import { bucketOf, truncate } from '@/lib/catalog'
import type { LedgerFilters } from '@/lib/filters'
import type { CrossFilter } from '@/lib/crossfilter'
import { prefersReducedMotion } from '@/lib/motion'

gsap.registerPlugin(ScrollTrigger, useGSAP)

const W = 640
const H = 360
const ML = 40
const MR = 16
const MT = 14
const MB = 30
const PW = W - ML - MR
const PH = H - MT - MB
const X_MIN = 60
const X_MAX = 190
const Y_MIN = 4.8
const Y_MAX = 9.2

const xFor = (bpm: number) => ML + ((bpm - X_MIN) / (X_MAX - X_MIN)) * PW
const yFor = (hpi: number) => MT + PH - ((hpi - Y_MIN) / (Y_MAX - Y_MIN)) * PH

interface Props {
  tracks: Track[]
  filters: LedgerFilters
  onCrossFilter: (cf: CrossFilter) => void
}

/** §3c — tempo × hit-potential scatter, color = tonal brightness. */
export default function BpmHpiScatter({ tracks, filters, onCrossFilter }: Props) {
  const root = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<number | null>(null)

  const TOTAL_TRACKS = tracks.length
  const BRIGHT_COUNT = useMemo(() => tracks.filter((t) => t.brightness === 'Bright/Aggressive').length, [tracks])
  const WARM_COUNT = TOTAL_TRACKS - BRIGHT_COUNT

  const AVG_BPM = useMemo(
    () => (TOTAL_TRACKS > 0 ? tracks.reduce((s, t) => s + t.bpm, 0) / TOTAL_TRACKS : 0),
    [tracks, TOTAL_TRACKS],
  )
  const AVG_HPI = useMemo(
    () => (TOTAL_TRACKS > 0 ? tracks.reduce((s, t) => s + t.hpi, 0) / TOTAL_TRACKS : 0),
    [tracks, TOTAL_TRACKS],
  )

  const dots = useMemo(
    () =>
      tracks.map((t, i) => ({
        i,
        x: xFor(t.bpm),
        y: yFor(t.hpi),
        bright: t.brightness === 'Bright/Aggressive',
        t,
      })),
    [tracks],
  )

  useGSAP(
    () => {
      const el = root.current
      if (!el) return
      if (prefersReducedMotion()) return
      const circles = el.querySelectorAll<SVGCircleElement>('.scatter-dot')
      const rules = el.querySelectorAll<SVGLineElement>('.scatter-rule')
      const labels = el.querySelectorAll<SVGTextElement>('.scatter-rule-label')
      gsap.set(circles, { scale: 0, transformOrigin: '50% 50%', transformBox: 'fill-box' })
      gsap.set(rules, { opacity: 0 })
      gsap.set(labels, { opacity: 0 })
      const tl = gsap.timeline({ paused: true })
      tl.to(circles, { scale: 1, duration: 0.5, ease: 'back.out(2.2)', stagger: { each: 0.004, from: 'random' } }, 0)
        .to(rules, { opacity: 1, duration: 0.4 }, 0.8)
        .to(labels, { opacity: 1, duration: 0.3 }, 0.95)
      const st = ScrollTrigger.create({ trigger: el, start: 'top 75%', once: true, onEnter: () => tl.play() })
      return () => {
        st.kill()
        tl.kill()
      }
    },
    { scope: root, dependencies: [tracks] },
  )

  const tone = filters.tone
  const hovered = hover !== null ? dots[hover] : null

  const legendBtn = (label: string, count: number, color: string, value: 'Bright/Aggressive' | 'Warm/Dark') => (
    <button
      type="button"
      onClick={() => onCrossFilter({ kind: 'tone', tone: tone === value ? 'ALL' : value })}
      aria-pressed={tone === value}
      className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3 transition-colors duration-150 hover:text-amber"
    >
      <span aria-hidden style={{ color }}>●</span> {label} {count}
    </button>
  )

  return (
    <div ref={root} className="order-2 col-span-12 lg:order-3 lg:col-span-7">
      <Panel
        title="TEMPO × HIT POTENTIAL"
        meta={
          <span className="flex items-center gap-4">
            {legendBtn('BRIGHT/AGGRESSIVE', BRIGHT_COUNT, '#E8A33D', 'Bright/Aggressive')}
            {legendBtn('WARM/DARK', WARM_COUNT, '#B87333', 'Warm/Dark')}
          </span>
        }
        className="h-full"
        contentClassName="relative"
      >
        <div className="relative overflow-x-auto">
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="min-w-[560px]"
            role="img"
            aria-label={`Scatter plot of BPM versus HPI for ${TOTAL_TRACKS} tracks; ${BRIGHT_COUNT} bright/aggressive, ${WARM_COUNT} warm/dark; mean BPM ${AVG_BPM != null ? AVG_BPM.toFixed(1) : '—'}, mean HPI ${AVG_HPI != null ? AVG_HPI.toFixed(2) : '—'}`}
          >
            {/* gridlines — every 20 BPM / 1 HPI */}
            {[60, 80, 100, 120, 140, 160, 180].map((b) => (
              <g key={b}>
                <line x1={xFor(b)} x2={xFor(b)} y1={MT} y2={MT + PH} stroke="#57493A" strokeOpacity="0.35" />
                <text x={xFor(b)} y={H - 10} textAnchor="middle" fill="#57493A" fontSize="9" fontFamily="'JetBrains Mono', monospace">
                  {b}
                </text>
              </g>
            ))}
            {[5, 6, 7, 8, 9].map((h) => (
              <g key={h}>
                <line x1={ML} x2={W - MR} y1={yFor(h)} y2={yFor(h)} stroke="#57493A" strokeOpacity="0.35" />
                <text x={ML - 6} y={yFor(h) + 3} textAnchor="end" fill="#57493A" fontSize="9" fontFamily="'JetBrains Mono', monospace">
                  {h}
                </text>
              </g>
            ))}
            {/* dots */}
            {dots.map(({ i, x, y, bright, t }) => {
              const dimmed =
                (tone === 'Bright/Aggressive' && !bright) || (tone === 'Warm/Dark' && bright)
              return (
                <circle
                  key={i}
                  className="scatter-dot cursor-pointer"
                  cx={x}
                  cy={y}
                  r={hover === i ? 6 : 4}
                  fill={bright ? '#E8A33D' : '#B87333'}
                  fillOpacity={dimmed ? 0.08 : 0.85}
                  stroke={hover === i ? '#F5C15C' : 'none'}
                  strokeWidth={hover === i ? 1.5 : 0}
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                  onClick={() => onCrossFilter({ kind: 'track', name: t.track })}
                >
                  <title>{t.track}</title>
                </circle>
              )
            })}
            {/* reference rules */}
            <line className="scatter-rule" x1={xFor(AVG_BPM)} x2={xFor(AVG_BPM)} y1={MT} y2={MT + PH} stroke="#57493A" strokeDasharray="4 4" />
            <line className="scatter-rule" x1={ML} x2={W - MR} y1={yFor(AVG_HPI)} y2={yFor(AVG_HPI)} stroke="#57493A" strokeDasharray="4 4" />
            <line className="scatter-rule" x1={ML} x2={W - MR} y1={yFor(8.5)} y2={yFor(8.5)} stroke="#D95B33" strokeDasharray="4 4" />
            <text className="scatter-rule-label" x={xFor(AVG_BPM) + 4} y={MT + 10} fill="#7D7160" fontSize="9" fontFamily="'JetBrains Mono', monospace">
              μ {AVG_BPM != null ? AVG_BPM.toFixed(1) : '—'}
            </text>
            <text className="scatter-rule-label" x={W - MR - 4} y={yFor(AVG_HPI) - 4} textAnchor="end" fill="#7D7160" fontSize="9" fontFamily="'JetBrains Mono', monospace">
              μ {AVG_HPI != null ? AVG_HPI.toFixed(2) : '—'}
            </text>
            <text className="scatter-rule-label" x={W - MR - 4} y={yFor(8.5) - 4} textAnchor="end" fill="#D95B33" fontSize="9" fontFamily="'JetBrains Mono', monospace">
              RED ZONE
            </text>
          </svg>
          {/* custom hover tooltip */}
          {hovered && (
            <div
              className="pointer-events-none absolute z-20 w-max max-w-[260px] rounded-[3px] border border-line-strong bg-bg-2 px-2.5 py-1.5 font-mono text-[11px] leading-snug shadow-panel"
              style={{
                left: `${(hovered.x / W) * 100}%`,
                top: `${(hovered.y / H) * 100}%`,
                transform: `translate(-50%, calc(-100% - 10px))`,
              }}
            >
              <p className="font-bold text-ink-1">{truncate(hovered.t.track, 34)}</p>
              <p className="text-ink-2">
                {hovered.t.bpm != null ? hovered.t.bpm.toFixed(1) : '—'} BPM · KEY {hovered.t.key} · HPI {hovered.t.hpi != null ? hovered.t.hpi.toFixed(2) : '—'}
              </p>
              <p className="text-ink-3">{bucketOf(hovered.t.verdict)}</p>
            </div>
          )}
        </div>
        <p className="mt-2 text-right font-mono text-[9px] uppercase tracking-[0.12em] text-ink-4 md:hidden">⇆ SCROLL PLOT</p>
      </Panel>
    </div>
  )
}
