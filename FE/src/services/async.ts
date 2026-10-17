/** A piece of work a page runs once, such as a button's request. */
export type Job = () => Promise<unknown>
