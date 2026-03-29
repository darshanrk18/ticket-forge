import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/shared/logo";
import { ThemeToggle } from "@/components/shared/theme-toggle";
import { layout } from "@/lib/design";
import { cn } from "@/lib/utils";

interface NavProps {
  showAuth?: boolean;
  children?: React.ReactNode;
}

export function Nav({ showAuth = true, children }: NavProps) {
  return (
    <header className="border-b">
      <div
        className={cn(
          "mx-auto flex items-center justify-between",
          layout.navHeight,
          layout.maxWidth,
          layout.pagePadding
        )}
      >
        <Link href="/">
          <Logo />
        </Link>

        <div className="flex items-center gap-3">
          <ThemeToggle />
          {children ? (
            children
          ) : showAuth ? (
            <>
              <Link href="/signin">
                <Button variant="ghost" size="sm">
                  Sign in
                </Button>
              </Link>
              <Link href="/signup">
                <Button size="sm">Get started</Button>
              </Link>
            </>
          ) : null}
        </div>
      </div>
    </header>
  );
}