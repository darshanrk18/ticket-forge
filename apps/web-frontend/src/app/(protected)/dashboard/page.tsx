"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ProjectCard } from "@/components/projects/project-card";
import { useAuth } from "@/lib/auth-context";
import { listProjects, type ProjectListItem } from "@/lib/api";

export default function DashboardPage() {
  const { user, token } = useAuth();
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function load() {
      if (!token) return;
      const { data } = await listProjects(token);
      if (data) setProjects(data);
      setIsLoading(false);
    }
    load();
  }, [token]);

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Projects</h1>
          <p className="text-sm text-muted-foreground">
            Welcome back, {user?.first_name}
          </p>
        </div>
        <Link href="/projects/new">
          <Button>
            <Plus className="mr-1.5 size-4" />
            New project
          </Button>
        </Link>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="size-6 animate-spin text-muted-foreground" />
        </div>
      ) : projects.length === 0 ? (
        <div className="mt-12 flex flex-col items-center justify-center rounded-lg border border-dashed py-16">
          <p className="mb-4 text-sm text-muted-foreground">
            No projects yet. Create your first one.
          </p>
          <Link href="/projects/new">
            <Button>
              <Plus className="mr-1.5 size-4" />
              Create project
            </Button>
          </Link>
        </div>
      ) : (
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      )}
    </div>
  );
}