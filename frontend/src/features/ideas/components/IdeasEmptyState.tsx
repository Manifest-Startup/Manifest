import React, { useState } from "react";

import Button from "features/common-ui/Button";
import { PlusIcon } from "features/common-ui/icons";
import { useCreateIdea } from "features/ideas/hooks/useCreateIdea";

/** Calm canvas shown beside the ideas sidebar when no idea is open. */
const IdeasEmptyState: React.FC = () => {
  const { createAndOpen } = useCreateIdea();
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    setCreating(true);
    await createAndOpen("empty_workspace");
    setCreating(false);
  };

  return (
    <section className="manifest-ideas-empty" aria-labelledby="ideas-empty-title" data-testid="ideas-empty-workspace">
      <div className="manifest-ideas-empty-inner">
        <div className="manifest-ideas-empty-glyph" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
            <path d="M14 3v5h5" />
            <path d="M9 13h6M9 17h4" />
          </svg>
        </div>
        <h2 id="ideas-empty-title" className="manifest-ideas-empty-title">Select an idea</h2>
        <p className="manifest-ideas-empty-copy">Pick one from the list to keep building, or start something new.</p>
        <Button variant="primary" onClick={handleCreate} disabled={creating} className="manifest-ideas-empty-action">
          <PlusIcon className="h-4 w-4" />
          New idea
        </Button>
      </div>
    </section>
  );
};

export default IdeasEmptyState;
