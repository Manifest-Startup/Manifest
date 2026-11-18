import React, { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { DOCUMENT_ASPECTS, type KnowledgeGraph } from "./wikiLinks";
import "./knowledgeGraph.css";

const DOCUMENT_LABELS: Record<string, string> = {
  business_model_canvas: "Canvas",
  pitch_deck: "Deck",
  product_requirements_document: "Requirements",
  provisional_patent: "Patent",
  similar_ideas: "Similar ideas",
};

const title = (label: string) =>
  label === label.toLowerCase() ? label.replace(/\b\w/g, (c) => c.toUpperCase()) : label;
// Concepts are addressed by their vault note name, the same name the wiki links use.
const conceptSlug = (path: string) => path.split("/").pop() || path;

/** Radial map: the idea in the middle, its concepts around it, connected ideas outside. */
const GraphMap: React.FC<{ graph: KnowledgeGraph; selected?: string; ideaTitle: string }> = ({
  graph,
  selected,
  ideaTitle,
}) => {
  const size = 520;
  const c = size / 2;
  const concepts = graph.concepts;
  const others = useMemo(() => {
    const map = new Map<string, string>();
    for (const concept of concepts) for (const idea of concept.ideas) map.set(idea.ideaId, idea.title);
    return [...map.entries()];
  }, [concepts]);
  const at = (i: number, n: number, r: number, offset = 0) => {
    const a = (2 * Math.PI * i) / Math.max(n, 1) - Math.PI / 2 + offset;
    return { x: c + r * Math.cos(a), y: c + r * Math.sin(a) };
  };
  const conceptAt = new Map(concepts.map((k, i) => [k.label, at(i, concepts.length, 150)]));
  const ideaAt = new Map(others.map(([id], i) => [id, at(i, others.length, 235, 0.2)]));
  return (
    <svg
      className="manifest-graph-map"
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={`${concepts.length} concepts connecting this idea to ${others.length} other ideas`}
    >
      {concepts.map((k) => {
        const p = conceptAt.get(k.label)!;
        return (
          <g key={k.label} data-active={selected === conceptSlug(k.path) || undefined}>
            <line x1={c} y1={c} x2={p.x} y2={p.y} className="edge" />
            {k.ideas.map((idea) => {
              const q = ideaAt.get(idea.ideaId)!;
              return <line key={idea.ideaId} x1={p.x} y1={p.y} x2={q.x} y2={q.y} className="edge edge--cross" />;
            })}
          </g>
        );
      })}
      {others.map(([id, name]) => {
        const q = ideaAt.get(id)!;
        return (
          <Link key={id} to={`/ideas/${id}/knowledge-graph`}>
            <circle cx={q.x} cy={q.y} r={7} className="node node--idea" />
            <text x={q.x} y={q.y + 19} textAnchor="middle" className="label label--idea">
              {name.length > 22 ? `${name.slice(0, 21)}…` : name}
            </text>
          </Link>
        );
      })}
      {concepts.map((k) => {
        const p = conceptAt.get(k.label)!;
        const slug = conceptSlug(k.path);
        return (
          <Link key={k.label} to={`?concept=${encodeURIComponent(slug)}`} replace>
            <circle
              cx={p.x}
              cy={p.y}
              r={4 + Math.min(6, k.passageIds.length + k.documentTypes.length + k.ideas.length)}
              className="node node--concept"
              data-active={selected === slug || undefined}
            />
            <text x={p.x} y={p.y - 12} textAnchor="middle" className="label">
              {title(k.label)}
            </text>
          </Link>
        );
      })}
      <circle cx={c} cy={c} r={16} className="node node--center" />
      <text x={c} y={c + 34} textAnchor="middle" className="label label--center">
        {ideaTitle.length > 30 ? `${ideaTitle.slice(0, 29)}…` : ideaTitle}
      </text>
    </svg>
  );
};

export const KnowledgeGraphView: React.FC<{
  graph: KnowledgeGraph | null | undefined;
  loading: boolean;
  ideaTitle: string;
}> = ({ graph, loading, ideaTitle }) => {
  const [params] = useSearchParams();
  const selected = params.get("concept") ?? undefined;
  if (!graph) {
    return (
      <p className="manifest-document-empty">
        {loading
          ? "Building the knowledge graph…"
          : "The knowledge graph is available to the idea's owner. Write the idea note or answer interview questions to start it."}
      </p>
    );
  }
  const passage = (id: string) => graph.passages.find((p) => p.id === id);
  const focus = graph.concepts.find((k) => conceptSlug(k.path) === selected);
  const ideaCount = new Set(graph.concepts.flatMap((k) => k.ideas.map((i) => i.ideaId))).size;
  return (
    <div className="manifest-knowledge">
      <header className="manifest-document-header">
        <div>
          <h3>Knowledge graph</h3>
          <p>
            {graph.concepts.length} concepts · {graph.passages.length} cited passages · {ideaCount}{" "}
            connected ideas · updates as you talk and as documents are written
          </p>
        </div>
      </header>
      {graph.concepts.length ? (
        <GraphMap graph={graph} selected={selected} ideaTitle={ideaTitle} />
      ) : (
        <p className="manifest-document-empty">
          No concepts yet. Add detail to the note or answer the qualification questions.
        </p>
      )}

      {focus && (
        <section className="manifest-knowledge-focus" aria-label={`Concept: ${title(focus.label)}`}>
          <h4>{title(focus.label)}</h4>
          {focus.passageIds.length > 0 && (
            <ul className="manifest-knowledge-quotes">
              {focus.passageIds.map((id) => (
                <li key={id}>
                  <Link to={`../description?cite=${id}`} relative="path" className="manifest-cite">
                    {id}
                  </Link>{" "}
                  {passage(id)?.text}
                </li>
              ))}
            </ul>
          )}
          <p className="manifest-knowledge-chips">
            {focus.documentTypes.map((d) =>
              DOCUMENT_ASPECTS[d] ? (
                <Link key={d} to={`../${DOCUMENT_ASPECTS[d]}`} relative="path" className="manifest-chip">
                  {DOCUMENT_LABELS[d] ?? d}
                </Link>
              ) : null,
            )}
            {focus.ideas.map((i) => (
              <Link key={i.ideaId} to={`/ideas/${i.ideaId}/knowledge-graph`} className="manifest-chip manifest-chip--idea">
                {i.title}
              </Link>
            ))}
          </p>
        </section>
      )}

      <section aria-label="Concepts">
        <h4>Concepts</h4>
        <p className="manifest-knowledge-chips">
          {graph.concepts.map((k) => (
            <Link
              key={k.label}
              to={`?concept=${encodeURIComponent(conceptSlug(k.path))}`}
              replace
              className="manifest-chip"
              data-active={focus?.label === k.label || undefined}
            >
              {title(k.label)}
              {k.ideas.length > 0 && <span> · {k.ideas.length + 1} ideas</span>}
            </Link>
          ))}
        </p>
      </section>

      {graph.related.length > 0 && (
        <section aria-label="Related ideas">
          <h4>Related ideas</h4>
          <ul className="manifest-knowledge-related">
            {graph.related.map((r) => (
              <li key={r.ideaId}>
                <Link to={`/ideas/${r.ideaId}/knowledge-graph`}>{r.title}</Link>
                <span> shares {r.concepts.map(title).join(", ")}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-label="Source passages">
        <h4>Source passages</h4>
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
      </section>
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
