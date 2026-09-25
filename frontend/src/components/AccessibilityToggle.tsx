/**
 * AccessibilityToggle — button that toggles accessibility mode.
 * Visual state changes are handled by the a11y CSS classes in index.css.
 */

import { Accessibility } from "lucide-react";
import { useAccessibility } from "@/hooks/useAccessibility";

export function AccessibilityToggle() {
  const { accessibility, toggle } = useAccessibility();
  const active = accessibility.enabled;

  return (
    <button
      onClick={toggle}
      title={active ? "Disable accessibility mode" : "Enable accessibility mode"}
      aria-label={
        active ? "Disable accessibility mode" : "Enable accessibility mode"
      }
      aria-pressed={active}
      className={[
        "flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium transition-colors",
        active
          ? "bg-text-accent/20 text-text-accent border border-text-accent/30"
          : "text-text-secondary hover:text-text-primary hover:bg-surface-3",
      ].join(" ")}
    >
      <Accessibility size={14} aria-hidden="true" />
      <span className="hidden sm:inline">
        {active ? "A11y On" : "A11y"}
      </span>
    </button>
  );
}
