import React from "react";
import { useQuery, useReactiveVar } from "@apollo/client/react";
import ReactMarkdown from "react-markdown";
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

interface BusinessModelCanvasDisplayProps {
  content: any;
  fallbackMessage: string;
  generationState?: DocumentGenerationState | null;
}

interface SuggestedIntegrationChipsProps {
  serviceIds: string[];
}

const SuggestedIntegrationChips: React.FC<SuggestedIntegrationChipsProps> = ({
  serviceIds,
}) => {
  const { isLoggedIn } = useReactiveVar(userVar);
  const { data } = useQuery(GET_INTEGRATIONS, {
    skip: !isLoggedIn || serviceIds.length === 0,
  });

  const connectedServiceIds = new Set(
    data?.integrations?.map(
      (integration: { serviceId: string }) => integration.serviceId,
    ) || [],
  );

  const suggestedIntegrations = serviceIds
    .map((serviceId) => getIntegrationCatalogEntry(serviceId))
    .filter(
      (integration): integration is NonNullable<typeof integration> =>
        !!integration,
    );

  if (suggestedIntegrations.length === 0) {
    return null;
  }

  return (
    <div className="mb-4">
      <div className="flex flex-wrap gap-2">
        {suggestedIntegrations.map((integration) => {
          const isConnected = connectedServiceIds.has(integration.id);
          return (
            <Link
              key={integration.id}
              to={`/account?focusIntegration=${encodeURIComponent(integration.id)}`}
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${
                isConnected
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200"
                  : "border-gray-200 bg-white text-gray-700 hover:border-gray-300 hover:bg-gray-50 dark:border-neutral700 dark:bg-neutral900 dark:text-gray-200 dark:hover:bg-neutral800"
              }`}
            >
              <span>{integration.name}</span>
              <span className="text-[0.65rem] uppercase tracking-[0.14em] opacity-80">
                {isConnected ? "Connected" : "Connect"}
              </span>
            </Link>
          );
        })}
      </div>
    </div>
  );
};

export const BusinessModelCanvasDisplay: React.FC<
  BusinessModelCanvasDisplayProps
> = ({ content, fallbackMessage, generationState }) => {
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
        <ReactMarkdown>{content}</ReactMarkdown>
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
            <div className="manifest-document-body">
              {sections.length ? (
                sections.map((section, index) => (
                  <React.Fragment key={index}>
                    <DocumentMarkdown content={section.content} />
                    {section.suggestedServiceIds.length > 0 && (
                      <details>
                        <summary>Suggested integrations</summary>
                        <SuggestedIntegrationChips
                          serviceIds={section.suggestedServiceIds}
                        />
                      </details>
                    )}
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
