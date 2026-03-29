"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import { StepDetails } from "./step-details";
import { StepColumns } from "./step-columns";
import { StepMembers } from "./step-members";

import { useAuth } from "@/lib/auth-context";
import { createProject, type UserSearchResult } from "@/lib/api";

const DEFAULT_COLUMNS = ["Backlog", "To Do", "In Progress", "In Review", "Done"];

const STEPS = [
  { title: "Project details", description: "Give your project a name" },
  { title: "Board columns", description: "Configure your kanban board" },
  { title: "Invite members", description: "Add your team" },
] as const;

export function WizardShell() {
  const router = useRouter();
  const { token } = useAuth();
  const [step, setStep] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Step 1 state
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [errors, setErrors] = useState<{ name?: string; description?: string }>(
    {}
  );

  // Step 2 state
  const [columns, setColumns] = useState<string[]>([...DEFAULT_COLUMNS]);

  // Step 3 state
  const [selectedMembers, setSelectedMembers] = useState<UserSearchResult[]>(
    []
  );

  function validateStep(): boolean {
    if (step === 0) {
      const newErrors: typeof errors = {};
      if (!name.trim()) newErrors.name = "Project name is required";
      if (name.length > 100)
        newErrors.name = "Project name must be at most 100 characters";
      if (description.length > 500)
        newErrors.description = "Description must be at most 500 characters";
      setErrors(newErrors);
      return Object.keys(newErrors).length === 0;
    }
    if (step === 1) {
      const nonEmpty = columns.filter((c) => c.trim());
      if (nonEmpty.length === 0) {
        toast.error("Add at least one board column");
        return false;
      }
      const names = nonEmpty.map((c) => c.trim().toLowerCase());
      if (new Set(names).size !== names.length) {
        toast.error("Column names must be unique");
        return false;
      }
      return true;
    }
    return true;
  }

  function nextStep() {
    if (!validateStep()) return;
    setStep((s) => Math.min(s + 1, STEPS.length - 1));
  }

  function prevStep() {
    setStep((s) => Math.max(s - 1, 0));
  }

  async function handleCreate() {
    if (!token) return;
    setIsSubmitting(true);

    const boardColumns = columns
      .filter((c) => c.trim())
      .map((c) => ({ name: c.trim() }));

    const { data, error } = await createProject(token, {
      name: name.trim(),
      description: description.trim() || undefined,
      board_columns: boardColumns,
      member_ids: selectedMembers.map((m) => m.id),
    });

    setIsSubmitting(false);

    if (error) {
      toast.error(error);
      return;
    }

    if (data) {
      toast.success("Project created!");
      router.push(`/projects/${data.slug}`);
    }
  }

  function handleSelectMember(user: UserSearchResult) {
    setSelectedMembers((prev) => [...prev, user]);
  }

  function handleRemoveMember(userId: string) {
    setSelectedMembers((prev) => prev.filter((u) => u.id !== userId));
  }

  const isLastStep = step === STEPS.length - 1;

  return (
    <Card className="mx-auto w-full max-w-lg">
      <CardHeader>
        <div className="flex items-center gap-2 pb-2">
          {STEPS.map((_, i) => (
            <div
              key={i}
              className={`h-1 flex-1 rounded-full transition-colors ${
                i <= step ? "bg-primary" : "bg-muted"
              }`}
            />
          ))}
        </div>
        <CardTitle>{STEPS[step].title}</CardTitle>
        <CardDescription>{STEPS[step].description}</CardDescription>
      </CardHeader>

      <CardContent>
        {step === 0 && (
          <StepDetails
            name={name}
            description={description}
            onNameChange={(v) => {
              setName(v);
              if (errors.name) setErrors((e) => ({ ...e, name: undefined }));
            }}
            onDescriptionChange={(v) => {
              setDescription(v);
              if (errors.description)
                setErrors((e) => ({ ...e, description: undefined }));
            }}
            errors={errors}
          />
        )}
        {step === 1 && <StepColumns columns={columns} onChange={setColumns} />}
        {step === 2 && (
          <StepMembers
            selected={selectedMembers}
            onSelect={handleSelectMember}
            onRemove={handleRemoveMember}
          />
        )}
      </CardContent>

      <CardFooter className="flex justify-between">
        <Button
          type="button"
          variant="ghost"
          onClick={step === 0 ? () => router.back() : prevStep}
        >
          <ArrowLeft className="mr-1.5 size-4" />
          {step === 0 ? "Cancel" : "Back"}
        </Button>

        {isLastStep ? (
          <Button onClick={handleCreate} disabled={isSubmitting}>
            {isSubmitting && <Loader2 className="mr-1.5 size-4 animate-spin" />}
            Create project
          </Button>
        ) : (
          <Button onClick={nextStep}>
            Next
            <ArrowRight className="ml-1.5 size-4" />
          </Button>
        )}
      </CardFooter>
    </Card>
  );
}