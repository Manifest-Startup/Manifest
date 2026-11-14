import PageHeader from "features/common-ui/PageHeader";
import React from "react";
import { Link, useLocation } from "react-router-dom";

import MarkdownDocument from "./MarkdownDocument";

const legalTabs = [
  { id: "terms", label: "Terms of Service", route: "/legal/terms", path: "/docs/TERMS_OF_SERVICE.md", title: "Manifest Terms of Service" },
  { id: "privacy", label: "Privacy Policy", route: "/legal/privacy", path: "/docs/PRIVACY_POLICY.md", title: "Manifest Privacy Policy" },
] as const;

const LegalDocumentPage: React.FC = () => {
  const location = useLocation();
  const activeDocument = legalTabs.find((tab) => location.pathname === tab.route) ?? legalTabs[0];

  return (
    <div className="manifest-page">
      <div className="manifest-page-shell">
        <PageHeader eyebrow="Legal" title={activeDocument.label} description="How Manifest handles your rights, responsibilities, and privacy.">
          {legalTabs.map((tab) => (
            <Link key={tab.id} to={tab.route} aria-current={activeDocument.id === tab.id ? "page" : undefined}
              className={`manifest-control ${activeDocument.id === tab.id ? "manifest-control-primary" : "manifest-control-secondary"}`}>
              {tab.label}
            </Link>
          ))}
        </PageHeader>

        <MarkdownDocument path={activeDocument.path} title={activeDocument.title} />
      </div>
    </div>
  );
};

export default LegalDocumentPage;
