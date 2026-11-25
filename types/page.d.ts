// The two globals of the page, for the type checker (jsconfig.json): boot.js, a plain script in <head>, sets them
// before the first paint; the modules read them (themes.js, header.js, util.js, app.js).

/** A theme's 4 colours, from which boot.js derives the others. */
interface ThemeColors { bg: string; text: string; muted: string; accent: string }

interface Window {
  /** The palettes and the colours of the page (boot.js). */
  themes: {
    palettes: { light: string[]; dark: string[] };
    /** The CSS variables of a theme from its 4 colours. */
    tokens(colors: ThemeColors): Record<string, string>;
    /** WCAG contrast ratio of two colours, 1 to 21. */
    contrast(a: string, b: string): number;
    isDark(background: string): boolean;
    /** The colours of a theme the user made or changed, or null for a built-in palette left as it is. */
    colorsOf(id: string): ThemeColors | null;
    /** The mode and the palette remembered, set on <html>. */
    apply(): void;
  };
  /** The size of the text: a zoom of the whole page (boot.js). */
  textZoom: {
    get(): number;
    canGrow(): boolean;
    canShrink(): boolean;
    /** +1: larger, -1: smaller; remembered. */
    step(direction: number): number;
  };
}
