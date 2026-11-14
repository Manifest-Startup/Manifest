import React, { useMemo } from 'react';
import { createLogger } from 'features/core/logError';

export const withRenderLog = <P extends object>(
  componentName: string,
  Wrapped: React.ComponentType<P>
): React.FC<P> => {
  const ComponentWithLog: React.FC<P> = (props) => {
    const logger = useMemo(() => createLogger(componentName), []);
    logger.log('rendered');
    return <Wrapped {...props} />;
  };
  ComponentWithLog.displayName = `WithRenderLog(${componentName})`;
  return ComponentWithLog;
}; 