import { getInks, getPapers, getPens, type Ink, type Paper, type Pen } from '../services/orders'
import { useAsync } from './useAsync'

/** Names of the paper, pen and ink an order uses, looked up in the catalog. */
export function useMaterials(ids: { paperId: number | null; penId: number | null; inkId: number | null }): { paper?: Paper; pen?: Pen; ink?: Ink } {
  const papers = useAsync(getPapers, [])
  const pens = useAsync(() => getPens(), [])
  const inks = useAsync(() => (ids.penId ? getInks(ids.penId) : Promise.resolve([] as Ink[])), [ids.penId])
  return {
    paper: papers.data?.find((p) => p.id === ids.paperId),
    pen: pens.data?.find((p) => p.id === ids.penId),
    ink: inks.data?.find((i) => i.id === ids.inkId),
  }
}
