"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Nav } from "@/components/shared/nav";
import { siteConfig } from "@/lib/design";
import { useAuth } from "@/lib/auth-context";

export default function Home() {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && user) {
      router.replace("/dashboard");
    }
  }, [user, isLoading, router]);

  if (isLoading || user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <Nav />

      <main className="flex flex-1 flex-col items-center justify-center px-6 text-center">
        <div className="mx-auto max-w-3xl space-y-8">
          <div className="space-y-4">
            <div className="inline-block rounded-full border px-4 py-1.5 text-sm text-muted-foreground">
              AI-powered ticket assignment
            </div>
            <h1 className="text-4xl font-bold tracking-tight sm:text-5xl md:text-6xl">
              {siteConfig.tagline.split(".")[0]}.
              <br />
              <span className="text-muted-foreground">
                {siteConfig.tagline.split(".")[1]?.trim()}.
              </span>
            </h1>
            <p className="mx-auto max-w-xl text-lg text-muted-foreground">
              {siteConfig.subtitle}
            </p>
          </div>

          <div className="flex items-center justify-center gap-4">
            <Link href="/signup">
              <Button size="lg">Get started for free</Button>
            </Link>
            <Link href="/signin">
              <Button variant="outline" size="lg">
                Sign in
              </Button>
            </Link>
          </div>

          <div className="mx-auto grid max-w-2xl gap-6 pt-12 text-left sm:grid-cols-3">
            <div className="space-y-2 rounded-lg border p-4">
              <h3 className="font-semibold">Skill matching</h3>
              <p className="text-sm text-muted-foreground">
                Cosine similarity between ticket embeddings and engineer profiles
                finds the best match instantly.
              </p>
            </div>
            <div className="space-y-2 rounded-lg border p-4">
              <h3 className="font-semibold">Experience decay</h3>
              <p className="text-sm text-muted-foreground">
                Engineer profiles evolve with every closed ticket, keeping
                recommendations fresh and accurate.
              </p>
            </div>
            <div className="space-y-2 rounded-lg border p-4">
              <h3 className="font-semibold">Cold start ready</h3>
              <p className="text-sm text-muted-foreground">
                Upload a resume and get meaningful recommendations before an
                engineer has any ticket history.
              </p>
            </div>
          </div>
        </div>
      </main>

      <footer className="border-t py-6 text-center text-sm text-muted-foreground">
        Built by the {siteConfig.name} team.
      </footer>
    </div>
  );
}