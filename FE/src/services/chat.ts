import { listOrders, SENT, type Order } from './orders'
import { listMessages, listWork, type Message, type WorkOrder } from './workshop'

export interface Conversation {
  order: Order
  /** Workshop side only: who the thread is with. */
  customerName?: string
  last: Message | null
  unread: number
}

const at = (c: Conversation) => c.last?.createdAt ?? c.order.submittedAt ?? c.order.createdAt
const byActivity = (list: Conversation[]) => list.sort((a, b) => at(b).localeCompare(at(a)))

async function withMessages(orders: Order[], name: (o: Order) => string | undefined): Promise<Conversation[]> {
  const threads = await Promise.all(
    orders.map(async (order) => {
      const m = await listMessages(order.id).catch(() => null)
      return { order, customerName: name(order), last: m?.items.at(-1) ?? null, unread: m?.unread ?? 0 }
    }),
  )
  return byActivity(threads)
}

/**
 * The customer's chat list: one thread per sent order, newest activity first. Built from `/orders` and each order's
 * `/messages` for now; a single `/me/conversations` endpoint should replace the fan-out once the backend has it.
 */
export async function listConversations(): Promise<Conversation[]> {
  return withMessages((await listOrders({ status: SENT, pageSize: 20 })).items, () => undefined)
}

/**
 * The workshop chat list. A Staff chats only on orders they hold (the backend answers `ORDER_NOT_CLAIMED` otherwise);
 * a Manager may answer on any sent order. Same fan-out as the customer list until `/workshop/conversations` exists.
 */
export async function listWorkConversations(staffId: number | undefined, manager: boolean): Promise<Conversation[]> {
  const orders = (await listWork({ status: SENT, pageSize: 30 })).items
  const mine = manager ? orders : orders.filter((o) => o.assignedStaffId === staffId)
  return withMessages(mine, (o) => (o as WorkOrder).customerName || undefined)
}
