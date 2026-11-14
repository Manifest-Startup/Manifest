import React, { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  eyebrow?: string;
  description?: string;
  children?: ReactNode;
}

const PageHeader: React.FC<PageHeaderProps> = ({ title, eyebrow, description, children }) => (
  <header className="manifest-page-header">
    {eyebrow ? <p className="manifest-kicker mb-2">{eyebrow}</p> : null}
    <h1 className="manifest-page-title">{title}</h1>
    {description ? <p className="manifest-subtitle mt-2 max-w-3xl text-sm">{description}</p> : null}
    {children ? <div className="mt-4 flex flex-wrap items-center gap-2">{children}</div> : null}
  </header>
);

export default PageHeader;
