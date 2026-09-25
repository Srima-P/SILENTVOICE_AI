/**
 * useAccessibility — convenience hook that reads accessibility preferences
 * and returns a className helper.
 */

import { useApp } from "@/contexts/AppContext";

export function useAccessibility() {
  const { state, setAccessibility } = useApp();
  const { accessibility } = state;

  /** Returns the CSS class string that applies accessibility overrides. */
  function a11yClass(base = ""): string {
    const classes: string[] = [base];
    if (accessibility.enabled) {
      classes.push("a11y-mode");
      if (accessibility.largeText) classes.push("a11y-large-text");
      if (accessibility.highContrast) classes.push("a11y-high-contrast");
      if (accessibility.reducedMotion) classes.push("a11y-reduced-motion");
      if (accessibility.strongFocus) classes.push("a11y-strong-focus");
    }
    return classes.filter(Boolean).join(" ");
  }

  function toggle() {
    const next = !accessibility.enabled;
    setAccessibility({
      enabled: next,
      largeText: next,
      strongFocus: next,
    });
  }

  return { accessibility, setAccessibility, a11yClass, toggle };
}
