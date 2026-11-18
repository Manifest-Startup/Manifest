import React, { useEffect, useState } from "react";

import { useSafeQuery } from "features/common-ui/api/useSafeQuery";
import { GET_PROVISIONAL_PATENT } from "features/core/apollo/queries";

import {
  DocumentGenerationNotice,
  type DocumentGenerationState,
} from "./DocumentGenerationNotice";
import { MarkdownDisplay } from "./MarkdownDisplay";
import { PdfViewerWrapper } from "./PdfViewerWrapper";

interface ProvisionalPatentDisplayProps {
  ideaId?: string | null;
  fallbackMessage: string;
  generationState?: DocumentGenerationState | null;
}

type PatentTab = {
  description: string;
  id: "specification" | "coversheet";
  title: string;
  url: string;
};

export const ProvisionalPatentDisplay: React.FC<
  ProvisionalPatentDisplayProps
> = ({ ideaId, fallbackMessage, generationState }) => {
  const { data, error, loading } = useSafeQuery(GET_PROVISIONAL_PATENT, {
    variables: { ideaId },
    skip: !ideaId,
    fetchPolicy: "cache-and-network",
  });
  const [activeTab, setActiveTab] = useState<PatentTab["id"] | null>(null);

  const patent = data?.provisionalPatent;
  const tabs: PatentTab[] = [];

  if (patent?.specificationPdf) {
    tabs.push({
      id: "specification",
      title: "Specification PDF",
      description:
        "Formal specification packet with cover page, section headings, and filing-style layout.",
      url: patent.specificationPdf,
    });
  }

  if (patent?.coversheetPdf) {
    tabs.push({
      id: "coversheet",
      title: "USPTO Cover Sheet",
      description:
        "Official provisional application cover sheet template with draft filing placeholders.",
      url: patent.coversheetPdf,
    });
  }

  useEffect(() => {
    if (!tabs.length) {
      setActiveTab(null);
      return;
    }

    if (!activeTab || !tabs.some((tab) => tab.id === activeTab)) {
      setActiveTab(tabs[0].id);
    }
  }, [activeTab, tabs]);

  const activePacket = tabs.find((tab) => tab.id === activeTab) || tabs[0];
  const shouldShowPacketGenerationBanner =
    Boolean(generationState) &&
    Boolean(patent?.provisionalPatent) &&
    tabs.length === 0;

  if (!tabs.length) {
    return (
      <div className="space-y-5">
        {shouldShowPacketGenerationBanner ? (
          <DocumentGenerationNotice
            layout="inline"
            state={generationState as DocumentGenerationState}
            title="Provisional Patent Packet"
            variant="pdf-packet"
          />
        ) : null}
        <MarkdownDisplay
          content={patent?.provisionalPatent}
          fallbackMessage={fallbackMessage}
          generationState={generationState}
          title="Provisional Patent Application"
          variant="legal"
          documentType="provisional_patent"
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {generationState ? (
        <DocumentGenerationNotice
          layout="inline"
          state={generationState}
          title="Provisional Patent Packet"
          variant="pdf-packet"
        />
      ) : null}
      <header className="manifest-document-header">
        <div>
          <h3>Provisional Patent Draft</h3>
          <p>
            U.S. provisional · Review the specification, inventor details and
            required drawings before filing.
          </p>
        </div>
      </header>

      <div className="flex flex-wrap gap-3">
        {tabs.map((tab) => (
          <button
            className={
              tab.id === activeTab
                ? "manifest-document-button bg-neutral900 text-white"
                : "manifest-document-button"
            }
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            type="button"
          >
            {tab.title}
          </button>
        ))}
      </div>

      {activePacket && (
        <PdfViewerWrapper
          description={activePacket.description}
          error={error}
          height={860}
          isLoading={loading && !patent}
          pdf={activePacket.url}
          title={activePacket.title}
        />
      )}

      {patent?.provisionalPatent ? (
        <details>
          <summary className="cursor-pointer text-sm">Draft text</summary>
          <MarkdownDisplay
            className="pt-2"
            content={patent.provisionalPatent}
            fallbackMessage={fallbackMessage}
            title="Draft Text"
            variant="legal"
            documentType="provisional_patent"
          />
        </details>
      ) : null}
    </div>
  );
};
