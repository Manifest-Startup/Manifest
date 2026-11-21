import React, { useEffect, useMemo, useRef, useState } from "react";

import "./settings.css";

/**
 * Settings shell: a sidebar of a few categories, one focused page per
 * category, and a search box that finds any individual setting.
 *
 * Design choices (from settings-UX research): group by what people think the
 * setting is about, most-used first; show status in the navigation instead of
 * long descriptions; search once settings no longer fit on one screen; keep
 * destructive actions last.
 */

export type SettingsIconName = "user" | "palette" | "sparkles" | "puzzle" | "code" | "database" | "shield" | "chat";

export interface SettingsItem {
  /** DOM id of the card or field this item scrolls to. */
  anchor: string;
  label: string;
  /** Extra words people might type for this setting. */
  keywords?: string;
}

export interface SettingsStatus {
  text: string;
  tone: "ok" | "warn" | "neutral";
}

export interface SettingsSection {
  id: string;
  label: string;
  summary: string;
  icon: SettingsIconName;
  status?: SettingsStatus | null;
  items: SettingsItem[];
  content: React.ReactNode;
}

interface SettingsViewProps {
  sections: SettingsSection[];
  activeId: string;
  onSelect: (sectionId: string) => void;
  /** Card to scroll to and highlight once the section is shown. */
  focusAnchor?: string | null;
  onFocusHandled?: () => void;
}

const ICON_PATHS: Record<SettingsIconName, string> = {
  user: "M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.5 20.1a7.5 7.5 0 0 1 15 0A17.9 17.9 0 0 1 12 21.75c-2.68 0-5.22-.58-7.5-1.65Z",
  palette:
    "M4.1 19.9a3 3 0 0 0 5.8-1.1c0-.8-.3-1.6-.9-2.1a3 3 0 0 0-4.9 3.2Zm0 0a6 6 0 0 0 7.6-2.9M9 16.7l9.4-9.4a2.1 2.1 0 1 0-3-3L6 13.7m3 3-3-3",
  sparkles:
    "M9.8 15.9 9 18.75l-.8-2.85a4.5 4.5 0 0 0-3.1-3.1L2.25 12l2.85-.8a4.5 4.5 0 0 0 3.1-3.1L9 5.25l.8 2.85a4.5 4.5 0 0 0 3.1 3.1l2.85.8-2.85.8a4.5 4.5 0 0 0-3.1 3.1ZM18.26 8.72 18 9.75l-.26-1.03a3.38 3.38 0 0 0-2.46-2.46L14.25 6l1.03-.26a3.38 3.38 0 0 0 2.46-2.46L18 2.25l.26 1.03a3.38 3.38 0 0 0 2.46 2.46l1.03.26-1.03.26a3.38 3.38 0 0 0-2.46 2.46Z",
  puzzle:
    "M14.25 6.09c0-.36.19-.68.4-.96.21-.28.35-.62.35-1 0-1.04-1.01-1.88-2.25-1.88S10.5 3.1 10.5 4.13c0 .38.13.72.35 1 .21.28.4.6.4.96a.64.64 0 0 1-.66.64 48.4 48.4 0 0 1-4.16-.3c.2 1.61.31 3.25.33 4.9a.64.64 0 0 1-.64.65c-.36 0-.68-.19-.96-.4a1.65 1.65 0 0 0-1-.35c-1.04 0-1.88 1.01-1.88 2.25s.84 2.25 1.88 2.25c.38 0 .72-.13 1-.35.28-.21.6-.4.96-.4.31 0 .55.26.53.57a48.04 48.04 0 0 1-.6 4.84c1.63.2 3.3.33 4.98.36a.64.64 0 0 0 .66-.64c0-.36-.19-.68-.4-.96a1.65 1.65 0 0 1-.35-1c0-1.04 1.01-1.88 2.25-1.88s2.25.84 2.25 1.88c0 .38-.13.72-.35 1-.21.28-.4.6-.4.96 0 .33.28.6.6.58a48.1 48.1 0 0 0 4.9-.52c.2-1.6.3-3.23.33-4.88a.64.64 0 0 0-.65-.64c-.36 0-.68.19-.96.4-.28.21-.62.35-1 .35-1.04 0-1.88-1.01-1.88-2.25s.84-2.25 1.88-2.25c.38 0 .72.13 1 .35.28.21.6.4.96.4.37 0 .66-.31.64-.68a48.3 48.3 0 0 0-.35-4.85 48.35 48.35 0 0 1-4.89.4.6.6 0 0 1-.6-.6Z",
  code: "M17.25 6.75 22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3-4.5 16.5",
  database:
    "M20.25 6.38c0 2.27-3.69 4.12-8.25 4.12S3.75 8.65 3.75 6.38m16.5 0C20.25 4.1 16.56 2.25 12 2.25S3.75 4.1 3.75 6.38m16.5 0v11.25c0 2.27-3.69 4.12-8.25 4.12s-8.25-1.85-8.25-4.12V6.38m16.5 5.62c0 2.27-3.69 4.12-8.25 4.12S3.75 14.27 3.75 12",
  shield:
    "M9 12.75 11.25 15 15 9.75m-3-7.04A11.96 11.96 0 0 1 3.6 6 12 12 0 0 0 3 9.75c0 5.6 3.82 10.3 9 11.62 5.18-1.33 9-6.03 9-11.62 0-1.31-.21-2.57-.6-3.75h-.15c-3.2 0-6.1-1.25-8.25-3.29Z",
  chat: "M8.63 12a.38.38 0 1 1-.76 0 .38.38 0 0 1 .76 0Zm4 0a.38.38 0 1 1-.76 0 .38.38 0 0 1 .76 0Zm4 0a.38.38 0 1 1-.76 0 .38.38 0 0 1 .76 0ZM21 12c0 4.56-4.03 8.25-9 8.25a9.76 9.76 0 0 1-2.56-.34A5.97 5.97 0 0 1 5.41 21a6 6 0 0 1-.6-.04 4.47 4.47 0 0 0 .98-2.31C4.06 17.28 3 15.3 3 12c0-4.56 4.03-8.25 9-8.25s9 3.69 9 8.25Z",
};

export const SettingsIcon: React.FC<{ name: SettingsIconName; className?: string }> = ({ name, className = "h-[18px] w-[18px]" }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6} aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" d={ICON_PATHS[name]} />
  </svg>
);

/** One card inside a settings page. `id` is the anchor search results jump to. */
export const SettingsCard: React.FC<{
  id?: string;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  tone?: "default" | "danger";
  children: React.ReactNode;
}> = ({ id, title, description, action, tone = "default", children }) => (
  <section id={id} className={`manifest-panel settings-card ${tone === "danger" ? "settings-card-danger" : ""}`} aria-labelledby={id ? `${id}-title` : undefined}>
    <header className="settings-card-header">
      <div className="min-w-0">
        <h3 id={id ? `${id}-title` : undefined} className="settings-card-title">{title}</h3>
        {description ? <p className="settings-card-description">{description}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </header>
    <div className="settings-card-body">{children}</div>
  </section>
);

const normalize = (value: string) => value.toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "");

interface SearchHit {
  section: SettingsSection;
  item: SettingsItem;
}

export const searchSettings = (sections: SettingsSection[], query: string): SearchHit[] => {
  const tokens = normalize(query).split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return [];
  const hits: Array<SearchHit & { score: number }> = [];
  for (const section of sections) {
    for (const item of section.items) {
      const label = normalize(item.label);
      const haystack = `${label} ${normalize(item.keywords ?? "")} ${normalize(section.label)}`;
      if (!tokens.every((token) => haystack.includes(token))) continue;
      // Whole-word match in the name first, then partial name match, then keyword-only.
      const labelWords = label.split(/[^a-z0-9]+/);
      const score = tokens.every((token) => labelWords.some((word) => word.startsWith(token)))
        ? 0
        : tokens.some((token) => label.includes(token))
          ? 1
          : 2;
      hits.push({ section, item, score });
    }
  }
  // Array.prototype.sort is stable, so equal scores keep the sidebar order.
  return hits.sort((a, b) => a.score - b.score).map(({ section, item }) => ({ section, item }));
};

const StatusPill: React.FC<{ status: SettingsStatus }> = ({ status }) => (
  <span className={`settings-status settings-status-${status.tone}`}>
    <span className="settings-status-dot" aria-hidden="true" />
    {status.text}
  </span>
);

const SettingsView: React.FC<SettingsViewProps> = ({ sections, activeId, onSelect, focusAnchor, onFocusHandled }) => {
  const [query, setQuery] = useState("");
  const [highlighted, setHighlighted] = useState(0);
  const searchRef = useRef<HTMLInputElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [pendingAnchor, setPendingAnchor] = useState<string | null>(null);

  const active = sections.find((section) => section.id === activeId) ?? sections[0];
  const hits = useMemo(() => searchSettings(sections, query), [sections, query]);
  const searching = query.trim().length > 0;

  // "/" or Cmd/Ctrl+K focuses settings search, like most desktop apps.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      if ((event.key === "/" && !typing) || ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k" && !typing)) {
        event.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (focusAnchor) setPendingAnchor(focusAnchor);
  }, [focusAnchor]);

  // On phones the categories are a scrolling row; keep the selected one in view.
  const navRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const nav = navRef.current;
    const item = nav?.querySelector<HTMLElement>(".settings-nav-item.is-active");
    if (!nav || !item || nav.scrollWidth <= nav.clientWidth) return;
    nav.scrollTo?.({ left: item.offsetLeft - (nav.clientWidth - item.offsetWidth) / 2, behavior: "smooth" });
  }, [active.id]);

  // Scroll to and briefly highlight the requested card once it is rendered.
  useEffect(() => {
    if (!pendingAnchor || searching) return;
    const timer = window.setTimeout(() => {
      const node = document.getElementById(pendingAnchor);
      if (node) {
        node.scrollIntoView?.({ behavior: "smooth", block: "start" });
        node.classList.remove("settings-flash");
        void node.offsetWidth;
        node.classList.add("settings-flash");
      }
      setPendingAnchor(null);
      onFocusHandled?.();
    }, 60);
    return () => window.clearTimeout(timer);
  }, [pendingAnchor, activeId, searching, onFocusHandled]);

  const openHit = (hit: SearchHit) => {
    setQuery("");
    onSelect(hit.section.id);
    setPendingAnchor(hit.item.anchor);
  };

  const selectSection = (id: string) => {
    setQuery("");
    onSelect(id);
    window.requestAnimationFrame(() => headingRef.current?.focus({ preventScroll: true }));
  };

  const onSearchKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      setQuery("");
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlighted((index) => Math.min(index + 1, Math.max(hits.length - 1, 0)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlighted((index) => Math.max(index - 1, 0));
    } else if (event.key === "Enter" && hits[highlighted]) {
      event.preventDefault();
      openHit(hits[highlighted]);
    }
  };

  return (
    <div className="settings-layout" data-testid="settings-view">
      <aside className="settings-sidebar">
        <label className="settings-search">
          <svg className="settings-search-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-4.35-4.35M17 10.5a6.5 6.5 0 1 1-13 0 6.5 6.5 0 0 1 13 0Z" />
          </svg>
          <span className="sr-only">Search settings</span>
          <input
            ref={searchRef}
            type="search"
            value={query}
            placeholder="Search settings"
            aria-controls="settings-search-results"
            onChange={(event) => {
              setQuery(event.target.value);
              setHighlighted(0);
            }}
            onKeyDown={onSearchKeyDown}
          />
          {!searching ? <kbd className="settings-kbd" aria-hidden="true">/</kbd> : null}
        </label>

        <nav ref={navRef} aria-label="Settings sections" className="settings-nav">
          {sections.map((section) => {
            const selected = !searching && section.id === active.id;
            return (
              <button
                key={section.id}
                type="button"
                className={`settings-nav-item ${selected ? "is-active" : ""}`}
                aria-current={selected ? "page" : undefined}
                onClick={() => selectSection(section.id)}
              >
                <span className="settings-nav-icon">
                  <SettingsIcon name={section.icon} />
                </span>
                <span className="settings-nav-text">
                  <span className="settings-nav-label">{section.label}</span>
                  {section.status ? <StatusPill status={section.status} /> : null}
                </span>
              </button>
            );
          })}
        </nav>
      </aside>

      <div className="settings-content">
        {searching ? (
          <div id="settings-search-results" role="region" aria-live="polite" aria-label="Search results">
            <p className="settings-eyebrow">Search</p>
            <h2 className="settings-title">
              {hits.length === 0 ? `No settings match “${query.trim()}”` : `${hits.length} ${hits.length === 1 ? "setting" : "settings"} for “${query.trim()}”`}
            </h2>
            {hits.length === 0 ? (
              <p className="settings-summary">Try a broader word, like “key”, “photo”, “delete” or “theme”.</p>
            ) : (
              <ul className="settings-results" role="listbox" aria-label="Matching settings">
                {hits.map((hit, index) => (
                  <li key={`${hit.section.id}-${hit.item.anchor}-${hit.item.label}`} role="option" aria-selected={index === highlighted}>
                    <button
                      type="button"
                      className={`settings-result ${index === highlighted ? "is-highlighted" : ""}`}
                      onMouseEnter={() => setHighlighted(index)}
                      onClick={() => openHit(hit)}
                    >
                      <span className="settings-nav-icon">
                        <SettingsIcon name={hit.section.icon} />
                      </span>
                      <span className="min-w-0 flex-1 text-left">
                        <span className="block font-medium text-theme-primary">{hit.item.label}</span>
                        <span className="block text-xs text-theme-secondary">{hit.section.label}</span>
                      </span>
                      <svg className="h-4 w-4 text-theme-secondary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                        <path strokeLinecap="round" strokeLinejoin="round" d="m9 5 7 7-7 7" />
                      </svg>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : (
          <div key={active.id} className="settings-pane">
            <header className="settings-pane-header">
              <h2 ref={headingRef} tabIndex={-1} className="settings-title">
                {active.label}
              </h2>
              <p className="settings-summary">{active.summary}</p>
            </header>
            <div className="settings-stack">{active.content}</div>
          </div>
        )}
      </div>
    </div>
  );
};

export default SettingsView;
