import { api } from './api'
import type { OrderStatus, OrderType } from './orders'
import type { MessageKind } from './workshop'

export type ChatSide = 'customer' | 'workshop'

export interface Conversation {
  orderId: number
  code: string
  type: OrderType
  status: OrderStatus
  /** Workshop side only: who the thread is with. */
  customerName: string | null
  last: { body: string | null; kind: MessageKind; hasAttachment: boolean; createdAt: string; mine: boolean }
  unread: number
}

interface RawConversation {
  order_id: number; code: string; order_type: OrderType; order_status: OrderStatus; customer_name: string | null; unread: number
  last_message: { body: string | null; kind: MessageKind; has_attachment: boolean; created_at: string; mine: boolean }
}

const base = (side: ChatSide) => (side === 'workshop' ? '/workshop/conversations' : '/me/conversations')

/**
 * The chat list: one row per order that has at least one message, newest first. A customer sees their own orders; a Staff the
 * orders they hold plus the unclaimed pool (read only until claimed); a Manager every sent order.
 */
export async function listConversations(side: ChatSide): Promise<Conversation[]> {
  const r = await api<{ items: RawConversation[] }>(`${base(side)}?page=1&page_size=50`)
  return r.items.map((c) => ({
    orderId: c.order_id, code: c.code, type: c.order_type, status: c.order_status, customerName: c.customer_name, unread: c.unread,
    last: {
      body: c.last_message.body, kind: c.last_message.kind, hasAttachment: c.last_message.has_attachment,
      createdAt: c.last_message.created_at, mine: c.last_message.mine,
    },
  }))
}

/** Unread messages from the other side over every order: the badge on the chat button. */
export const unreadCount = async (side: ChatSide): Promise<number> => (await api<{ unread: number }>(`${base(side)}/unread-count`)).unread
