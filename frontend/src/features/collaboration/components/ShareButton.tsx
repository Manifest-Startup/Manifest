import React, { useEffect, useState } from 'react';
import Button from 'features/common-ui/Button';
import { ShareIcon } from 'features/common-ui/icons';
import { subscribeToVoiceCollaborationCommand } from 'features/voice/voiceCommandEvents';
import ShareModal from './ShareModal';

interface ShareButtonProps {
  ideaId: string;
  className?: string;
}

export const ShareButton: React.FC<ShareButtonProps> = ({ ideaId, className = '' }) => {
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    return subscribeToVoiceCollaborationCommand((detail) => {
      if (detail.ideaId === ideaId && detail.target === 'share') {
        setIsOpen(true);
      }
    });
  }, [ideaId]);

  return (
    <>
      <Button
        aria-label="Share idea"
        onClick={() => setIsOpen(true)}
        data-testid="share-button"
        className={`h-11 w-11 p-0 text-gray500 dark:text-gray400 ${className}`}
        title="Share"
        type="button"
        variant="ghost"
      >
        <ShareIcon className="h-4 w-4" />
      </Button>

      <ShareModal ideaId={ideaId} isOpen={isOpen} onClose={() => setIsOpen(false)} />
    </>
  );
};

export default ShareButton;
