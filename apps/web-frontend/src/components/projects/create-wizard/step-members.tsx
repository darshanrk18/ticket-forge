"use client";

import { Label } from "@/components/ui/label";
import { MemberSearch } from "@/components/projects/member-search";
import type { UserSearchResult } from "@/lib/api";

interface StepMembersProps {
  selected: UserSearchResult[];
  onSelect: (user: UserSearchResult) => void;
  onRemove: (userId: string) => void;
}

export function StepMembers({
  selected,
  onSelect,
  onRemove,
}: StepMembersProps) {
  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <Label>Invite team members</Label>
        <p className="text-sm text-muted-foreground">
          Search by email to add registered users. You can skip this and invite
          people later.
        </p>
      </div>

      <MemberSearch
        selected={selected}
        onSelect={onSelect}
        onRemove={onRemove}
      />
    </div>
  );
}