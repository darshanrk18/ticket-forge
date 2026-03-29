"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Nav } from "@/components/shared/nav";
import { useAuth } from "@/lib/auth-context";

export default function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, isLoading, logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.push("/signin");
    }
  }, [user, isLoading, router]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (!user) return null;

  return (
    <>
      <Nav showAuth={false}>
        <span className="text-sm text-muted-foreground">
          {user.first_name} {user.last_name}
        </span>
        <Button variant="ghost" size="sm" onClick={logout}>
          <LogOut className="mr-1.5 size-3.5" />
          Logout
        </Button>
      </Nav>
      {children}
    </>
  );
}