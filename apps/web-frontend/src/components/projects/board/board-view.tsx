"use client";

import { useState, useCallback, useEffect } from "react";
import { DragDropContext, type DropResult } from "@hello-pangea/dnd";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { BoardColumn, type ColumnData } from "./board-column";
import type { TicketData } from "./board-card";
import { TicketDetailModal } from "./ticket-detail-modal";
import {
  type BoardColumn as ApiBoardColumn,
  type ProjectMember,
  type TicketResponse,
  getBoardTickets,
  createTicket as apiCreateTicket,
  moveTicket as apiMoveTicket,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

interface BoardViewProps {
  projectSlug: string;
  boardColumns: ApiBoardColumn[];
  members: ProjectMember[];
}

const AVATAR_COLORS = [
  "#6366f1",
  "#8b5cf6",
  "#06b6d4",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#ec4899",
  "#14b8a6",
];

function getAvatarColor(index: number) {
  return AVATAR_COLORS[index % AVATAR_COLORS.length];
}

function apiTicketToCard(
  t: TicketResponse,
  memberIndex: Map<string, number>
): TicketData {
  return {
    id: t.id,
    key: t.ticket_key,
    title: t.title,
    type: t.type as TicketData["type"],
    priority: t.priority as TicketData["priority"],
    labels: t.labels || [],
    dueDate: t.due_date
      ? new Date(t.due_date + "T00:00:00").toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
          year: "numeric",
        })
      : undefined,
    assignee: t.assignee
      ? {
          initials: `${t.assignee.first_name[0]}${t.assignee.last_name[0]}`,
          name: `${t.assignee.first_name} ${t.assignee.last_name}`,
          color: getAvatarColor(memberIndex.get(t.assignee.id) ?? 0),
        }
      : undefined,
  };
}

function buildColumns(
  boardColumns: ApiBoardColumn[],
  tickets: TicketResponse[],
  memberIndex: Map<string, number>
): ColumnData[] {
  const cols = boardColumns
    .sort((a, b) => a.position - b.position)
    .map((col) => ({
      id: col.id,
      name: col.name,
      tickets: [] as TicketData[],
    }));

  for (const ticket of tickets) {
    const col = cols.find((c) => c.id === ticket.column_id);
    if (col) {
      col.tickets.push(apiTicketToCard(ticket, memberIndex));
    }
  }

  for (const col of cols) {
    const posMap = new Map(
      tickets
        .filter((t) => t.column_id === col.id)
        .map((t) => [t.id, t.position])
    );
    col.tickets.sort(
      (a, b) => (posMap.get(a.id) ?? 0) - (posMap.get(b.id) ?? 0)
    );
  }

  return cols;
}

export function BoardView({
  projectSlug,
  boardColumns,
  members,
}: BoardViewProps) {
  const { token } = useAuth();
  const [columns, setColumns] = useState<ColumnData[]>([]);
  const [rawTickets, setRawTickets] = useState<TicketResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Modal state
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const memberIndex = new Map(
    members.map((m, i) => [m.user_id, i])
  );

  // Load tickets
  useEffect(() => {
    async function load() {
      if (!token) return;
      const { data, error } = await getBoardTickets(token, projectSlug);
      if (error) {
        toast.error(error);
        setIsLoading(false);
        return;
      }
      if (data) {
        setRawTickets(data.tickets);
        setColumns(buildColumns(boardColumns, data.tickets, memberIndex));
      }
      setIsLoading(false);
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, projectSlug]);

  // Find the selected raw ticket for the modal
  const selectedRawTicket = selectedTicketId
    ? rawTickets.find((t) => t.id === selectedTicketId) ?? null
    : null;

  // ---- Open ticket modal ----
  const handleTicketClick = useCallback((ticketId: string) => {
    setSelectedTicketId(ticketId);
    setModalOpen(true);
  }, []);

  // ---- Drag end ----
  const onDragEnd = useCallback(
    async (result: DropResult) => {
      const { source, destination, draggableId } = result;
      if (!destination) return;
      if (
        source.droppableId === destination.droppableId &&
        source.index === destination.index
      )
        return;

      // Optimistic update
      setColumns((prev) => {
        const updated = prev.map((col) => ({
          ...col,
          tickets: [...col.tickets],
        }));
        const sourceCol = updated.find((c) => c.id === source.droppableId);
        const destCol = updated.find((c) => c.id === destination.droppableId);
        if (!sourceCol || !destCol) return prev;
        const [moved] = sourceCol.tickets.splice(source.index, 1);
        destCol.tickets.splice(destination.index, 0, moved);
        return updated;
      });

      const ticket = rawTickets.find((t) => t.id === draggableId);
      if (!ticket || !token) return;

      const { error } = await apiMoveTicket(
        token,
        projectSlug,
        ticket.ticket_key,
        {
          column_id: destination.droppableId,
          position: destination.index,
        }
      );

      if (error) {
        toast.error("Failed to move ticket");
        const { data } = await getBoardTickets(token, projectSlug);
        if (data) {
          setRawTickets(data.tickets);
          setColumns(buildColumns(boardColumns, data.tickets, memberIndex));
        }
      } else {
        // Update raw ticket's column_id
        setRawTickets((prev) =>
          prev.map((t) =>
            t.id === draggableId
              ? {
                  ...t,
                  column_id: destination.droppableId,
                  position: destination.index,
                }
              : t
          )
        );
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [token, projectSlug, rawTickets]
  );

  // ---- Create ticket ----
  const handleCreateTicket = useCallback(
    async (columnId: string, title: string) => {
      if (!token) return;
      const { data, error } = await apiCreateTicket(token, projectSlug, {
        title,
        column_id: columnId,
      });
      if (error) {
        toast.error(error);
        return;
      }
      if (data) {
        setRawTickets((prev) => [...prev, data]);
        setColumns((prev) =>
          prev.map((col) =>
            col.id === columnId
              ? {
                  ...col,
                  tickets: [
                    ...col.tickets,
                    apiTicketToCard(data, memberIndex),
                  ],
                }
              : col
          )
        );
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [token, projectSlug]
  );

  // ---- Ticket updated from modal ----
  const handleTicketUpdated = useCallback(
    (updated: TicketResponse) => {
      setRawTickets((prev) =>
        prev.map((t) => (t.id === updated.id ? updated : t))
      );
      setColumns((prev) =>
        prev.map((col) => ({
          ...col,
          tickets: col.tickets.map((t) =>
            t.id === updated.id
              ? apiTicketToCard(updated, memberIndex)
              : t
          ),
        }))
      );
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  // ---- Ticket deleted from modal ----
  const handleTicketDeleted = useCallback(
    (ticketKey: string) => {
      const ticket = rawTickets.find((t) => t.ticket_key === ticketKey);
      if (!ticket) return;
      setRawTickets((prev) => prev.filter((t) => t.ticket_key !== ticketKey));
      setColumns((prev) =>
        prev.map((col) => ({
          ...col,
          tickets: col.tickets.filter((t) => t.id !== ticket.id),
        }))
      );
    },
    [rawTickets]
  );

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <>
      <DragDropContext onDragEnd={onDragEnd}>
        <div className="flex h-full gap-3">
          {columns.map((column, idx) => (
            <BoardColumn
              key={column.id}
              column={column}
              isLast={idx === columns.length - 1}
              onCreateTicket={handleCreateTicket}
              onTicketClick={handleTicketClick}
            />
          ))}
        </div>
      </DragDropContext>

      <TicketDetailModal
        ticket={selectedRawTicket}
        projectSlug={projectSlug}
        members={members}
        open={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setSelectedTicketId(null);
        }}
        onUpdated={handleTicketUpdated}
        onDeleted={handleTicketDeleted}
      />
    </>
  );
}
