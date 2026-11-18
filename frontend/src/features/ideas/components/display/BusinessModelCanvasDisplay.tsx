import type { IconType } from "react-icons";
import React from "react";
import { useQuery, useReactiveVar } from "@apollo/client/react";
import { DocumentMarkdown } from "./MarkdownDisplay";
import "./documents.css";
import { Link } from "react-router-dom";
import { getIntegrationCatalogEntry } from "features/account/lib/integrationsCatalog";
import { userVar } from "features/core/apollo/localState";
import { GET_INTEGRATIONS } from "features/core/apollo/queries";
import {
  DocumentGenerationNotice,
  type DocumentGenerationState,
} from "./DocumentGenerationNotice";
import { parseBusinessModelCanvasSections } from "./bmcIntegrationHints";
import { useWikiLinks } from "../../knowledge/WikiLinkContext";
import { citedFor } from "../../knowledge/wikiLinks";

interface BusinessModelCanvasDisplayProps {
  content: any;
  fallbackMessage: string;
  generationState?: DocumentGenerationState | null;
}

interface KeyPartnerConnectionsProps {
  suggestedServiceIds: string[];
}

type PartnerChip = { id: string; name: string; Icon: IconType | null; connected: boolean };

/**
 * Key partners are the people and services the founder actually works with:
 * every connected integration (Open Media included) and any partner they
 * added by name, followed by the AI's suggestions they haven't connected yet.
 */
const KeyPartnerConnections: React.FC<KeyPartnerConnectionsProps> = ({ suggestedServiceIds }) => {
  const { isLoggedIn } = useReactiveVar(userVar);
  const { data } = useQuery(GET_INTEGRATIONS, { skip: !isLoggedIn });

  const connected: PartnerChip[] = (data?.integrations ?? []).map((integration) => {
    const entry = getIntegrationCatalogEntry(integration.serviceId);
    return {
      id: integration.serviceId,
      name: entry?.name ?? integration.serviceName,
      Icon: entry?.icon ?? null,
      connected: true,
    };
  });
  const connectedIds = new Set(connected.map((partner) => partner.id));
  const suggested: PartnerChip[] = suggestedServiceIds
    .filter((id) => !connectedIds.has(id))
    .map((id) => getIntegrationCatalogEntry(id))
    .filter((entry): entry is NonNullable<typeof entry> => !!entry)
    .map((entry) => ({ id: entry.id, name: entry.name, Icon: entry.icon, connected: false }));

  if (!isLoggedIn && suggested.length === 0) {
    return null;
  }

  const chip = (partner: PartnerChip) => (
    <Link
      key={partner.id}
      to={partner.id === "open_media" ? "/account" : `/account?focusIntegration=${encodeURIComponent(partner.id)}`}
      className={`manifest-partner-chip${partner.connected ? "" : " manifest-partner-chip--suggested"}`}
      aria-label={partner.connected ? `${partner.name}: connected` : `Connect ${partner.name}`}
    >
      {partner.Icon ? <partner.Icon size={14} aria-hidden="true" /> : <span className="manifest-partner-initial" aria-hidden="true">{partner.name.charAt(0)}</span>}
      <span>{partner.name}</span>
      {partner.connected ? null : <span className="manifest-partner-action">Connect</span>}
    </Link>
  );

  return (
    <div className="manifest-partners" aria-label="Your partners">
      {connected.length > 0 && <div className="manifest-partner-row">{connected.map(chip)}</div>}
      {suggested.length > 0 && (
        <>
          <p className="manifest-partner-label">Suggested</p>
          <div className="manifest-partner-row">{suggested.map(chip)}</div>
        </>
      )}
      {isLoggedIn && (
        <Link to="/account?focusIntegration=other" className="manifest-partner-add">
          + Add a partner
        </Link>
      )}
    </div>
  );
};

export const BusinessModelCanvasDisplay: React.FC<
  BusinessModelCanvasDisplayProps
> = ({ content: stored, fallbackMessage, generationState }) => {
  // Prefer the knowledge graph's cited copy (same text plus [[wiki-link]] citations).
  const { graph } = useWikiLinks();
  const content = citedFor(graph, "business_model_canvas", stored) ?? stored;
  if (typeof content !== "string" || !content.trim()) {
    if (generationState) {
      return (
        <DocumentGenerationNotice
          state={generationState}
          title="Business Model Canvas"
          variant="business-model-canvas"
        />
      );
    }

    return (
      <div className="text-gray-500 dark:text-gray-400 italic">
        {fallbackMessage}
      </div>
    );
  }

  const parsedSections = parseBusinessModelCanvasSections(content);

  if (parsedSections.length === 0) {
    return (
      <div className="prose prose-lg dark:prose-invert max-w-none">
        <DocumentMarkdown content={content} />
      </div>
    );
  }

  const blocks = [
    "Key Partners",
    "Key Activities",
    "Key Resources",
    "Value Propositions",
    "Customer Relationships",
    "Channels",
    "Customer Segments",
    "Cost Structure",
    "Revenue Streams",
  ];
  const normalize = (title: string) =>
    title
      .replace(/^\d+[.)]?\s*/, "")
      .replace(/[*_]/g, "")
      .trim()
      .toLowerCase()
      .replace(/^value proposition$/, "value propositions");
  const arranged = blocks.map((title) => ({
    title,
    sections: parsedSections.filter(
      (section) => normalize(section.title) === normalize(title),
    ),
  }));
  const extraSections = parsedSections.filter(
    (section) =>
      !blocks.some((title) => normalize(title) === normalize(section.title)),
  );
  return (
    <div className="manifest-canvas">
      {generationState && (
        <DocumentGenerationNotice
          layout="inline"
          state={generationState}
          title="Business Model Canvas"
          variant="business-model-canvas"
        />
      )}
      <header className="manifest-document-header">
        <div>
          <h3>Business Model Canvas</h3>
          <p>A working view of your business model</p>
        </div>
      </header>
      <div className="manifest-canvas-grid">
        {arranged.map(({ title, sections }) => (
          <section
            className="manifest-canvas-block"
            data-block={normalize(title)}
            key={title}
          >
            <h4>{title}</h4>
            {normalize(title) === "key partners" && (
              <KeyPartnerConnections
                suggestedServiceIds={sections.flatMap((section) => section.suggestedServiceIds)}
              />
            )}
            <div className="manifest-document-body">
              {sections.length ? (
                sections.map((section, index) => (
                  <React.Fragment key={index}>
                    <DocumentMarkdown content={section.content} />
                  </React.Fragment>
                ))
              ) : (
                <p className="text-gray500">Not yet specified</p>
              )}
            </div>
          </section>
        ))}
      </div>
      {extraSections.map((section, index) => (
        <section className="manifest-document-body" key={index}>
          <h4>{section.title}</h4>
          <DocumentMarkdown content={section.content} />
        </section>
      ))}
      <p className="manifest-canvas-attribution">
        Business Model Canvas by{" "}
        <a
          href="https://www.strategyzer.com/library/the-business-model-canvas"
          target="_blank"
          rel="noreferrer"
        >
          Strategyzer
        </a>{" "}
        · Adapted layout ·{" "}
        <a
          href="https://creativecommons.org/licenses/by-sa/3.0/"
          target="_blank"
          rel="noreferrer"
        >
          CC BY-SA 3.0
        </a>
      </p>
    </div>
  );
};
