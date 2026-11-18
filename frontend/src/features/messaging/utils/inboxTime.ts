/*
 * Open Media's time formats (src/domain/threadLayout.ts), formatted here because times must be shown
 * in the viewer's own time zone; Open Media sends ISO times.
 */

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

function daysAgo(date: Date, now: Date): number {
  return Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000);
}

/** "9:02 PM", for the time beside a single message. */
export function formatClockTime(date: Date): string {
  return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" }).format(date);
}

/** Short time for the conversation list: "9:02 PM", "Yesterday", "Monday", "10/1/26". */
export function formatListTime(date: Date, now = new Date()): string {
  const days = daysAgo(date, now);
  if (days === 0) return formatClockTime(date);
  if (days === 1) return "Yesterday";
  if (days > 1 && days < 7) return new Intl.DateTimeFormat("en-US", { weekday: "long" }).format(date);
  return new Intl.DateTimeFormat("en-US", { month: "numeric", day: "numeric", year: "2-digit" }).format(date);
}

/** The two halves of a thread time: { day: "Today", time: "9:02 PM" }, { day: "Sat, Oct 1", time: "9:02 PM" }. */
export function threadTimeParts(date: Date, now = new Date()): { day: string; time: string } {
  const time = formatClockTime(date);
  const days = daysAgo(date, now);
  if (days === 0) return { day: "Today", time };
  if (days === 1) return { day: "Yesterday", time };
  if (days > 1 && days < 7) return { day: new Intl.DateTimeFormat("en-US", { weekday: "long" }).format(date), time };
  const sameYear = date.getFullYear() === now.getFullYear();
  return {
    day: new Intl.DateTimeFormat(
      "en-US",
      sameYear ? { weekday: "short", month: "short", day: "numeric" } : { month: "short", day: "numeric", year: "numeric" },
    ).format(date),
    time,
  };
}
