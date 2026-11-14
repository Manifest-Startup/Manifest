import React, { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownDocumentProps {
  path: string;
  title: string;
}

const headingStyles = {
  h1: "text-3xl font-semibold tracking-[-0.03em] text-neutral900 dark:text-white",
  h2: "mt-10 text-2xl font-semibold tracking-[-0.03em] text-neutral900 dark:text-white",
  h3: "mt-8 text-xl font-semibold text-neutral900 dark:text-white",
  h4: "mt-6 text-lg font-semibold text-neutral900 dark:text-white",
};

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
      <div className="manifest-prose text-sm leading-7 text-gray500 dark:text-gray300">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ children }) => <h2 className={headingStyles.h1}>{children}</h2>,
            h2: ({ children }) => <h2 className={headingStyles.h2}>{children}</h2>,
            h3: ({ children }) => <h3 className={headingStyles.h3}>{children}</h3>,
            h4: ({ children }) => <h4 className={headingStyles.h4}>{children}</h4>,
            p: ({ children }) => <p className="mt-4 text-sm leading-7 text-gray500 dark:text-gray300">{children}</p>,
            ul: ({ children }) => <ul className="mt-4 list-disc space-y-2 pl-5">{children}</ul>,
            ol: ({ children }) => <ol className="mt-4 list-decimal space-y-2 pl-5">{children}</ol>,
            li: ({ children }) => <li>{children}</li>,
            a: ({ children, href }) => (
              <a
                href={href}
                target={href?.startsWith("http") ? "_blank" : undefined}
                rel={href?.startsWith("http") ? "noreferrer" : undefined}
                className="font-semibold text-accent-700 underline decoration-accent-300 underline-offset-4 dark:text-accent-300"
              >
                {children}
              </a>
            ),
            code: ({ children }) => (
              <code className="rounded bg-theme-tertiary px-1 py-0.5 font-mono text-[0.875em] text-theme-primary">{children}</code>
            ),
            pre: ({ children }) => (
              <pre className="mt-5 overflow-x-auto rounded-lg bg-neutral900 px-4 py-4 text-sm text-gray100 dark:bg-black [&_code]:bg-transparent [&_code]:p-0 [&_code]:text-gray100">
                {children}
              </pre>
            ),
            blockquote: ({ children }) => (
              <blockquote className="mt-5 rounded-r-[1.5rem] border-l-4 border-accent-400 bg-accent-50/70 px-5 py-4 text-sm text-neutral900 dark:bg-accent-900/30 dark:text-gray100">
                {children}
              </blockquote>
            ),
            table: ({ children }) => (
              <div className="mt-5 overflow-x-auto rounded-lg border border-gray200 dark:border-neutral700">
                <table className="w-full border-collapse text-left text-sm">{children}</table>
              </div>
            ),
            thead: ({ children }) => <thead className="bg-white/75 dark:bg-neutral800/90">{children}</thead>,
            tbody: ({ children }) => <tbody className="bg-white/70 dark:bg-neutral900/75">{children}</tbody>,
            tr: ({ children }) => <tr className="border-t border-gray200 dark:border-neutral700">{children}</tr>,
            th: ({ children }) => (
              <th className="px-4 py-3 text-xs font-medium text-gray500 dark:text-gray400">{children}</th>
            ),
            td: ({ children }) => <td className="px-4 py-3 align-top text-gray500 dark:text-gray300">{children}</td>,
            hr: () => <hr className="mt-8 border-gray200 dark:border-neutral700" />,
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </div>
  );
};

export default MarkdownDocument;
