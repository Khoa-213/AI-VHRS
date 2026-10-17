/** A piece of work a page runs once, such as a button's request. */
export type Job = () => Promise<unknown>

/** Runs a job with the page's busy and error handling. */
export type Run = (job: Job) => Promise<void>
