"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { X } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { searchUsers, type UserSearchResult } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

interface MemberSearchProps {
  selected: UserSearchResult[];
  onSelect: (user: UserSearchResult) => void;
  onRemove: (userId: string) => void;
  projectSlug?: string;
}

export function MemberSearch({
  selected,
  onSelect,
  onRemove,
  projectSlug,
}: MemberSearchProps) {
  const { token } = useAuth();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<UserSearchResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  const doSearch = useCallback(
    async (q: string) => {
      if (!token || q.length < 2) {
        setResults([]);
        return;
      }
      setIsLoading(true);
      const { data } = await searchUsers(token, q, projectSlug);
      if (data) {
        // Filter out already-selected users
        const selectedIds = new Set(selected.map((u) => u.id));
        setResults(data.filter((u) => !selectedIds.has(u.id)));
      }
      setIsLoading(false);
    },
    [token, projectSlug, selected]
  );

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(query), 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, doSearch]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <div className="space-y-3">
      {/* Selected members */}
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {selected.map((user) => (
            <Badge
              key={user.id}
              variant="secondary"
              className="gap-1 pl-2 pr-1"
            >
              <span>
                {user.first_name} {user.last_name}
              </span>
              <button
                type="button"
                onClick={() => onRemove(user.id)}
                className="ml-0.5 rounded-full p-0.5 hover:bg-muted"
              >
                <X className="size-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}

      {/* Search input */}
      <div ref={containerRef} className="relative">
        <Input
          placeholder="Search by email..."
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
          }}
          onFocus={() => {
            if (query.length >= 2) setIsOpen(true);
          }}
        />

        {/* Dropdown */}
        {isOpen && query.length >= 2 && (
          <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-md">
            <ScrollArea className="max-h-48">
              {isLoading ? (
                <p className="px-3 py-2 text-sm text-muted-foreground">
                  Searching...
                </p>
              ) : results.length === 0 ? (
                <p className="px-3 py-2 text-sm text-muted-foreground">
                  No users found
                </p>
              ) : (
                results.map((user) => (
                  <button
                    key={user.id}
                    type="button"
                    className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-accent"
                    onClick={() => {
                      onSelect(user);
                      setQuery("");
                      setIsOpen(false);
                    }}
                  >
                    <div className="flex size-7 items-center justify-center rounded-full bg-muted text-xs font-medium">
                      {user.first_name[0]}
                      {user.last_name[0]}
                    </div>
                    <div>
                      <p className="font-medium">
                        {user.first_name} {user.last_name}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {user.email}
                      </p>
                    </div>
                  </button>
                ))
              )}
            </ScrollArea>
          </div>
        )}
      </div>
    </div>
  );
}