/**
 * Colour-theme preference shared by the root layout (pre-paint script) and the header toggle.
 * "system" follows prefers-color-scheme; "light"/"dark" set data-theme on <html>.
 */

export type ThemePreference = 'system' | 'light' | 'dark';

export const THEME_STORAGE_KEY = 'police-dashboard-theme';

/** Runs before first paint so a stored theme never flashes the other palette. */
export const themeInitScript = `try{var t=localStorage.getItem('${THEME_STORAGE_KEY}');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t}catch(e){}`;
