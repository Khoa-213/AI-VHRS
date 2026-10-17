import { useCallback, useRef, useState } from 'react'

/**
 * Runs saves one after another, in the order they were asked for, so an older request can never
 * overwrite a newer one. `pending` counts the saves still waiting or running.
 */
export function useSaveQueue() {
  const tail = useRef<PromiseLike<unknown>>(Promise.resolve())
  const [pending, setPending] = useState(0)

  const enqueue = useCallback(function <T>(job: () => PromiseLike<T>): PromiseLike<T> {
    setPending((n) => n + 1)
    const run = tail.current.then(job, job)
    tail.current = run.then(
      () => setPending((n) => n - 1),
      () => setPending((n) => n - 1),
    )
    return run
  }, [])

  /** Resolves when everything asked for so far has been saved. */
  const idle = useCallback(() => tail.current, [])

  return { enqueue, idle, pending }
}
