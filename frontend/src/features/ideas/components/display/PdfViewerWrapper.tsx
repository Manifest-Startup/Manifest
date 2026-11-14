import React, { Suspense, useEffect, useMemo } from "react";
import { useMessage } from "features/notifications/context/MessageContext";
import { resolveBackendAssetUrl } from "features/core/network/urls";
import { DocumentGenerationNotice } from "./DocumentGenerationNotice";

const PatentPdfViewer = React.lazy(
  () => import("features/common-ui/PatentPdfViewer"),
);

interface PdfViewerWrapperProps {
  description?: string;
  pdf: string | Blob | undefined;
  height: number;
  title: string;
  isLoading: boolean;
  error: any;
}

export const PdfViewerWrapper: React.FC<PdfViewerWrapperProps> = ({
  description,
  pdf,
  height,
  title,
  isLoading,
  error,
}) => {
  const { setMessage } = useMessage();
  const fileUrl = useMemo(() => {
    if (!pdf) {
      return "";
    }

    return typeof pdf === "string"
      ? resolveBackendAssetUrl(pdf)
      : URL.createObjectURL(pdf);
  }, [pdf]);

  useEffect(() => {
    if (error) {
      setMessage(`Failed to load ${title.toLowerCase()}.`, "error");
    }
  }, [error, title, setMessage]);

  useEffect(() => {
    if (!pdf || typeof pdf === "string" || !fileUrl) {
      return undefined;
    }

    return () => URL.revokeObjectURL(fileUrl);
  }, [fileUrl, pdf]);

  if (isLoading) {
    return (
      <DocumentGenerationNotice
        layout="inline"
        state={{
          startedAt: Date.now(),
          pendingDocuments: [title],
          mode: "initial",
        }}
        title={title}
        variant="pdf-packet"
      />
    );
  }

  if (error || !pdf) return null;

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-neutral900 dark:text-white">
            {title}
          </h3>
          {description ? (
            <p className="mt-2 max-w-3xl text-sm leading-6 text-gray600 dark:text-gray300">
              {description}
            </p>
          ) : null}
        </div>
        {typeof fileUrl === "string" ? (
          <div className="flex flex-wrap gap-2">
            <a
              className="inline-flex items-center rounded-md border border-gray200 bg-white px-4 py-2 text-sm font-medium text-neutral900 transition-colors hover:border-neutral400 dark:border-neutral700 dark:bg-neutral900 dark:text-white"
              href={fileUrl}
              rel="noopener noreferrer"
              target="_blank"
            >
              Open PDF
            </a>
            <a
              className="inline-flex items-center rounded-md bg-neutral900 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-neutral800 dark:bg-white dark:text-neutral900 dark:hover:bg-neutral100"
              download
              href={fileUrl}
            >
              Download
            </a>
          </div>
        ) : null}
      </div>
      <div className="overflow-hidden rounded-md border border-gray200 bg-white dark:border-neutral700 dark:bg-neutral900">
        <Suspense
          fallback={
            <div className="p-6 text-center text-sm text-gray500">
              Loading PDF viewer...
            </div>
          }
        >
          <PatentPdfViewer fileUrl={fileUrl} height={height} />
        </Suspense>
      </div>
    </div>
  );
};
