"use client";

import { useState, useCallback } from "react";
import { DragDropContext, type DropResult } from "@hello-pangea/dnd";

import { BoardColumn, type ColumnData } from "./board-column";
import type { TicketData } from "./board-card";
import type { BoardColumn as ApiBoardColumn } from "@/lib/api";

interface BoardViewProps {
  projectSlug: string;
  boardColumns: ApiBoardColumn[];
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

let ticketCounter = 0;

function generateTicketKey(slug: string): string {
  ticketCounter += 1;
  const prefix = slug.split("-")[0]?.toUpperCase().slice(0, 5) || "TF";
  return `${prefix}-${ticketCounter}`;
}

function buildInitialColumns(boardColumns: ApiBoardColumn[]): ColumnData[] {
  return boardColumns
    .sort((a, b) => a.position - b.position)
    .map((col) => ({
      id: col.id,
      name: col.name,
      tickets: [],
    }));
}

export function BoardView({ projectSlug, boardColumns }: BoardViewProps) {
  const [columns, setColumns] = useState<ColumnData[]>(() =>
    buildInitialColumns(boardColumns)
  );

  const onDragEnd = useCallback((result: DropResult) => {
    const { source, destination } = result;
    if (!destination) return;
    if (
      source.droppableId === destination.droppableId &&
      source.index === destination.index
    )
      return;

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
  }, []);

  const handleCreateTicket = useCallback(
    (columnId: string, title: string) => {
      const types: TicketData["type"][] = ["task", "story", "bug"];
      const today = new Date();
      const dueDate = new Date(today);
      dueDate.setDate(today.getDate() + Math.floor(Math.random() * 14) + 1);
      const formattedDate = dueDate.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      });

      const newTicket: TicketData = {
        id: `ticket-${Date.now()}-${Math.random()}`,
        key: generateTicketKey(projectSlug),
        title,
        type: types[Math.floor(Math.random() * types.length)],
        dueDate: formattedDate,
      };

      setColumns((prev) =>
        prev.map((col) =>
          col.id === columnId
            ? { ...col, tickets: [...col.tickets, newTicket] }
            : col
        )
      );
    },
    [projectSlug]
  );

  return (
    <DragDropContext onDragEnd={onDragEnd}>
      <div className="flex h-full gap-3">
        {columns.map((column, idx) => (
          <BoardColumn
            key={column.id}
            column={column}
            index={idx}
            isLast={idx === columns.length - 1}
            onCreateTicket={handleCreateTicket}
          />
        ))}
      </div>
    </DragDropContext>
  );
}