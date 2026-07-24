import { memo, useEffect, useRef } from 'react'
import { prefersReducedMotion } from '@/lib/motion'

/**
 * Dual-needle VU meter (44×22). Perpetual random-walk rotation within
 * −24°…+6° (design.md §7). Pauses when the tab is hidden; static under
 * prefers-reduced-motion.
 */
const VuMeter = memo(function VuMeter() {
  const n1 = useRef<SVGGElement>(null)
  const n2 = useRef<SVGGElement>(null)

  useEffect(() => {
    const park = () => {
      n1.current?.setAttribute('transform', 'rotate(-12 16 20)')
      n2.current?.setAttribute('transform', 'rotate(-8 28 20)')
    }
    if (prefersReducedMotion()) {
      park()
      return
    }
    let raf = 0
    let iv: ReturnType<typeof setInterval> | null = null
    const a1 = { cur: -12, tgt: -12 }
    const a2 = { cur: -8, tgt: -8 }
    const walk = () => -24 + Math.random() * 30
    const startIv = () => {
      iv = setInterval(() => {
        a1.tgt = walk()
        a2.tgt = walk()
      }, 300 + Math.random() * 150)
    }
    const loop = () => {
      /* spring-return-ish lerp (stiffness 90 / damping 18 feel) */
      a1.cur += (a1.tgt - a1.cur) * 0.09
      a2.cur += (a2.tgt - a2.cur) * 0.09
      n1.current?.setAttribute('transform', `rotate(${Number.isFinite(a1.cur) ? a1.cur.toFixed(2) : '0.00'} 16 20)`)
      n2.current?.setAttribute('transform', `rotate(${Number.isFinite(a2.cur) ? a2.cur.toFixed(2) : '0.00'} 28 20)`)
      raf = requestAnimationFrame(loop)
    }
    startIv()
    raf = requestAnimationFrame(loop)
    const onVis = () => {
      if (document.hidden) {
        if (iv) clearInterval(iv)
        iv = null
        cancelAnimationFrame(raf)
      } else {
        if (!iv) startIv()
        raf = requestAnimationFrame(loop)
      }
    }
    document.addEventListener('visibilitychange', onVis)
    return () => {
      if (iv) clearInterval(iv)
      cancelAnimationFrame(raf)
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [])

  return (
    <svg width="44" height="22" viewBox="0 0 44 22" aria-hidden="true" className="shrink-0">
      {/* tick arc */}
      {[-24, -12, 0, 6].map((deg) => {
        const rad = ((deg - 90) * Math.PI) / 180
        const cx = 22
        const cy = 20
        const r1 = 15
        const r2 = deg === 6 ? 12 : 13.4
        return (
          <line
            key={deg}
            x1={cx + r1 * Math.cos(rad)}
            y1={cy + r1 * Math.sin(rad)}
            x2={cx + r2 * Math.cos(rad)}
            y2={cy + r2 * Math.sin(rad)}
            stroke={deg === 6 ? '#D95B33' : '#3D332A'}
            strokeWidth="1"
          />
        )
      })}
      {/* needles with amber tips */}
      <g ref={n1} transform="rotate(-12 16 20)">
        <line x1="16" y1="20" x2="16" y2="7.5" stroke="#B3A58D" strokeWidth="1" />
        <line x1="16" y1="9.6" x2="16" y2="7.5" stroke="#E8A33D" strokeWidth="1.4" />
      </g>
      <g ref={n2} transform="rotate(-8 28 20)">
        <line x1="28" y1="20" x2="28" y2="7.5" stroke="#B3A58D" strokeWidth="1" />
        <line x1="28" y1="9.6" x2="28" y2="7.5" stroke="#E8A33D" strokeWidth="1.4" />
      </g>
      <circle cx="16" cy="20" r="1.2" fill="#3D332A" />
      <circle cx="28" cy="20" r="1.2" fill="#3D332A" />
    </svg>
  )
})

export default VuMeter

/** Tiny static VU glyph for the footer. */
export function StaticVuGlyph() {
  return (
    <svg width="24" height="12" viewBox="0 0 24 12" aria-hidden="true" className="shrink-0">
      {[-20, 0, 20].map((deg) => {
        const rad = ((deg - 90) * Math.PI) / 180
        return (
          <line
            key={deg}
            x1={12 + 9 * Math.cos(rad)}
            y1={11 + 9 * Math.sin(rad)}
            x2={12 + 7 * Math.cos(rad)}
            y2={11 + 7 * Math.sin(rad)}
            stroke="#3D332A"
            strokeWidth="1"
          />
        )
      })}
      <line x1="12" y1="11" x2="15" y2="4" stroke="#E8A33D" strokeWidth="1" />
      <circle cx="12" cy="11" r="1" fill="#3D332A" />
    </svg>
  )
}
