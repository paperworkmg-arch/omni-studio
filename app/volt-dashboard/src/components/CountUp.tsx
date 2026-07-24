import { useRef } from 'react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useGSAP } from '@gsap/react'
import { prefersReducedMotion } from '@/lib/motion'

gsap.registerPlugin(ScrollTrigger, useGSAP)

interface CountUpProps {
  value: number
  decimals?: number
  duration?: number
  delay?: number
  className?: string
  format?: (n: number) => string
}

/** GSAP-tweened number (design.md §7 count-up: 1400ms, expo, tabular mono). */
export default function CountUp({ value, decimals = 0, duration = 1.4, delay = 0.2, className, format }: CountUpProps) {
  const ref = useRef<HTMLSpanElement>(null)

  useGSAP(
    () => {
      const el = ref.current
      if (!el) return
      const render = (v: number) => {
        if (format) {
          el.textContent = format(v)
        } else {
          el.textContent = Number.isFinite(v) ? v.toFixed(decimals) : '—'
        }
      }
      if (prefersReducedMotion()) {
        render(value)
        return
      }
      const state = { v: 0 }
      const tween = gsap.to(state, {
        v: value,
        duration,
        delay,
        ease: 'expo.out',
        snap: { v: Math.pow(10, -decimals) },
        onUpdate: () => render(state.v),
        paused: true,
      })
      const st = ScrollTrigger.create({
        trigger: el,
        start: 'top 88%',
        once: true,
        onEnter: () => tween.play(),
      })
      return () => {
        st.kill()
        tween.kill()
      }
    },
    { dependencies: [value, decimals, duration, delay] },
  )

  return (
    <span ref={ref} className={className} style={{ fontVariantNumeric: 'tabular-nums' }}>
      {format ? format(0) : Number.isFinite(0) ? (0).toFixed(decimals) : '—'}
    </span>
  )
}
