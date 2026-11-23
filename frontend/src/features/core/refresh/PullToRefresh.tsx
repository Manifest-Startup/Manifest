/**
 * Pull down at the top of the page to sync and refresh: like Mail or Notes on iPhone and Mac.
 *
 * Works with a finger (phones, tablets, the installed app) and a trackpad (two fingers down at
 * the top of a list). A pull past the threshold runs `refreshEverything`:
 *  1. the app's vault mode syncs its folder with the account (ADR 0012),
 *  2. this computer's background vault sync runs now, through `manifest bridge`, when the
 *     browser already lets Manifest reach this computer (never prompting for it),
 *  3. every query on screen is fetched again, so notes and documents show the latest.
 */
import React, { useEffect, useRef, useState } from "react";
import { useApolloClient } from "@apollo/client/react";
import type { ApolloClient } from "@apollo/client";
import { SYNC_NOW_EVENT } from "features/vault/cloudSync";
import { localNetworkGranted, syncComputerVault } from "features/vault/computerFolder";

/** How far to pull (in px, after resistance) before letting go syncs. */
export const PULL_THRESHOLD = 64;
const MAX_PULL = 96;
/** Trackpad: wheel distance up at the top, and the pause that ends one gesture. */
const WHEEL_THRESHOLD = 160;
const WHEEL_GAP_MS = 260;

type Phase = "idle" | "pulling" | "ready" | "syncing" | "done";

export async function refreshEverything(app: ApolloClient): Promise<void> {
  window.dispatchEvent(new Event(SYNC_NOW_EVENT));
  try {
    if (await localNetworkGranted()) await syncComputerVault();
  } catch {
    // The bridge isn't running or the vault isn't set up here: the account still refreshes.
  }
  await app.refetchQueries({ include: "active" });
}

/** True when nothing between the target and the page is scrolled down. */
export function atTop(target: EventTarget | null): boolean {
  if ((document.scrollingElement?.scrollTop ?? 0) > 0) return false;
  for (let el = target instanceof Element ? target : null; el; el = el.parentElement) {
    if (el.scrollTop > 0) {
      const { overflowY } = getComputedStyle(el);
      if (overflowY === "auto" || overflowY === "scroll") return false;
    }
  }
  return true;
}

const LABELS: Record<Phase, string> = {
  idle: "",
  pulling: "Pull to sync",
  ready: "Release to sync",
  syncing: "Syncing…",
  done: "Up to date",
};

export const PullToRefresh: React.FC = () => {
  const app = useApolloClient();
  const [pull, setPull] = useState(0);
  const [phase, setPhase] = useState<Phase>("idle");
  const busy = useRef(false);
  const appRef = useRef(app);
  appRef.current = app;

  useEffect(() => {
    let startY: number | null = null;
    let distance = 0;
    let wheel = 0;
    let lastWheel = 0;
    let wheelGesture = false;
    let settle = 0;

    const show = (value: number) => {
      distance = value;
      setPull(value);
      setPhase(value >= PULL_THRESHOLD ? "ready" : value > 0 ? "pulling" : "idle");
    };
    const run = async () => {
      if (busy.current) return;
      busy.current = true;
      setPull(PULL_THRESHOLD);
      setPhase("syncing");
      try {
        await refreshEverything(appRef.current);
      } finally {
        setPhase("done");
        window.clearTimeout(settle);
        settle = window.setTimeout(() => {
          busy.current = false;
          setPull(0);
          setPhase("idle");
        }, 700);
      }
    };

    const onTouchStart = (event: TouchEvent) => {
      if (busy.current || event.touches.length !== 1 || !atTop(event.target)) return;
      startY = event.touches[0].clientY;
    };
    const onTouchMove = (event: TouchEvent) => {
      if (startY === null) return;
      const dy = event.touches[0].clientY - startY;
      if (dy <= 0) return show(0);
      if (event.cancelable) event.preventDefault(); // ours, not the browser's reload
      show(Math.min(MAX_PULL, dy * 0.5));
    };
    const onTouchEnd = () => {
      if (startY === null) return;
      startY = null;
      if (distance >= PULL_THRESHOLD) void run();
      else show(0);
    };
    const onWheel = (event: WheelEvent) => {
      if (busy.current || event.ctrlKey) return;
      const now = event.timeStamp;
      const fresh = now - lastWheel > WHEEL_GAP_MS;
      lastWheel = now;
      // Only a gesture that starts at the top counts, so the momentum of scrolling up to the
      // top never syncs by accident.
      if (fresh) {
        wheelGesture = event.deltaY < 0 && atTop(event.target);
        wheel = 0;
      }
      if (!wheelGesture || event.deltaY >= 0) return;
      wheel += -event.deltaY;
      show(Math.min(MAX_PULL, (wheel / WHEEL_THRESHOLD) * PULL_THRESHOLD));
      if (wheel >= WHEEL_THRESHOLD) {
        wheelGesture = false;
        void run();
      } else {
        window.clearTimeout(settle);
        settle = window.setTimeout(() => !busy.current && show(0), WHEEL_GAP_MS * 2);
      }
    };

    document.addEventListener("touchstart", onTouchStart, { passive: true });
    document.addEventListener("touchmove", onTouchMove, { passive: false });
    document.addEventListener("touchend", onTouchEnd);
    document.addEventListener("touchcancel", onTouchEnd);
    document.addEventListener("wheel", onWheel, { passive: true });
    return () => {
      window.clearTimeout(settle);
      document.removeEventListener("touchstart", onTouchStart);
      document.removeEventListener("touchmove", onTouchMove);
      document.removeEventListener("touchend", onTouchEnd);
      document.removeEventListener("touchcancel", onTouchEnd);
      document.removeEventListener("wheel", onWheel);
    };
  }, []);

  if (phase === "idle") return null;
  const turning = phase === "syncing";
  return (
    <div
      className="pointer-events-none fixed inset-x-0 top-0 z-[60] flex justify-center"
      style={{ transform: `translateY(${Math.max(8, pull - 24)}px)`, transition: slide(phase) }}
      role="status"
      aria-live="polite"
    >
      <span className="flex items-center gap-2 rounded-full bg-white/95 px-3 py-1.5 text-xs font-medium text-neutral900 shadow-md ring-1 ring-black/5 dark:bg-neutral800/95 dark:text-white dark:ring-white/10">
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className={`h-4 w-4 ${turning ? "animate-spin" : ""}`}
          style={turning ? undefined : { transform: `rotate(${Math.min(1, pull / PULL_THRESHOLD) * 180}deg)` }}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        >
          {phase === "done" ? <path d="M5 12l5 5L20 7" /> : turning ? <path d="M12 3a9 9 0 1 0 9 9" /> : <path d="M12 5v14M6 13l6 6 6-6" />}
        </svg>
        {LABELS[phase]}
      </span>
    </div>
  );
};

const slide = (phase: Phase) => (phase === "pulling" || phase === "ready" ? "none" : "transform 200ms ease");

export default PullToRefresh;
