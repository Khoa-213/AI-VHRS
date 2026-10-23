import type { JobStatus } from '../../services/technician'

/** Colour of a job status chip (CSS variable). */
export const jobTone = (s: JobStatus) => (s === 'WRITING' || s === 'WRITTEN' ? 'var(--accent-text)' : s === 'PAUSED' ? 'var(--warn)' : 'var(--good)')

/** Chip class used on the dashboard lists. */
export const jobChip = (s: JobStatus) => (s === 'WRITING' || s === 'WRITTEN' ? 'orange' : s === 'PAUSED' ? 'warn' : 'good')

/** Where a job is opened: photo and QC once it is written, the run page before. */
export const jobLink = (id: number, s: JobStatus) => `/tech/${s === 'WRITTEN' ? 'qc' : 'preview'}/${id}`
