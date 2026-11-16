import { createLogger } from 'features/core/logError';

const logger = createLogger('errorHandlers');

// Common error handling patterns
export const handleApiError = (
  error: any, 
  context: string, 
  setMessage: (message: string, type: 'error' | 'success' | 'info') => void,
  fallbackMessage = "An error occurred. Please try again."
) => {
  logger.error(`${context} failed:`, error);
  
  // Extract error message from different error formats
  let errorMessage = fallbackMessage;
  
  if (error?.data?.detail) {
    errorMessage = error.data.detail;
  } else if (error?.message) {
    errorMessage = error.message;
  } else if (typeof error === 'string') {
    errorMessage = error;
  }
  
  setMessage(errorMessage, "error");
  return errorMessage;
};

// Handle navigation errors
export const handleNavigationError = (
  error: any,
  path: string,
  setMessage: (message: string, type: 'error' | 'success' | 'info') => void
) => {
  logger.error(`Navigation failed to ${path}:`, error);
  setMessage(`Navigation error: Unable to go to ${path}`, "error");
};

// Handle form validation errors
export const handleValidationError = (
  field: string,
  message: string,
  setMessage: (message: string, type: 'error' | 'success' | 'info') => void
) => {
  logger.warn(`Validation error for ${field}:`, message);
  setMessage(message, "error");
};

// Handle authentication errors
export const handleAuthError = (
  error: any,
  setMessage: (message: string, type: 'error' | 'success' | 'info') => void
) => {
  logger.error("Authentication error:", error);
  
  let message = "Authentication failed. Please try again.";
  
  if (error?.status === 401) {
    message = "Your session has ended. Please sign in again.";
  } else if (error?.status === 403) {
    message = "Access denied. Please log in again.";
  } else if (error?.data?.detail) {
    message = error.data.detail;
  }
  
  setMessage(message, "error");
};

// Handle network errors
export const handleNetworkError = (
  error: any,
  setMessage: (message: string, type: 'error' | 'success' | 'info') => void
) => {
  logger.error("Network error:", error);
  
  let message = "Network error. Please check your connection.";
  
  if (error?.status === 0) {
    message = "Unable to connect to server. Please check your internet connection.";
  } else if (error?.status >= 500) {
    message = "Server error. Please try again later.";
  }
  
  setMessage(message, "error");
};

// Generic error handler with retry logic
export const handleErrorWithRetry = async <T>(
  operation: () => Promise<T>,
  context: string,
  setMessage: (message: string, type: 'error' | 'success' | 'info') => void,
  maxRetries = 3,
  retryDelay = 1000
): Promise<T | null> => {
  let lastError: any;
  
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      logger.log(`${context} attempt ${attempt}/${maxRetries}`);
      const result = await operation();
      logger.log(`${context} succeeded on attempt ${attempt}`);
      return result;
    } catch (error) {
      lastError = error;
      logger.warn(`${context} failed on attempt ${attempt}:`, error);
      
      if (attempt < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, retryDelay * attempt));
      }
    }
  }
  
  logger.error(`${context} failed after ${maxRetries} attempts:`, lastError);
  handleApiError(lastError, context, setMessage);
  return null;
}; 