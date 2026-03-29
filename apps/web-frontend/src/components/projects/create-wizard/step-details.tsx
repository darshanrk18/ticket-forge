"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface StepDetailsProps {
  name: string;
  description: string;
  onNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  errors?: { name?: string; description?: string };
}

export function StepDetails({
  name,
  description,
  onNameChange,
  onDescriptionChange,
  errors,
}: StepDetailsProps) {
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="project-name">Project name</Label>
        <Input
          id="project-name"
          placeholder="e.g. TicketForge Core"
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          autoFocus
        />
        {errors?.name && (
          <p className="text-sm text-destructive">{errors.name}</p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="project-description">
          Description{" "}
          <span className="text-muted-foreground">(optional)</span>
        </Label>
        <textarea
          id="project-description"
          className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          placeholder="What's this project about?"
          value={description}
          onChange={(e) => onDescriptionChange(e.target.value)}
          maxLength={500}
        />
        {errors?.description && (
          <p className="text-sm text-destructive">{errors.description}</p>
        )}
      </div>
    </div>
  );
}