"use client";

import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Nav } from "@/components/shared/nav";
import { siteConfig, layout } from "@/lib/design";
import { cn } from "@/lib/utils";

export default function DashboardPage() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen">
      <Nav showAuth={false}>
        <span className="text-sm text-muted-foreground">
          @{user?.username}
        </span>
        <Button variant="outline" size="sm" onClick={logout}>
          Sign out
        </Button>
      </Nav>

      <main className={cn("mx-auto", layout.maxWidth, layout.pagePadding, layout.sectionGap)}>
        <div className="space-y-2">
          <h1 className="text-3xl font-bold tracking-tight">
            Welcome back, {user?.first_name}
          </h1>
          <p className="text-muted-foreground">
            Here&apos;s an overview of your workspace.
          </p>
        </div>

        <div className="mt-12 flex flex-col items-center justify-center rounded-lg border border-dashed py-16">
          <p className="text-sm text-muted-foreground">
            No boards yet. Board creation coming soon.
          </p>
        </div>
      </main>
    </div>
  );
}