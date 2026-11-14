import React from "react";

interface IOSPageWrapperProps {
  children: React.ReactNode;
  className?: string;
  showTabBar?: boolean;
}

/**
 * iOS-styled page wrapper with safe area insets and iOS design patterns
 */
const IOSPageWrapper: React.FC<IOSPageWrapperProps> = ({
  children,
  className = "",
  showTabBar = true,
}) => {
  return (
    <div className={`ios-page-wrapper min-h-screen bg-gray-50 dark:bg-neutral900 transition-colors ${className}`}>
      <div className={`ios-content ${showTabBar ? 'pb-20' : 'pb-4'}`}>
        {children}
      </div>
    </div>
  );
};

export default IOSPageWrapper;

