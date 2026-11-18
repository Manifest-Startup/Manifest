import React, { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownDocumentProps {
  path: string;
  title: string;
}

const MarkdownDocument: React.FC<MarkdownDocumentProps> = ({ path, title }) => {
  const [content, setContent] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    const load = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await fetch(path, { signal: controller.signal });
        if (!response.ok) {
          throw new Error(`Failed to load ${title.toLowerCase()}.`);
        }

        const text = await response.text();
        setContent(text);
      } catch (loadError) {
        if (controller.signal.aborted) {
          return;
        }

        setError(loadError instanceof Error ? loadError.message : `Failed to load ${title.toLowerCase()}.`);
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      }
    };

    void load();

    return () => controller.abort();
  }, [path, title]);

  if (isLoading) {
    return (
      <div className="manifest-reading-surface">
        <p className="manifest-kicker">{title}</p>
        <p className="mt-4 text-sm text-gray500 dark:text-gray400">Loading documentation...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="manifest-reading-surface">
        <p className="manifest-kicker">{title}</p>
        <p className="mt-4 text-sm text-danger">{error}</p>
      </div>
    );
  }

  return (
    <div className="manifest-reading-surface">
      <div className="manifest-markdown">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ children, href }) => (
              <a
                href={href}
                target={href?.startsWith("http") ? "_blank" : undefined}
                rel={href?.startsWith("http") ? "noreferrer" : undefined}
              >
                {children}
              </a>
            ),
            table: ({ children }) => (
              <div className="manifest-markdown-table">
                <table>{children}</table>
              </div>
            ),
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </div>
  );
};

export default MarkdownDocument;
