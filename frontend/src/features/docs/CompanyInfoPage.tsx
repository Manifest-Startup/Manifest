import PageHeader from "features/common-ui/PageHeader";
import React from "react";
import { Link, useLocation } from "react-router-dom";

import MarkdownDocument from "./MarkdownDocument";

// Copy is served by the backend (backend/app/services/agent_content.py) as
// Markdown so the React page, the no-JavaScript shell and the /*.md twins
// read by AI agents always say the same thing.
const companyTabs = [
  { id: "about", label: "About", route: "/about", path: "/about.md", title: "About Manifest" },
  { id: "contact", label: "Contact", route: "/contact", path: "/contact.md", title: "Contact Manifest" },
] as const;

const CompanyInfoPage: React.FC = () => {
  const location = useLocation();
  const active = companyTabs.find((tab) => location.pathname === tab.route) ?? companyTabs[0];

  return (
    <div className="manifest-page">
      <div className="manifest-page-shell">
        <PageHeader eyebrow="Company" title={active.title} description="Who we are and how to reach us.">
          {companyTabs.map((tab) => (
            <Link key={tab.id} to={tab.route} aria-current={active.id === tab.id ? "page" : undefined}
              className={`manifest-control ${active.id === tab.id ? "manifest-control-primary" : "manifest-control-secondary"}`}>
              {tab.label}
            </Link>
          ))}
        </PageHeader>

        <MarkdownDocument path={active.path} title={active.title} />
      </div>
    </div>
  );
};

export default CompanyInfoPage;
