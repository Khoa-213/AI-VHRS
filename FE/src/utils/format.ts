/** Vietnamese dong, e.g. 450.000₫ */
export const fmt = (n: number) => (n || 0).toLocaleString('vi-VN') + '₫'

/** Font size (in cqw) for text on a paper sheet, by text length. */
export const fontScale = (len: number) => (len < 22 ? 11 : len < 60 ? 7.5 : len < 140 ? 5.2 : 4)

/** 30% deposit, rounded to the nearest 1.000₫. */
export const depositOf = (total: number) => Math.round((total * 0.3) / 1000) * 1000

export const todayLabel = () =>
  new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
