import { NavigateFunction } from 'react-router-dom';
import { handleNavigationError } from 'features/core/errorHandlers';
import { createLogger } from 'features/core/logError';

const logger = createLogger('safeNavigate');

export const safeNavigate = (
  navigate: NavigateFunction,
  setMessage: (msg: string, type: 'error' | 'success' | 'info') => void,
  path: string
) => {
  try {
    logger.log(`Navigating to ${path}`);
    navigate(path);
  } catch (error) {
    handleNavigationError(error, path, setMessage);
  }
}; 