// Design tokens for Intelligent Forecast (OKLCH). Accent is a single tunable.
export const ACCENT = "#4f46e5";

export const C = {
  pageBg: "oklch(0.985 0.002 255)",
  surface: "#fff",
  border: "oklch(0.91 0.006 260)",
  borderSoft: "oklch(0.93 0.006 260)",
  hairline: "oklch(0.955 0.004 260)",
  headerBg: "oklch(0.98 0.003 260)",
  text: "oklch(0.22 0.014 262)",
  text2: "oklch(0.26 0.014 262)",
  muted: "oklch(0.55 0.012 260)",
  faint: "oklch(0.6 0.01 260)",
  cell: "oklch(0.42 0.012 260)",
  accentTint: "oklch(0.96 0.02 264)",
  accentTintSoft: "oklch(0.975 0.008 264)",
  accentPill: "oklch(0.95 0.03 264)",
  warning: "oklch(0.58 0.17 40)",
  critical: "oklch(0.55 0.17 25)",
  greenRail: "oklch(0.68 0.13 155)",
};

export const MONO = "'IBM Plex Mono', monospace";

export const SHADOW = {
  card: "0 1px 2px oklch(0.6 0.02 260 / 0.04)",
  popover: "0 12px 40px oklch(0.3 0.02 260 / 0.16)",
  drawer: "-16px 0 48px oklch(0.3 0.02 260 / 0.12)",
};

// Risk tier -> band bar + score-chip colors.
export function tierColors(risk) {
  if (risk >= 8)
    return { band: "oklch(0.58 0.2 25)", chipBg: "oklch(0.95 0.05 25)", chipFg: "oklch(0.45 0.17 25)" };
  if (risk >= 5)
    return { band: "oklch(0.72 0.17 55)", chipBg: "oklch(0.96 0.06 70)", chipFg: "oklch(0.5 0.13 55)" };
  if (risk >= 3)
    return { band: "oklch(0.83 0.14 95)", chipBg: "oklch(0.97 0.07 100)", chipFg: "oklch(0.52 0.09 95)" };
  return { band: "oklch(0.7 0.13 155)", chipBg: "oklch(0.95 0.05 160)", chipFg: "oklch(0.45 0.1 155)" };
}

export function tierOf(risk) {
  return risk >= 8 ? "Critical" : risk >= 5 ? "High" : risk >= 3 ? "Medium" : "Low";
}

export const KPI_TONE = {
  muted: C.muted,
  warning: C.warning,
  critical: C.critical,
};
