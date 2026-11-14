import PageHeader from "features/common-ui/PageHeader";
import React from "react";
import { Link } from "react-router-dom";

const sections = [
  {
    href: "/docs/guide",
    kicker: "User Guide",
    title: "Learn the workspace",
    description:
      "Start from account setup, then move through the ideas workspace, collaboration, pitch reels, messaging, search, voice, and account tools.",
    bullets: [
      "Getting started and guest mode",
      "Ideas workspace and generated documents",
      "Collaboration, publishing, messaging, and account settings",
    ],
  },
  {
    href: "/docs/api",
    kicker: "API Reference",
    title: "Build an integration",
    description:
      "See which endpoints use session JWTs, where API keys apply, and load the full reference straight from the canonical markdown docs.",
    bullets: [
      "GraphQL, REST, API keys, and voice routes",
      "Tier limits, examples, and error handling",
      "Full synced API and voice references",
    ],
  },
  {
    href: "/legal/terms",
    kicker: "Legal",
    title: "Terms and privacy",
    description:
      "See the user-facing legal documents that cover AI outputs, founder ownership, marketplace risks, optional tracking, retention, and regional privacy concepts.",
    bullets: [
      "Terms of Service for founders, collaborators, and investors",
      "Privacy Policy aligned with product consent controls",
      "Startup-specific disclaimers for AI, equity, and marketplace risk",
    ],
  },
];

const DocsHubPage: React.FC = () => {
  return (
    <div className="manifest-page">
      <div className="manifest-page-shell">
        <PageHeader eyebrow="Manifest" title="Documentation" description="Guides, API reference, and legal information.">
          <Link to="/docs/guide" className="manifest-control manifest-control-primary">Open user guide</Link>
          <Link to="/docs/api" className="manifest-control manifest-control-secondary">Open API reference</Link>
          <Link to="/legal/terms" className="manifest-control manifest-control-ghost">Open legal pages</Link>
        </PageHeader>

        <section className="grid gap-4 lg:grid-cols-3">
          {sections.map((section) => (
            <article key={section.href} className="manifest-panel flex h-full flex-col p-4 sm:p-5">
              <p className="manifest-kicker">{section.kicker}</p>
              <h2 className="mt-3 text-xl font-semibold tracking-[-0.03em] text-neutral900 dark:text-white">{section.title}</h2>
              <p className="manifest-subtitle mt-4 text-sm sm:text-base">{section.description}</p>
              <ul className="mt-4 space-y-2 text-sm leading-7 text-gray500 dark:text-gray300">
                {section.bullets.map((bullet) => (
                  <li key={bullet} className="flex items-start gap-3">
                    <span className="mt-2 h-2 w-2 rounded-full bg-accent-500" aria-hidden="true" />
                    <span>{bullet}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-auto pt-6">
                <Link
                  to={section.href}
                  className="manifest-control manifest-control-secondary"
                >
                  View {section.kicker.toLowerCase()}
                </Link>
              </div>
            </article>
          ))}
        </section>
      </div>
    </div>
  );
};

export default DocsHubPage;
