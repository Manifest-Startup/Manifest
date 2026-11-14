import React, { useState } from 'react';
import { useMutation } from '@apollo/client/react';
import { TOGGLE_UPVOTE } from 'features/core/apollo/queries';

interface UpvoteButtonProps {
  ideaId: string;
  initialVoted: boolean;
  initialCount: number;
  onVoteChange?: (voted: boolean, count: number) => void;
  showCount?: boolean;
  size?: 'sm' | 'md' | 'lg';
  variant?: 'default' | 'icon';
}

const UpvoteButton: React.FC<UpvoteButtonProps> = ({
  ideaId,
  initialVoted,
  initialCount,
  onVoteChange,
  showCount = true,
  size = 'md',
  variant = 'default'
}) => {
  const [voted, setVoted] = useState(initialVoted);
  const [count, setCount] = useState(initialCount);
  const [toggleUpvote, { loading }] = useMutation(TOGGLE_UPVOTE);

  const handleClick = async () => {
    try {
      const result = await toggleUpvote({
        variables: { ideaId }
      });
      
      const newVoted = result?.data?.toggleUpvote?.voted ?? !voted;
      const newCount = result?.data?.toggleUpvote?.voteCount ?? count;
      
      setVoted(newVoted);
      setCount(newCount);
      onVoteChange?.(newVoted, newCount);
    } catch (error) {
      console.error('Failed to toggle upvote:', error);
    }
  };

  const sizeClasses = {
    sm: 'w-8 h-8',
    md: 'w-10 h-10',
    lg: 'w-12 h-12'
  };

  const iconSizes = {
    sm: 16,
    md: 20,
    lg: 24
  };

  const isIconVariant = variant === 'icon';

  return (
    <div className="flex flex-col items-center">
      <button
        onClick={handleClick}
        disabled={loading}
        className={`
          ${sizeClasses[size]}
          flex items-center justify-center rounded-full transition-all duration-200
          ${isIconVariant 
            ? `${voted ? 'text-red-500' : 'text-white'} hover:opacity-80` 
            : `${voted 
                ? 'bg-red-100 text-red-500 hover:bg-red-200' 
                : 'bg-gray-100 text-gray-500 hover:bg-gray-200'}`
          }
          disabled:opacity-50 disabled:cursor-not-allowed
        `}
        aria-label={voted ? 'Remove upvote' : 'Upvote'}
      >
        <svg
          width={iconSizes[size]}
          height={iconSizes[size]}
          viewBox="0 0 24 24"
          fill={voted ? 'currentColor' : 'none'}
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
        </svg>
      </button>
      {showCount && (
        <span className={`text-sm font-semibold mt-1 ${isIconVariant ? 'text-white' : (voted ? 'text-red-500' : 'text-gray-500')}`}>
          {count}
        </span>
      )}
    </div>
  );
};

export default UpvoteButton;
