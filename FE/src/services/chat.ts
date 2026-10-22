import { listOrders, SENT, type Order } from './orders'
import { listMessages, type Message } from './workshop'

export interface Conversation {
  order: Order
  last: Message | null
  unread: number
}

/**
 * The customer's chat list: one thread per sent order, newest activity first. Built from `/orders` and each order's
 * `/messages` for now; a single `/me/conversations` endpoint should replace the fan-out once the backend has it.
 */
export async function listConversations(): Promise<Conversation[]> {
  const orders = (await listOrders({ status: SENT, pageSize: 20 })).items
  const threads = await Promise.all(
    orders.map(async (order) => {
      const m = await listMessages(order.id).catch(() => null)
      return { order, last: m?.items.at(-1) ?? null, unread: m?.unread ?? 0 }
    }),
  )
  const at = (c: Conversation) => c.last?.createdAt ?? c.order.submittedAt ?? c.order.createdAt
  return threads.sort((a, b) => at(b).localeCompare(at(a)))
}
