"use client";

import { Droppable } from "@hello-pangea/dnd";
import { Sparkles } from "lucide-react";

import { BoardCard, type TicketData } from "./board-card";
import { CreateTicketInline } from "./create-ticket-inline";

export interface ColumnData {
  id: string;
  name: string;
  tickets: TicketData[];
}

interface BoardColumnProps {
  column: ColumnData;
  isLast: boolean;
  onCreateTicket: (columnId: string, title: string) => void;
  onTicketClick: (ticketId: string) => void;
}

export function BoardColumn({
  column,
  isLast,
  onCreateTicket,
  onTicketClick,
}: BoardColumnProps) {
  return (
    <div className="flex w-[272px] shrink-0 flex-col">
      {/* Column header */}
      <div className="mb-2 flex items-center gap-2 px-1">
        <h3 className="text-[11.5px] font-bold uppercase tracking-widest text-muted-foreground">
          {column.name}
        </h3>
        {column.tickets.length > 0 && (
          <span className="text-[11.5px] font-semibold text-muted-foreground/60">
            {column.tickets.length}
          </span>
        )}
        {isLast && (
          <Sparkles className="size-3.5 text-muted-foreground/40" />
        )}
      </div>

      {/* Droppable card area */}
      <Droppable droppableId={column.id}>
        {(provided, snapshot) => (
          <div
            ref={provided.innerRef}
            {...provided.droppableProps}
            className={`flex min-h-[120px] flex-1 flex-col gap-1.5 rounded-lg px-0.5 py-1 transition-colors ${
              snapshot.isDraggingOver
                ? "bg-primary/[0.04] ring-1 ring-primary/10"
                : ""
            }`}
          >
            {column.tickets.map((ticket, idx) => (
              <BoardCard
                key={ticket.id}
                ticket={ticket}
                index={idx}
                onClick={onTicketClick}
              />
            ))}
            {provided.placeholder}

            {column.tickets.length === 0 && !snapshot.isDraggingOver && (
              <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-muted-foreground/15 py-8">
                <p className="text-xs text-muted-foreground/40">
                  Drag tickets here
                </p>
              </div>
            )}
          </div>
        )}
      </Droppable>

      {/* Create ticket */}
      <div className="mt-1 px-0.5">
        <CreateTicketInline
          columnId={column.id}
          onCreateTicket={onCreateTicket}
        />
      </div>
    </div>
  );
}
