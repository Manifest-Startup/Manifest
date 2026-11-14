import React, { useState } from 'react';
import { useMutation, useReactiveVar } from '@apollo/client/react';
import { TOGGLE_FOLLOW } from 'features/core/apollo/queries';
import { userVar } from 'features/core/apollo/localState';
import { useMessage } from 'features/notifications/context/MessageContext';

interface FollowButtonProps {
  userId: string;
  isFollowing: boolean;
  onFollowChange?: (following: boolean) => void;
  size?: 'sm' | 'md' | 'lg';
  variant?: 'default' | 'outline';
}

const FollowButton: React.FC<FollowButtonProps> = ({
  userId,
  isFollowing: initialFollowing,
  onFollowChange,
  size = 'md',
  variant = 'default'
}) => {
  const [isFollowing, setIsFollowing] = useState(initialFollowing);
  const [isHovering, setIsHovering] = useState(false);
  const { userData } = useReactiveVar(userVar);
  const { setMessage } = useMessage();
  const isSelf = Boolean(userData?.userId && userData.userId === userId);
  const [toggleFollow, { loading }] = useMutation(TOGGLE_FOLLOW);

  const handleClick = async () => {
    if (isSelf) return;

    try {
      const result = await toggleFollow({
        variables: { followedId: userId }
      });
      
      const newFollowing = result?.data?.toggleFollow?.following ?? !isFollowing;
      setIsFollowing(newFollowing);
      onFollowChange?.(newFollowing);
    } catch (error) {
      console.error('Failed to toggle follow:', error);
      setMessage('Unable to update follow status right now.', 'error');
    }
  };

  const sizeClasses = {
    sm: 'px-3 py-1 text-xs',
    md: 'px-4 py-1.5 text-sm',
    lg: 'px-6 py-2 text-base'
  };

  const getButtonStyles = () => {
    if (isFollowing) {
      if (isHovering) {
        return 'bg-red-50 text-red-600 border-red-300 hover:bg-red-100';
      }
      return variant === 'outline'
        ? 'bg-transparent text-gray-700 border-gray-300 hover:bg-gray-50'
        : 'bg-gray-100 text-gray-700 border-gray-300 hover:bg-gray-200';
    }
    return variant === 'outline'
      ? 'bg-transparent text-blue-600 border-blue-600 hover:bg-blue-50'
      : 'bg-blue-600 text-white border-blue-600 hover:bg-blue-700';
  };

  const getButtonText = () => {
    if (loading) return 'Loading...';
    if (isSelf) return 'You';
    if (isFollowing) {
      return isHovering ? 'Unfollow' : 'Following';
    }
    return 'Follow';
  };

  return (
    <button
      onClick={handleClick}
      disabled={loading || isSelf}
      onMouseEnter={() => setIsHovering(true)}
      onMouseLeave={() => setIsHovering(false)}
      className={`
        ${sizeClasses[size]}
        ${getButtonStyles()}
        font-semibold rounded-full border-2 transition-all duration-200
        disabled:opacity-50 disabled:cursor-not-allowed
      `}
      title={isSelf ? 'You cannot follow yourself' : undefined}
    >
      {getButtonText()}
    </button>
  );
};

export default FollowButton;
