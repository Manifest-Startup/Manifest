// utils/logError.ts
export function logError(context: string, error: any, extra?: Record<string, any>) {
  // Log error with context, stack, and any extra info
  const isProduction = process.env.NODE_ENV === 'production';
  const shouldWriteConsole =
    process.env.REACT_APP_SILENT_LOGGER !== 'true' &&
    process.env.NODE_ENV !== 'test' &&
    !isProduction;

  if (shouldWriteConsole) {
    if (error instanceof Error) {
      console.error(`[Error] ${context}:`, error.message, error.stack, extra || '');
    } else {
      console.error(`[Error] ${context}:`, error, extra || '');
    }
  }
}

// Utility function to create a component-specific logger
export const createLogger = (componentName: string) => {
  const isProduction = process.env.NODE_ENV === 'production';
  const shouldWriteConsole =
    process.env.REACT_APP_SILENT_LOGGER !== 'true' &&
    process.env.NODE_ENV !== 'test' &&
    !isProduction;
  const shouldBufferLogs = !isProduction;

  const pushToLogBuffer = (level: string, message: string, data?: any) => {
    if (typeof window === 'undefined') {
      return;
    }

    if (shouldBufferLogs) {
      const payload = { ts: Date.now(), level, component: componentName, message, data };
      (window as any).__LOGS__ = (window as any).__LOGS__ || [];
      (window as any).__LOGS__.push(payload);
      (window as any).__LOGS__ = (window as any).__LOGS__.slice(-500);
    }

    // Forward to Sentry in production if available.
    if (isProduction && (window as any).Sentry?.captureMessage) {
      (window as any).Sentry.captureMessage(`${level.toUpperCase()} [${componentName}] ${message}`, {
        extra: data,
        level: level === 'error' ? 'error' : 'info'
      });
    }
  };

  return {
    log: (message: string, data?: any) => {
      if (shouldWriteConsole) {
        console.log(`[${componentName}] ${message}`, data);
      }
      pushToLogBuffer('log', message, data);
    },
    warn: (message: string, data?: any) => {
      if (shouldWriteConsole) {
        console.warn(`[${componentName}] ${message}`, data);
      }
      pushToLogBuffer('warn', message, data);
    },
    error: (message: string, error?: any, context?: any) => {
      if (shouldWriteConsole) {
        console.error(`[${componentName}] ${message}:`, error, context);
      }
      pushToLogBuffer('error', message, { error, context });
    },
    debug: (message: string, data?: any) => {
      if (shouldWriteConsole) {
        console.debug(`[${componentName}] ${message}`, data);
      }
      pushToLogBuffer('debug', message, data);
    }
  };
}; 
