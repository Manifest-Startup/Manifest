import React, { Component, ErrorInfo, ReactNode } from "react";
import { createLogger } from "features/core/logError";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
}

const logger = createLogger('ErrorBoundary');

class ErrorBoundary extends Component<Props, State> {
  public state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    // Update state so the next render shows the fallback UI.
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // You can also log the error to an error reporting service
    logger.error('Unhandled runtime error', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      // Render fallback UI
      return (
        this.props.fallback ?? (
          <div className="flex flex-col items-center justify-center h-full text-center p-4">
            <h1 className="text-2xl font-semibold mb-2">Something went wrong.</h1>
            <p className="text-gray-600">Please refresh the page or try again later.</p>
          </div>
        )
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary; 