"use client";

import { Draggable } from "@hello-pangea/dnd";
import {
  AlertTriangle,
  Bookmark,
  Calendar,
  CheckSquare,
  User,
} from "lucide-react";

export interface TicketData {
  id: string;
  key: string;
  title: string;
  type: "task" | "story" | "bug";
  priority: "low" | "medium" | "high" | "critical";
  labels: string[];
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
  onClick: (ticketId: string) => void;
}

const typeIcon: Record<string, { icon: typeof CheckSquare; color: string }> = {
  task: { icon: CheckSquare, color: "text-blue-500" },
  story: { icon: Bookmark, color: "text-green-500" },
  bug: { icon: AlertTriangle, color: "text-red-500" },
};

const labelColors: Record<string, string> = {
  frontend:
    "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300",
  backend: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  design: "bg-pink-100 text-pink-700 dark:bg-pink-950 dark:text-pink-300",
  docs: "bg-teal-100 text-teal-700 dark:bg-teal-950 dark:text-teal-300",
  bug: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
  infrastructure:
    "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  testing:
    "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300",
  security:
    "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300",
  performance:
    "bg-cyan-100 text-cyan-700 dark:bg-cyan-950 dark:text-cyan-300",
};

function getLabelColor(label: string) {
  return (
    labelColors[label.toLowerCase()] ||
    "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400"
  );
}

export function BoardCard({ ticket, index, onClick }: BoardCardProps) {
  const TypeIcon = typeIcon[ticket.type]?.icon || CheckSquare;
  const typeColor = typeIcon[ticket.type]?.color || "text-blue-500";

  return (
    <Draggable draggableId={ticket.id} index={index}>
      {(provided, snapshot) => (
        <div
          ref={provided.innerRef}
          {...provided.draggableProps}
          {...provided.dragHandleProps}
          onClick={() => onClick(ticket.id)}
          className={`group cursor-pointer rounded-md border bg-card px-3 pb-2.5 pt-3 shadow-sm transition-all hover:bg-accent/40 ${
            snapshot.isDragging
              ? "rotate-[1.5deg] shadow-xl ring-2 ring-primary/20"
              : ""
          }`}
        >
          {/* Labels */}
          {ticket.labels.length > 0 && (
            <div className="mb-1.5 flex flex-wrap gap-1">
              {ticket.labels.map((label) => (
                <span
                  key={label}
                  className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${getLabelColor(label)}`}
                >
                  {label}
                </span>
              ))}
            </div>
          )}

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