import { cn } from "@/lib/utils";
import { siteConfig } from "@/lib/design";

interface LogoProps {
  variant?: "light" | "dark";
  className?: string;
}

export function Logo({ variant = "dark", className }: LogoProps) {
  const isLight = variant === "light";

  return (
    <span
      className={cn(
        "text-xl font-bold tracking-tight",
        isLight ? "text-white" : "text-foreground",
        className
      )}
    >
      {siteConfig.name}
    </span>
  );
}