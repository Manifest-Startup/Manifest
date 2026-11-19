import React, { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { DOCUMENT_ASPECTS, type KnowledgeGraph } from "./wikiLinks";
import "./knowledgeGraph.css";

type Concept = KnowledgeGraph["concepts"][number];
type Relation = KnowledgeGraph["relations"][number];

const DOCUMENT_LABELS: Record<string, string> = {
  business_model_canvas: "Canvas",
  pitch_deck: "Deck",
  product_requirements_document: "Requirements",
  provisional_patent: "Patent",
  similar_ideas: "Similar ideas",
};

/** The idea model's lanes, in the order a founder would tell the story (ADR 0009). */
export const LANES: { role: string; label: string; hint: string }[] = [
  { role: "who", label: "Who it's for", hint: "people and organisations" },
  { role: "problem", label: "Problem", hint: "what goes wrong today" },
  { role: "solution", label: "Solution", hint: "what you're building" },
  { role: "technology", label: "How it works", hint: "technology it relies on" },
  { role: "business", label: "Business", hint: "who pays and how" },
];

const title = (label: string) =>
  label === label.toLowerCase() ? label.replace(/\b\w/g, (c) => c.toUpperCase()) : label;
// Concepts are addressed by their vault note name, the same name the wiki links use.
const conceptSlug = (path: string) => path.split("/").pop() || path;
const conceptHref = (c: Concept) => `?concept=${encodeURIComponent(conceptSlug(c.path))}`;

/** Splits text so the concept's words can be highlighted where the founder wrote them. */
export function highlight(text: string, phrases: string[]): React.ReactNode[] {
  const words = phrases
    .filter((p) => p.trim())
    .sort((a, b) => b.length - a.length)
    .map((p) =>
      p
        .split(/\s+/)
        .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
        .join("[\\s-]+") + "(?:s|es|ies|ing|ed)?",
    );
  if (!words.length) return [text];
  const pattern = new RegExp(`\\b(${words.join("|")})\\b`, "gi");
  const parts = text.split(pattern);
  return parts.map((part, i) => (i % 2 ? <mark key={i}>{part}</mark> : part));
}

/** Phone layout: the same lanes as readable stacked lists (the map is too small there). */
const IdeaLanes: React.FC<{ concepts: Concept[]; selected?: string }> = ({ concepts, selected }) => (
  <div className="manifest-idea-lanes">
    {LANES.map((lane) => {
      const items = concepts.filter((c) => c.role === lane.role);
      if (!items.length) return null;
      return (
        <section key={lane.role} aria-label={lane.label} className="manifest-idea-lane">
          <h5>
            {lane.label} <span>{lane.hint}</span>
          </h5>
          <p className="manifest-knowledge-chips">
            {items.map((c) => (
              <Link
                key={c.label}
                to={conceptHref(c)}
                replace
                className={`manifest-pill manifest-pill--${c.role}`}
                data-active={selected === conceptSlug(c.path) || undefined}
              >
                {title(c.label)}
              </Link>
            ))}
          </p>
        </section>
      );
    })}
  </div>
);

/** Concepts in lanes by role, with the founder's own connections drawn between them. */
const IdeaMap: React.FC<{
  concepts: Concept[];
  relations: Relation[];
  selected?: string;
}> = ({ concepts, relations, selected }) => {
  const lanes = LANES.map((lane) => ({
    ...lane,
    items: concepts
      .filter((c) => c.role === lane.role)
      // Broader concepts first, each followed by the narrower ones under it.
      .sort((a, b) => (a.parent ? 1 : 0) - (b.parent ? 1 : 0) || b.weight - a.weight),
  })).filter((lane) => lane.items.length);
  const colW = 196;
  const nodeW = 168;
  const rowH = 46;
  const top = 44;
  const pos = new Map<string, { x: number; y: number; lane: number }>();
  lanes.forEach((lane, li) =>
    lane.items.forEach((c, ri) => pos.set(c.label, { x: 12 + li * colW, y: top + ri * rowH, lane: li })),
  );
  const width = Math.max(1, lanes.length) * colW;
  const height = top + Math.max(1, ...lanes.map((l) => l.items.length)) * rowH + 8;
  const focus = concepts.find((c) => conceptSlug(c.path) === selected)?.label;
  const drawn = relations.filter((r) => pos.has(r.source) && pos.has(r.target));
  const clip = (text: string, n: number) => (text.length > n ? `${text.slice(0, n - 1)}…` : text);

  return (
    <svg
      className="manifest-idea-map"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Idea map: ${concepts.length} concepts in ${lanes.length} parts, ${drawn.length} connections`}
    >
      {lanes.map((lane, li) => (
        <g key={lane.role} className={`lane lane--${lane.role}`}>
          <rect x={4 + li * colW} y={4} width={colW - 8} height={height - 8} rx={14} className="lane-bg" />
          <text x={12 + li * colW} y={26} className="lane-title">
            {lane.label}
          </text>
        </g>
      ))}
      {drawn.map((r) => {
        const a = pos.get(r.source)!;
        const b = pos.get(r.target)!;
        const sameLane = a.lane === b.lane;
        const forward = b.x >= a.x;
        const x1 = sameLane ? a.x + nodeW : forward ? a.x + nodeW : a.x;
        const x2 = sameLane ? b.x + nodeW : forward ? b.x : b.x + nodeW;
        const y1 = a.y + 15;
        const y2 = b.y + 15;
        const bend = sameLane ? 22 : (x2 - x1) / 2;
        const d = sameLane
          ? `M${x1},${y1} C${x1 + bend},${y1} ${x2 + bend},${y2} ${x2},${y2}`
          : `M${x1},${y1} C${x1 + bend},${y1} ${x2 - bend},${y2} ${x2},${y2}`;
        const active = focus && (r.source === focus || r.target === focus);
        return (
          <g key={`${r.source}-${r.target}`} className="link" data-active={active || undefined} data-dim={(focus && !active) || undefined}>
            <path d={d} markerEnd="url(#manifest-arrow)" />
            <title>{`${title(r.source)} ${r.label} ${title(r.target)} (${r.passageIds.join(", ")})`}</title>
          </g>
        );
      })}
      <defs>
        <marker id="manifest-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M0,0 L8,4 L0,8 z" className="arrow" />
        </marker>
      </defs>
      {lanes.flatMap((lane) =>
        lane.items.map((c) => {
          const p = pos.get(c.label)!;
          const indent = c.parent && lane.items.some((o) => o.label === c.parent) ? 10 : 0;
          const active = selected === conceptSlug(c.path);
          return (
            <Link key={c.label} to={conceptHref(c)} replace className="node-link">
              <g className={`node node--${c.role}`} data-active={active || undefined}>
                <rect x={p.x + indent} y={p.y} width={nodeW - indent} height={30} rx={9} />
                <text x={p.x + indent + 10} y={p.y + 19}>
                  {indent ? "↳ " : ""}
                  {clip(title(c.label), indent ? 19 : 23)}
                </text>
                <text x={p.x + nodeW - 8} y={p.y + 19} textAnchor="end" className="count">
                  {c.passageIds.length || ""}
                </text>
                <title>{c.why}</title>
              </g>
            </Link>
          );
        }),
      )}
    </svg>
  );
};

const RelationRow: React.FC<{ r: Relation; byLabel: Map<string, Concept> }> = ({ r, byLabel }) => {
  const a = byLabel.get(r.source);
  const b = byLabel.get(r.target);
  return (
    <li>
      {a ? <Link to={conceptHref(a)} replace className={`manifest-pill manifest-pill--${a.role}`}>{title(r.source)}</Link> : title(r.source)}
      <span className="manifest-relation-verb">{r.label}</span>
      {b ? <Link to={conceptHref(b)} replace className={`manifest-pill manifest-pill--${b.role}`}>{title(r.target)}</Link> : title(r.target)}
      <span className="manifest-relation-cites">
        {r.passageIds.map((id) => (
          <Link key={id} to={`../description?cite=${id}`} relative="path" className="manifest-cite">
            {id}
          </Link>
        ))}
      </span>
    </li>
  );
};

export const KnowledgeGraphView: React.FC<{
  graph: KnowledgeGraph | null | undefined;
  loading: boolean;
  ideaTitle: string;
}> = ({ graph, loading, ideaTitle }) => {
  const [params] = useSearchParams();
  const selected = params.get("concept") ?? undefined;
  const byLabel = useMemo(() => new Map((graph?.concepts ?? []).map((c) => [c.label, c])), [graph]);
  if (!graph) {
    return (
      <p className="manifest-document-empty">
        {loading
          ? "Building the knowledge graph…"
          : "The knowledge graph is available to the idea's owner. Write the idea note or answer interview questions to start it."}
      </p>
    );
  }
  const relations = graph.relations ?? [];
  const passage = (id: string) => graph.passages.find((p) => p.id === id);
  const focus = graph.concepts.find((k) => conceptSlug(k.path) === selected);
  const themes = graph.concepts.filter((c) => c.role === "context");
  const skills = graph.concepts.filter((c) => c.role === "skill");
  const mapped = graph.concepts.filter((c) => LANES.some((l) => l.role === c.role));
  const focusRelations = focus
    ? relations.filter((r) => r.source === focus.label || r.target === focus.label)
    : [];
  const sentences = new Set(graph.concepts.flatMap((c) => c.passageIds)).size;

  return (
    <div className="manifest-knowledge">
      <header className="manifest-document-header">
        <div>
          <h3>Knowledge graph</h3>
          <p>
            Built only from your own words in “{ideaTitle}”: {graph.concepts.length} concepts from {sentences}{" "}
            of your sentences, sorted into the parts of the idea. Select a concept to see where it came from.
          </p>
        </div>
      </header>

      {mapped.length ? (
        <>
          <IdeaMap concepts={mapped} relations={relations} selected={selected} />
          <IdeaLanes concepts={mapped} selected={selected} />
        </>
      ) : (
        <p className="manifest-document-empty">
          No concepts yet. Say who it's for, what goes wrong today and what you'd build, in the note or the interview.
        </p>
      )}

      {(themes.length > 0 || skills.length > 0) && (
        <div className="manifest-knowledge-themes">
          {themes.length > 0 && (
            <p className="manifest-knowledge-chips">
              <span className="manifest-knowledge-label">Themes</span>
              {themes.map((k) => (
                <Link key={k.label} to={conceptHref(k)} replace className="manifest-chip" data-active={focus?.label === k.label || undefined}>
                  {title(k.label)}
                </Link>
              ))}
            </p>
          )}
          {skills.length > 0 && (
            <p className="manifest-knowledge-chips">
              <span className="manifest-knowledge-label">Skills needed</span>
              {skills.map((k) => (
                <Link key={k.label} to={conceptHref(k)} replace className="manifest-chip" data-active={focus?.label === k.label || undefined}>
                  {k.label}
                </Link>
              ))}
            </p>
          )}
        </div>
      )}

      {focus && (
        <section className="manifest-knowledge-focus" aria-label={`Concept: ${title(focus.label)}`}>
          <div className="manifest-knowledge-focus-head">
            <h4>{title(focus.label)}</h4>
            <span className={`manifest-pill manifest-pill--${focus.role}`}>{focus.roleLabel}</span>
            {focus.parent && <span className="manifest-knowledge-kind">part of {title(focus.parent)}</span>}
          </div>
          <p className="manifest-knowledge-why">
            <strong>How it was found.</strong> {focus.why}
          </p>
          {focus.passageIds.length > 0 && (
            <ul className="manifest-knowledge-quotes">
              {focus.passageIds.map((id) => (
                <li key={id}>
                  <Link to={`../description?cite=${id}`} relative="path" className="manifest-cite">
                    {id}
                  </Link>{" "}
                  {highlight(passage(id)?.text ?? "", [
                    focus.label,
                    // One-word fragments ("plan") are evidence, not names: don't mark them.
                    ...focus.aliases.filter((a) => a.includes(" ")),
                  ])}
                </li>
              ))}
            </ul>
          )}
          {focusRelations.length > 0 && (
            <ul className="manifest-knowledge-relations">
              {focusRelations.map((r) => (
                <RelationRow key={`${r.source}-${r.target}`} r={r} byLabel={byLabel} />
              ))}
            </ul>
          )}
          {(focus.documentTypes.length > 0 || focus.ideas.length > 0) && (
            <p className="manifest-knowledge-chips">
              {focus.documentTypes.map((d) =>
                DOCUMENT_ASPECTS[d] ? (
                  <Link key={d} to={`../${DOCUMENT_ASPECTS[d]}`} relative="path" className="manifest-chip">
                    In {DOCUMENT_LABELS[d] ?? d}
                  </Link>
                ) : null,
              )}
              {focus.ideas.map((i) => (
                <Link key={i.ideaId} to={`/ideas/${i.ideaId}/knowledge-graph`} className="manifest-chip manifest-chip--idea">
                  Also in {i.title}
                </Link>
              ))}
            </p>
          )}
        </section>
      )}

      {relations.length > 0 && (
        <section aria-label="How it connects">
          <h4>How it connects</h4>
          <ul className="manifest-knowledge-relations">
            {relations.map((r) => (
              <RelationRow key={`${r.source}-${r.target}`} r={r} byLabel={byLabel} />
            ))}
          </ul>
        </section>
      )}

      {graph.related.length > 0 && (
        <section aria-label="Related ideas">
          <h4>Related ideas</h4>
          <ul className="manifest-knowledge-related">
            {graph.related.map((r) => (
              <li key={r.ideaId}>
                <Link to={`/ideas/${r.ideaId}/knowledge-graph`}>{r.title}</Link>
                <span> {r.reason || `shares ${r.concepts.map(title).join(", ")}`}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <details className="manifest-knowledge-sources">
        <summary>Your sentences ({graph.passages.length})</summary>
        <ul className="manifest-knowledge-quotes">
          {graph.passages.map((p) => (
            <li key={p.id}>
              <Link to={`../description?cite=${p.id}`} relative="path" className="manifest-cite">
                {p.id}
              </Link>{" "}
              {p.text}
              {p.kind === "answer" && <span className="manifest-knowledge-kind"> · interview</span>}
            </li>
          ))}
        </ul>
      </details>

      <details className="manifest-knowledge-sources">
        <summary>How this graph is made</summary>
        <ol className="manifest-knowledge-method">
          <li>Your note is split into sentences (p1, p2…) and your interview answers into a1, a2…. Generated documents never add concepts.</li>
          <li>Phrases you repeat, or that name something specific, become concepts. Fragments fold into the phrase they belong to (“plan” into “meal plan”).</li>
          <li>Each concept gets a part of the idea from what it is (people, organisations, technology) and from the words around it (“skip”, “closed” → problem; “pay” → business).</li>
          <li>Two concepts in the same sentence are connected; the label comes from their parts (who → struggles with → problem; solution → addresses → problem).</li>
          <li>Other ideas connect only through concepts that are distinctive across your ideas, and documents cite the sentence they best match.</li>
        </ol>
      </details>
    </div>
  );
};

/** Shown above the idea note when a document citation links here (`?cite=p3`). */
export const CitationBanner: React.FC<{ graph: KnowledgeGraph | null | undefined }> = ({ graph }) => {
  const [params, setParams] = useSearchParams();
  const id = params.get("cite");
  const passage = id ? graph?.passages.find((p) => p.id === id) : undefined;
  if (!id || !passage) return null;
  const close = () => {
    const next = new URLSearchParams(params);
    next.delete("cite");
    setParams(next, { replace: true });
  };
  return (
    <aside className="manifest-cite-banner" role="note" aria-label="Cited passage">
      <span className="manifest-cite">{id}</span>
      <blockquote>{passage.text}</blockquote>
      <p>
        {passage.kind === "answer"
          ? "From your qualification interview. Your documents cite this answer."
          : "From this note. Your documents cite this sentence."}{" "}
        <Link to="../knowledge-graph" relative="path">
          Open the knowledge graph
        </Link>
      </p>
      <button type="button" onClick={close} aria-label="Close cited passage">
        ×
      </button>
    </aside>
  );
};
