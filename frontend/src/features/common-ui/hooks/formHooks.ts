import { useState, useCallback } from 'react';
import { createLogger } from 'features/core/logError';

const logger = createLogger('formHooks');

// Custom hook for managing form state with validation
export const useFormState = <T extends Record<string, any>>(initialState: T) => {
  const [formData, setFormData] = useState<T>(initialState);
  const [errors, setErrors] = useState<Partial<Record<keyof T, string>>>({});

  const updateField = useCallback((field: keyof T, value: any) => {
    logger.log('updateField called', { field, value });
    setFormData(prev => ({ ...prev, [field]: value }));
    // Clear error for this field when user starts typing
    setErrors(prev => {
      if (prev[field]) {
        return { ...prev, [field]: undefined };
      }
      return prev;
    });
  }, []);

  const updateMultipleFields = useCallback((updates: Partial<T>) => {
    logger.log('updateMultipleFields called', updates);
    setFormData(prev => ({ ...prev, ...updates }));
  }, []);

  const setFieldError = useCallback((field: keyof T, error: string) => {
    logger.log('setFieldError called', { field, error });
    setErrors(prev => ({ ...prev, [field]: error }));
  }, []);

  const clearErrors = useCallback(() => {
    logger.log('clearErrors called');
    setErrors({});
  }, []);

  const resetForm = useCallback(() => {
    logger.log('resetForm called');
    setFormData(initialState);
    setErrors({});
  }, [initialState]);

  return {
    formData,
    errors,
    updateField,
    updateMultipleFields,
    setFieldError,
    clearErrors,
    resetForm,
    setFormData
  };
};

// Custom hook for handling form submission with loading state
export const useFormSubmission = <T, R>(
  submitFn: (data: T) => Promise<R>,
  onSuccess?: (result: R) => void,
  onError?: (error: any) => void
) => {
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = useCallback(async (data: T) => {
    logger.log('handleSubmit called', { data });
    setIsSubmitting(true);
    
    try {
      const result = await submitFn(data);
      logger.log('submitFn succeeded', result);
      onSuccess?.(result);
      return result;
    } catch (error) {
      logger.error('submitFn failed:', error);
      onError?.(error);
      throw error;
    } finally {
      setIsSubmitting(false);
    }
  }, [submitFn, onSuccess, onError]);

  return {
    isSubmitting,
    handleSubmit
  };
};

// Custom hook for input change handlers
export const useInputHandlers = <T extends Record<string, any>>(
  updateField: (field: keyof T, value: any) => void
) => {
  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    logger.log('handleInputChange called', { name, value });
    updateField(name as keyof T, value);
  }, [updateField]);

  const handleTextAreaChange = useCallback((field: keyof T) => (value: string) => {
    logger.log('handleTextAreaChange called', { field, value });
    updateField(field, value);
  }, [updateField]);

  return {
    handleInputChange,
    handleTextAreaChange
  };
}; 