import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { logError } from '../core/logError';

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

interface PatentPdfViewerProps {
  fileUrl: string | Blob;
  height?: number;
}

const PatentPdfViewer: React.FC<PatentPdfViewerProps> = ({ fileUrl, height = 600 }) => {
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [useNativeFallback, setUseNativeFallback] = useState(false);
  const [resolvedUrl, setResolvedUrl] = useState(typeof fileUrl === 'string' ? fileUrl : '');
  const [numPages, setNumPages] = useState(0);
  const [pageWidth, setPageWidth] = useState<number | undefined>(undefined);
  const containerRef = useRef<HTMLDivElement>(null);

  const fileSource = useMemo(() => {
    if (!resolvedUrl) {
      return undefined;
    }
    return resolvedUrl;
  }, [resolvedUrl]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setUseNativeFallback(false);
    setNumPages(0);

    if (typeof fileUrl === 'string') {
      setResolvedUrl(fileUrl);
      return;
    }

    const objectUrl = URL.createObjectURL(fileUrl);
    setResolvedUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [fileUrl]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) {
      return undefined;
    }

    const measure = () => {
      const w = el.clientWidth;
      if (w > 0) {
        setPageWidth(w);
      }
    };

    measure();
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null;
    ro?.observe(el);
    window.addEventListener('resize', measure);
    return () => {
      ro?.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [resolvedUrl]);

  const onDocumentLoadSuccess = useCallback(() => {
    setLoading(false);
    setError(null);
  }, []);

  const onDocumentLoadError = useCallback((e: Error) => {
    setError('Failed to load PDF.');
    setUseNativeFallback(true);
    logError('PatentPdfViewer: Failed to load PDF', e);
    setLoading(false);
  }, []);

  if (!resolvedUrl) {
    return <div style={{ minHeight: height, background: '#f5f5f3' }} />;
  }

  if (useNativeFallback) {
    return (
      <div style={{ minHeight: height, overflow: 'hidden', background: '#f5f5f3' }}>
        <iframe
          src={resolvedUrl}
          title="Patent PDF"
          style={{ width: '100%', height, border: 0, background: '#ffffff' }}
        />
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      style={{
        minHeight: height,
        maxHeight: height,
        overflowY: 'auto',
        background: '#f5f5f3',
      }}
    >
      <Document
        file={fileSource}
        loading={
          <div style={{ textAlign: 'center', padding: 16, color: '#4b5563' }}>Loading PDF…</div>
        }
        onLoadSuccess={(pdf) => {
          setNumPages(pdf.numPages);
          onDocumentLoadSuccess();
        }}
        onLoadError={onDocumentLoadError}
        onLoadProgress={() => setLoading(true)}
      >
        {numPages > 0 && pageWidth
          ? Array.from({ length: numPages }, (_, i) => (
              <div key={i + 1} style={{ display: 'flex', justifyContent: 'center', padding: '8px 0' }}>
                <Page pageNumber={i + 1} width={pageWidth} renderTextLayer renderAnnotationLayer />
              </div>
            ))
          : null}
      </Document>
      {loading && numPages === 0 && (
        <div style={{ textAlign: 'center', padding: 16, color: '#4b5563' }}>Loading PDF...</div>
      )}
      {error && <div style={{ color: '#b91c1c', textAlign: 'center', padding: 16 }}>{error}</div>}
    </div>
  );
};

export default PatentPdfViewer;
