/**
 * Shared color constants for Playwright specs that assert on computed text/UI colors.
 * Single source of truth: update here when theme colors change.
 */

/** RGB substring values for "readable" text (getComputedStyle may return e.g. "rgb(r, g, b)"). */
export const READABLE_TEXT_RGB = [
  '255, 255, 255',   // white
  '209, 213, 219',   // text-gray-300
  '55, 65, 81',      // text-gray-700
  '248, 250, 252',   // slate heading (#f8fafc)
  '203, 213, 225',   // slate muted (#cbd5e1)
  '17, 24, 39',      // body dark (#111827)
] as const;

/** RGB substring values for status/decoration colors (excluded from "very dark = unreadable" check). */
export const STATUS_COLOR_RGB = [
  '239, 68, 68',    // red
  '34, 197, 94',    // green
  '234, 179, 8',    // yellow
  '59, 130, 246',   // blue
  '168, 85, 247',   // purple
  '134, 239, 172',  // green-300 badge
  '253, 224, 71',   // yellow-300 badge
  '34, 211, 238',   // cyan step 0
  '96, 165, 250',   // blue step 1
  '74, 222, 128',   // green step 2
  '250, 204, 21',   // yellow step 3
  '251, 146, 60',   // orange step 4
  '244, 114, 182',  // pink step 5
  '192, 132, 252',  // violet step 6
] as const;

export function isReadableColor(color: string): boolean {
  return (
    READABLE_TEXT_RGB.some((part) => color.includes(part)) ||
    color === '#ffffff' ||
    color === 'white'
  );
}

export function isStatusColor(color: string): boolean {
  return STATUS_COLOR_RGB.some((part) => color.includes(part));
}
