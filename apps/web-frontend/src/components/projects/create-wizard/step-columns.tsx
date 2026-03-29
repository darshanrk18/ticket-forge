"use client";

import { GripVertical, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const DEFAULT_COLUMNS = ["Backlog", "To Do", "In Progress", "In Review", "Done"];
const MAX_COLUMNS = 12;

interface StepColumnsProps {
  columns: string[];
  onChange: (columns: string[]) => void;
}

export function StepColumns({ columns, onChange }: StepColumnsProps) {
  function addColumn() {
    if (columns.length >= MAX_COLUMNS) return;
    onChange([...columns, ""]);
  }

  function removeColumn(index: number) {
    if (columns.length <= 1) return;
    onChange(columns.filter((_, i) => i !== index));
  }

  function updateColumn(index: number, value: string) {
    const updated = [...columns];
    updated[index] = value;
    onChange(updated);
  }

  function resetToDefaults() {
    onChange([...DEFAULT_COLUMNS]);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Label>Board columns</Label>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={resetToDefaults}
          className="text-xs"
        >
          Reset to defaults
        </Button>
      </div>

      <p className="text-sm text-muted-foreground">
        Set up the columns for your kanban board. You can always change these
        later.
      </p>

      <div className="space-y-2">
        {columns.map((col, index) => (
          <div key={index} className="flex items-center gap-2">
            <GripVertical className="size-4 shrink-0 text-muted-foreground" />
            <Input
              value={col}
              onChange={(e) => updateColumn(index, e.target.value)}
              placeholder={`Column ${index + 1}`}
              className="flex-1"
            />
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={() => removeColumn(index)}
              disabled={columns.length <= 1}
              className="shrink-0"
            >
              <Trash2 className="size-3.5" />
            </Button>
          </div>
        ))}
      </div>

      {columns.length < MAX_COLUMNS && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={addColumn}
          className="w-full"
        >
          <Plus className="mr-1.5 size-3.5" />
          Add column
        </Button>
      )}
    </div>
  );
}