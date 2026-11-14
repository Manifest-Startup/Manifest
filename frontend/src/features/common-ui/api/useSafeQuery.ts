import { useEffect, useRef } from 'react';
import { DocumentNode } from 'graphql';
import type { OperationVariables } from '@apollo/client';
import { useQuery as apolloUseQuery } from '@apollo/client/react';
import { handleApiError } from 'features/core/errorHandlers';
import { useMessage } from 'features/notifications/context/MessageContext';
import { createLogger } from 'features/core/logError';

const logger = createLogger('useSafeQuery');

type SafeQueryOptions<TData, TVariables extends OperationVariables> =
  apolloUseQuery.Options<TData, TVariables> & {
    onCompleted?: (data: TData) => void;
    onError?: (error: Error) => void;
  };

export function useSafeQuery<TData = any, TVariables extends OperationVariables = OperationVariables>(
  query: DocumentNode,
  options?: SafeQueryOptions<TData, TVariables>,
) {
  const { setMessage } = useMessage();
  const { onCompleted, onError, ...queryOptions } = options || {};
  // Preserve this wrapper's optional-options API while Apollo's public hook
  // uses conditional overloads for required GraphQL variables.
  // No caller sets `returnPartialData`, so — like Apollo's own overloads —
  // `data` is never in the "partial" state.
  const useTypedQuery = apolloUseQuery as (
    query: DocumentNode,
    options?: apolloUseQuery.Options<TData, TVariables>,
  ) => apolloUseQuery.Result<TData, TVariables, 'empty' | 'complete' | 'streaming'>;
  const result = useTypedQuery(query, queryOptions as apolloUseQuery.Options<TData, TVariables>);
  const handlers = useRef({ onCompleted, onError, setMessage });
  const delivered = useRef<unknown>(undefined);

  useEffect(() => {
    handlers.current = { onCompleted, onError, setMessage };
  });

  // Apollo 4 removed useQuery callbacks. Deliver the existing wrapper's
  // callbacks after render, including cached results and refetches. Callback
  // identity must not retrigger delivery (most callers pass inline functions).
  useEffect(() => {
    if (options?.skip || result.loading) {
      delivered.current = undefined;
      return;
    }
    const value = result.error || (result.dataState === 'complete' ? result.data : undefined);
    if (value === undefined || delivered.current === value) return;
    delivered.current = value;
    if (result.error) {
      logger.error('GraphQL query failed', result.error);
      handleApiError(result.error, 'GraphQL query', handlers.current.setMessage);
      handlers.current.onError?.(result.error);
    } else {
      handlers.current.onCompleted?.(result.data as TData);
    }
  }, [options?.skip, result.loading, result.error, result.data, result.dataState]);

  return result;
}
