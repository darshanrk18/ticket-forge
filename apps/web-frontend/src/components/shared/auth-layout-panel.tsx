import { Logo } from "@/components/shared/logo";
import { branding } from "@/lib/design";

export function AuthLayoutPanel() {
  return (
    <div className="relative hidden bg-primary lg:flex lg:flex-col lg:justify-between lg:p-10">
      <Logo variant="light" />
      <blockquote className="space-y-2">
        <p className="text-lg text-primary-foreground/80">
          &ldquo;{branding.testimonial.quote}&rdquo;
        </p>
        <footer className="text-sm text-primary-foreground/60">
          — {branding.testimonial.author}
        </footer>
      </blockquote>
    </div>
  );
}