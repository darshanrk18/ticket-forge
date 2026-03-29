"use client";

import Link from "next/link";
import { Users } from "lucide-react";

import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { ProjectListItem } from "@/lib/api";

interface ProjectCardProps {
  project: ProjectListItem;
}

export function ProjectCard({ project }: ProjectCardProps) {
  return (
    <Link href={`/projects/${project.slug}`}>
      <Card className="transition-colors hover:border-foreground/20">
        <CardHeader>
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <CardTitle className="text-base">{project.name}</CardTitle>
              {project.description && (
                <CardDescription className="line-clamp-2">
                  {project.description}
                </CardDescription>
              )}
            </div>
            <Badge variant="secondary" className="capitalize">
              {project.role}
            </Badge>
          </div>
          <div className="flex items-center gap-1.5 pt-2 text-xs text-muted-foreground">
            <Users className="size-3.5" />
            <span>
              {project.member_count}{" "}
              {project.member_count === 1 ? "member" : "members"}
            </span>
          </div>
        </CardHeader>
      </Card>
    </Link>
  );
}