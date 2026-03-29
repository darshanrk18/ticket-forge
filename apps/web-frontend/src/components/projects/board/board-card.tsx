"use client";

import { Draggable } from "@hello-pangea/dnd";
import { Calendar, CheckSquare, Bookmark, User } from "lucide-react";

export interface TicketData {
  id: string;
  key: string;
  title: string;
  type: "task" | "story" | "bug";
  assignee?: {
    initials: string;
    name: string;
    color: string;
  };
  dueDate?: string;
}

interface BoardCardProps {
  ticket: TicketData;
  index: number;
}

const typeIcon: Record<string, { icon: typeof CheckSquare; color: string }> = {
  task: { icon: CheckSquare, color: "text-blue-500" },
  story: { icon: Bookmark, color: "text-green-500" },
  bug: { icon: Bookmark, color: "text-red-500" },
};

export function BoardCard({ ticket, index }: BoardCardProps) {
  const TypeIcon = typeIcon[ticket.type]?.icon || CheckSquare;
  const typeColor = typeIcon[ticket.type]?.color || "text-blue-500";

  return (
    <Draggable draggableId={ticket.id} index={index}>
      {(provided, snapshot) => (
        <div
          ref={provided.innerRef}
          {...provided.draggableProps}
          {...provided.dragHandleProps}
          className={`group cursor-pointer rounded-md border bg-card px-3 pb-2.5 pt-3 shadow-sm transition-all hover:bg-accent/40 ${
            snapshot.isDragging
              ? "rotate-[1.5deg] shadow-xl ring-2 ring-primary/20"
              : ""
          }`}
        >
          {/* Title */}
          <p className="text-[13px] font-medium leading-snug text-foreground">
            {ticket.title}
          </p>

          {/* Due date */}
          {ticket.dueDate && (
            <div className="mt-2 inline-flex items-center gap-1 rounded bg-muted/60 px-1.5 py-0.5">
              <Calendar className="size-3 text-muted-foreground" />
              <span className="text-[11px] text-muted-foreground">
                {ticket.dueDate}
              </span>
            </div>
          )}

          {/* Footer: type icon + key + assignee */}
          <div className="mt-2.5 flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <TypeIcon className={`size-3.5 ${typeColor}`} />
              <span className="text-[11px] font-medium text-muted-foreground">
                {ticket.key}
              </span>
            </div>

            {ticket.assignee ? (
              <div
                className="flex size-6 items-center justify-center rounded-full text-[10px] font-semibold text-white"
                style={{ backgroundColor: ticket.assignee.color }}
                title={ticket.assignee.name}
              >
                {ticket.assignee.initials}
              </div>
            ) : (
              <div className="flex size-6 items-center justify-center rounded-full border border-dashed border-muted-foreground/30">
                <User className="size-3 text-muted-foreground/50" />
              </div>
            )}
          </div>
        </div>
      )}
    </Draggable>
  );
}