/** Clamp a number between 0 and 1. */
export const clamp01 = (n: number) => Math.min(1, Math.max(0, n))

/** Normalize `p` within segment [a, b] to 0..1. */
export const seg = (p: number, a: number, b: number) => clamp01((p - a) / (b - a))

/** Ease-out cubic. */
export const ease = (t: number) => 1 - Math.pow(1 - t, 3)
