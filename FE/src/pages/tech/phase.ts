import { useEffect, useState } from 'react'
import type { Order } from '../../types'

/** Where an assigned order is from the technician's point of view. */
export type Phase = 'qc' | 'live' | 'ready' | 'wait' | 'done'

const inQueue = (o: Order) => o.status === 'Queued' || o.status === 'Rewriting'

/** The robot run has reached its end time. Photo and QC comes next. */
export const runDone = (o: Order, now: number) =>
  !!o.run && inQueue(o) && now >= o.run.startedAt + o.run.seconds * 1000

export function phaseOf(o: Order, now: number): Phase | null {
  if (o.run && inQueue(o)) return runDone(o, now) ? 'qc' : 'live'
  if (inQueue(o)) return 'ready'
  if (o.status === 'Accepted') return 'wait'
  if (['Written', 'Shipped', 'Delivered'].includes(o.status)) return 'done'
  return null
}

/** Re-renders on an interval so time-based phases flip by themselves. */
export function useNow(ms = 1000) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), ms)
    return () => window.clearInterval(t)
  }, [ms])
  return now
}

/** Prototype only: a drawn stand-in for a camera shot, so QC can be completed without a camera. */
export function samplePhoto(label: string, paper: string, ink: string): string {
  const c = document.createElement('canvas')
  c.width = 640
  c.height = 480
  const g = c.getContext('2d')
  if (!g) return ''
  g.fillStyle = '#2a2c33'
  g.fillRect(0, 0, 640, 480)
  g.fillStyle = paper
  g.fillRect(70, 50, 500, 380)
  g.fillStyle = ink
  g.font = '600 44px "Dancing Script", cursive'
  g.textAlign = 'center'
  g.fillText('Sample photo', 320, 235)
  g.font = '500 18px sans-serif'
  g.fillText(label, 320, 285)
  return c.toDataURL('image/jpeg', 0.72)
}

/** Downscale a photo to a small JPEG so it fits in localStorage. */
export function shrinkImage(file: File, max = 1100, quality = 0.72): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      const k = Math.min(1, max / Math.max(img.width, img.height))
      const c = document.createElement('canvas')
      c.width = Math.max(1, Math.round(img.width * k))
      c.height = Math.max(1, Math.round(img.height * k))
      const g = c.getContext('2d')
      URL.revokeObjectURL(url)
      if (!g) {
        reject(new Error('Could not process that photo. Try a JPEG or PNG.'))
        return
      }
      g.drawImage(img, 0, 0, c.width, c.height)
      resolve(c.toDataURL('image/jpeg', quality))
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('This browser cannot open that photo format. Use a JPEG or PNG.'))
    }
    img.src = url
  })
}
