"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import {
  AlertTriangle,
  Bookmark,
  Calendar as CalendarIcon,
  CheckSquare,
  ChevronDown,
  Loader2,
  Tag,
  Trash2,
  User,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { useAuth } from "@/lib/auth-context";
import {
  updateTicket,
  deleteTicket as apiDeleteTicket,
  type TicketResponse,
  type ProjectMember,
} from "@/lib/api";

interface TicketDetailModalProps {
  ticket: TicketResponse | null;
  projectSlug: string;
  members: ProjectMember[];
  open: boolean;
  onClose: () => void;
  onUpdated: (ticket: TicketResponse) => void;
  onDeleted: (ticketKey: string) => void;
}

const priorityOptions = [
  { value: "critical", label: "Critical", color: "bg-red-500" },
  { value: "high", label: "High", color: "bg-orange-500" },
  { value: "medium", label: "Medium", color: "bg-yellow-500" },
  { value: "low", label: "Low", color: "bg-blue-400" },
];

const typeOptions = [
  { value: "task", label: "Task", icon: CheckSquare, color: "text-blue-500" },
  { value: "story", label: "Story", icon: Bookmark, color: "text-green-500" },
  { value: "bug", label: "Bug", icon: AlertTriangle, color: "text-red-500" },
];

const COMMON_LABELS = [
  "frontend",
  "backend",
  "design",
  "docs",
  "infrastructure",
  "testing",
  "security",
  "performance",
];

export function TicketDetailModal({
  ticket,
  projectSlug,
  members,
  open,
  onClose,
  onUpdated,
  onDeleted,
}: TicketDetailModalProps) {
  const { token } = useAuth();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("medium");
  const [type, setType] = useState("task");
  const [assigneeId, setAssigneeId] = useState<string | null>(null);
  const [dueDate, setDueDate] = useState("");
  const [labels, setLabels] = useState<string[]>([]);
  const [newLabel, setNewLabel] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showLabelInput, setShowLabelInput] = useState(false);
  const titleRef = useRef<HTMLInputElement>(null);

  // Sync state when ticket changes
  useEffect(() => {
    if (ticket) {
      setTitle(ticket.title);
      setDescription(ticket.description || "");
      setPriority(ticket.priority);
      setType(ticket.type);
      setAssigneeId(ticket.assignee?.id || null);
      setDueDate(ticket.due_date || "");
      setLabels(ticket.labels || []);
    }
  }, [ticket]);

  const handleSave = useCallback(async () => {
    if (!token || !ticket) return;
    setIsSaving(true);

    const { data, error } = await updateTicket(
      token,
      projectSlug,
      ticket.ticket_key,
      {
        title: title.trim(),
        description: description.trim() || undefined,
        priority,
        type,
        assignee_id: assigneeId,
        due_date: dueDate || undefined,
        labels,
      }
    );

    setIsSaving(false);

    if (error) {
      toast.error(error);
      return;
    }

    if (data) {
      toast.success("Ticket updated");
      onUpdated(data);
      onClose();
    }
  }, [
    token,
    ticket,
    projectSlug,
    title,
    description,
    priority,
    type,
    assigneeId,
    dueDate,
    labels,
    onUpdated,
    onClose,
  ]);

  const handleDelete = useCallback(async () => {
    if (!token || !ticket) return;
    const confirmed = window.confirm(
      `Delete ${ticket.ticket_key}? This cannot be undone.`
    );
    if (!confirmed) return;

    setIsDeleting(true);
    const { error } = await apiDeleteTicket(
      token,
      projectSlug,
      ticket.ticket_key
    );
    setIsDeleting(false);

    if (error) {
      toast.error(error);
      return;
    }

    toast.success("Ticket deleted");
    onDeleted(ticket.ticket_key);
    onClose();
  }, [token, ticket, projectSlug, onDeleted, onClose]);

  function addLabel(label: string) {
    const trimmed = label.trim().toLowerCase();
    if (trimmed && !labels.includes(trimmed)) {
      setLabels([...labels, trimmed]);
    }
    setNewLabel("");
    setShowLabelInput(false);
  }

  function removeLabel(label: string) {
    setLabels(labels.filter((l) => l !== label));
  }

  if (!ticket) return null;

  const currentType = typeOptions.find((t) => t.value === type);
  const TypeIcon = currentType?.icon || CheckSquare;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto p-0">
        {/* Header */}
        <DialogHeader className="border-b px-6 py-4">
          <div className="flex items-center gap-2">
            <TypeIcon
              className={`size-4 ${currentType?.color || "text-blue-500"}`}
            />
            <span className="text-sm font-medium text-muted-foreground">
              {ticket.ticket_key}
            </span>
          </div>
          <DialogTitle className="sr-only">
            Edit {ticket.ticket_key}
          </DialogTitle>
        </DialogHeader>

        <div className="grid gap-0 md:grid-cols-[1fr,240px]">
          {/* Left: main fields */}
          <div className="space-y-4 p-6">
            {/* Title */}
            <div>
              <Input
                ref={titleRef}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="border-none px-0 text-lg font-semibold shadow-none focus-visible:ring-0"
                placeholder="Ticket title"
              />
            </div>

            {/* Description */}
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">
                Description
              </Label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Add a description..."
                className="min-h-[120px] w-full resize-none rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            {/* Labels */}
            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground">Labels</Label>
              <div className="flex flex-wrap gap-1.5">
                {labels.map((label) => (
                  <Badge
                    key={label}
                    variant="secondary"
                    className="gap-1 pl-2 pr-1 text-xs"
                  >
                    {label}
                    <button
                      type="button"
                      onClick={() => removeLabel(label)}
                      className="rounded-full p-0.5 hover:bg-muted"
                    >
                      <X className="size-2.5" />
                    </button>
                  </Badge>
                ))}

                {showLabelInput ? (
                  <div className="flex items-center gap-1">
                    <Input
                      value={newLabel}
                      onChange={(e) => setNewLabel(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") addLabel(newLabel);
                        if (e.key === "Escape") {
                          setShowLabelInput(false);
                          setNewLabel("");
                        }
                      }}
                      placeholder="Label name"
                      className="h-6 w-28 text-xs"
                      autoFocus
                    />
                  </div>
                ) : (
                  <button
                    onClick={() => setShowLabelInput(true)}
                    className="flex items-center gap-0.5 rounded-md border border-dashed px-2 py-0.5 text-xs text-muted-foreground hover:bg-accent"
                  >
                    <Tag className="size-3" />
                    Add
                  </button>
                )}
              </div>

              {/* Quick label suggestions */}
              {showLabelInput && (
                <div className="flex flex-wrap gap-1">
                  {COMMON_LABELS.filter((l) => !labels.includes(l))
                    .slice(0, 6)
                    .map((label) => (
                      <button
                        key={label}
                        onClick={() => addLabel(label)}
                        className="rounded border px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-accent"
                      >
                        {label}
                      </button>
                    ))}
                </div>
              )}
            </div>
          </div>

          {/* Right: sidebar fields */}
          <div className="space-y-4 border-l bg-muted/20 p-4">
            {/* Assignee */}
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Assignee</Label>
              <Select
                value={assigneeId || "unassigned"}
                onValueChange={(v) =>
                  setAssigneeId(v === "unassigned" ? null : v)
                }
              >
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue placeholder="Unassigned" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="unassigned">
                    <div className="flex items-center gap-2">
                      <User className="size-3 text-muted-foreground" />
                      <span>Unassigned</span>
                    </div>
                  </SelectItem>
                  {members.map((member) => (
                    <SelectItem key={member.user_id} value={member.user_id}>
                      <div className="flex items-center gap-2">
                        <div className="flex size-4 items-center justify-center rounded-full bg-primary text-[8px] font-semibold text-primary-foreground">
                          {member.first_name[0]}
                          {member.last_name[0]}
                        </div>
                        <span>
                          {member.first_name} {member.last_name}
                        </span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Priority */}
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Priority</Label>
              <Select value={priority} onValueChange={setPriority}>
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {priorityOptions.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      <div className="flex items-center gap-2">
                        <span
                          className={`size-2 rounded-full ${opt.color}`}
                        />
                        <span>{opt.label}</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Type */}
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Type</Label>
              <Select value={type} onValueChange={setType}>
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {typeOptions.map((opt) => {
                    const Icon = opt.icon;
                    return (
                      <SelectItem key={opt.value} value={opt.value}>
                        <div className="flex items-center gap-2">
                          <Icon className={`size-3.5 ${opt.color}`} />
                          <span>{opt.label}</span>
                        </div>
                      </SelectItem>
                    );
                  })}
                </SelectContent>
              </Select>
            </div>

            {/* Due date */}
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Due date</Label>
              <div className="relative">
                <CalendarIcon className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  type="date"
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                  className="h-8 pl-7 text-xs"
                />
              </div>
              {dueDate && (
                <button
                  onClick={() => setDueDate("")}
                  className="text-[10px] text-muted-foreground hover:text-foreground"
                >
                  Clear date
                </button>
              )}
            </div>

            <Separator />

            {/* Meta */}
            <div className="space-y-1 text-[11px] text-muted-foreground">
              <p>
                Created{" "}
                {new Date(ticket.created_at).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                })}
              </p>
              <p>
                Updated{" "}
                {new Date(ticket.updated_at).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                })}
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t px-6 py-3">
          <Button
            variant="ghost"
            size="sm"
            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
            onClick={handleDelete}
            disabled={isDeleting}
          >
            {isDeleting ? (
              <Loader2 className="mr-1.5 size-3.5 animate-spin" />
            ) : (
              <Trash2 className="mr-1.5 size-3.5" />
            )}
            Delete
          </Button>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={onClose}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleSave}
              disabled={isSaving || !title.trim()}
            >
              {isSaving && (
                <Loader2 className="mr-1.5 size-3.5 animate-spin" />
              )}
              Save changes
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}