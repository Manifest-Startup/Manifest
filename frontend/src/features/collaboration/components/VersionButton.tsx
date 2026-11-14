import React, { useEffect, useState } from 'react';
import Button from 'features/common-ui/Button';
import { HistoryIcon } from 'features/common-ui/icons';
import { subscribeToVoiceCollaborationCommand } from 'features/voice/voiceCommandEvents';
import VersionHistory from './VersionHistory';

interface VersionButtonProps {
  ideaId: string;
  className?: string;
  onVersionRestored?: () => void;
}

export const VersionButton: React.FC<VersionButtonProps> = ({ 
  ideaId, 
  className = '',
  onVersionRestored 
}) => {
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    return subscribeToVoiceCollaborationCommand((detail) => {
      if (detail.ideaId === ideaId && detail.target === 'history') {
        setIsOpen(true);
      }
    });
  }, [ideaId]);

  return (
    <>
      <Button
        aria-label="Open history"
        onClick={() => setIsOpen(true)}
        data-testid="version-button"
        className={`h-11 w-11 p-0 text-gray500 dark:text-gray400 ${className}`}
        title="Version History"
        type="button"
        variant="ghost"
      >
        <HistoryIcon className="h-4 w-4" />
      </Button>

      <VersionHistory 
        ideaId={ideaId} 
        isOpen={isOpen} 
        onClose={() => setIsOpen(false)}
        onVersionRestored={onVersionRestored}
      />
    </>
  );
};

export default VersionButton;
