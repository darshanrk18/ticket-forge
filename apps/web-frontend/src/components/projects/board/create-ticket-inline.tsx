"use client";

import { useState, useRef, useEffect } from "react";
import { Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";

interface CreateTicketInlineProps {
  columnId: string;
  onCreateTicket: (columnId: string, title: string) => void;
}

export function CreateTicketInline({
  columnId,
  onCreateTicket,
}: CreateTicketInlineProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [title, setTitle] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  function handleSubmit() {
    if (!title.trim()) return;
    onCreateTicket(columnId, title.trim());
    setTitle("");
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
    if (e.key === "Escape") {
      setIsOpen(false);
      setTitle("");
    }
  }

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="flex w-full items-center gap-1 rounded-md px-2 py-1.5 text-[13px] text-muted-foreground transition-colors hover:bg-accent"
      >
        <Plus className="size-4" />
        Create
      </button>
    );
  }

  return (
    <div className="space-y-1.5">
      <div className="rounded-md border bg-card p-2.5 shadow-sm">
        <textarea
          ref={inputRef}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="What needs to be done?"
          className="w-full resize-none bg-transparent text-[13px] placeholder:text-muted-foreground/60 focus:outline-none"
          rows={2}
        />
      </div>
      <div className="flex items-center gap-1.5">
        <Button
          size="sm"
          onClick={handleSubmit}
          disabled={!title.trim()}
          className="h-7 text-xs"
        >
          Create
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-7 px-2"
          onClick={() => {
            setIsOpen(false);
            setTitle("");
          }}
        >
          <X className="size-3.5" />
        </Button>
      </div>
    </div>
  );
}