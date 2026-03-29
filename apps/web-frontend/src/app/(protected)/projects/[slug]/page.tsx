"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Filter,
  Loader2,
  Search,
  Settings,
  User,
} from "lucide-react";
import { toast } from "sonner";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { BoardView } from "@/components/projects/board/board-view";
import { useAuth } from "@/lib/auth-context";
import { getProject, type ProjectResponse } from "@/lib/api";

export default function ProjectDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { token, user } = useAuth();
  const slug = params.slug as string;

  const [project, setProject] = useState<ProjectResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function load() {
      if (!token) return;
      const { data, error } = await getProject(token, slug);
      if (error) {
        toast.error(error);
        router.push("/dashboard");
        return;
      }
      if (data) setProject(data);
      setIsLoading(false);
    }
    load();
  }, [token, slug, router]);

  const myRole = project?.members.find(
    (m) => m.user_id === user?.id
  )?.role;
  const canManage = myRole === "owner" || myRole === "admin";

  if (isLoading) {
    return (
      <div className="flex h-[calc(100vh-4rem)] items-center justify-center">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!project) return null;

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col overflow-hidden">
      {/* Project sub-header */}
      <div className="border-b px-6 py-2.5">
        {/* Breadcrumb */}
        <div className="flex items-center gap-1.5 text-[13px]">
          <Link
            href="/dashboard"
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            Projects
          </Link>
          <span className="text-muted-foreground/50">/</span>
          <span className="font-medium">{project.name}</span>
        </div>
      </div>

      {/* Board toolbar */}
      <div className="flex items-center justify-between border-b px-6 py-2">
        <div className="flex items-center gap-3">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search board"
              className="h-8 w-48 pl-8 text-[13px]"
            />
          </div>

          {/* Member avatars filter */}
          <div className="flex items-center">
            <div className="flex -space-x-1.5">
              {project.members.slice(0, 4).map((member, idx) => {
                const colors = [
                  "#6366f1",
                  "#06b6d4",
                  "#10b981",
                  "#f59e0b",
                  "#ef4444",
                ];
                return (
                  <button
                    key={member.id}
                    className="flex size-7 items-center justify-center rounded-full border-2 border-background text-[10px] font-semibold text-white transition-transform hover:scale-110 hover:z-10"
                    style={{ backgroundColor: colors[idx % colors.length] }}
                    title={`${member.first_name} ${member.last_name}`}
                  >
                    {member.first_name[0]}
                    {member.last_name[0]}
                  </button>
                );
              })}
              {project.members.length > 4 && (
                <div className="flex size-7 items-center justify-center rounded-full border-2 border-background bg-muted text-[10px] font-medium text-muted-foreground">
                  +{project.members.length - 4}
                </div>
              )}
            </div>
          </div>

          <Separator orientation="vertical" className="h-5" />

          {/* Filter */}
          <Button variant="ghost" size="sm" className="h-8 text-[13px]">
            <Filter className="mr-1.5 size-3.5" />
            Filter
          </Button>
        </div>

        {/* Right side */}
        <div className="flex items-center gap-2">
          {canManage && (
            <Link href={`/projects/${slug}/settings`}>
              <Button variant="ghost" size="sm" className="h-8 text-[13px]">
                <Settings className="mr-1.5 size-3.5" />
                Settings
              </Button>
            </Link>
          )}
        </div>
      </div>

      {/* Board area */}
      <div className="flex-1 overflow-x-auto overflow-y-hidden bg-background p-5">
        <BoardView
          projectSlug={slug}
          boardColumns={project.board_columns}
        />
      </div>
    </div>
  );
}