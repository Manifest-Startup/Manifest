import {
  ApolloClient,
  ApolloLink,
  CombinedGraphQLErrors,
  InMemoryCache,
  ServerError,
  ServerParseError,
  createHttpLink,
  from,
} from '@apollo/client';
import { onError } from '@apollo/client/link/error';
import { announceAiKeyRequired, isAiKeyRequiredMessage } from 'features/ai/aiKeyRequired';
import { handleApiError } from '../errorHandlers';
import { createLogger } from '../logError';
import { userVar } from './localState';
import { setContext } from '@apollo/client/link/context';
import { buildSessionHeaders } from 'features/auth/session';
import { Observable } from 'rxjs';
import { isVaultMode } from 'features/vault/mode';

const logger = createLogger('Apollo');

// Get GraphQL endpoint from environment variable or use default
const getGraphQLEndpoint = () => {
  if (process.env.REACT_APP_GRAPHQL_URL) {
    return process.env.REACT_APP_GRAPHQL_URL;
  }
  return '/graphql';
};

const GRAPHQL_URI = getGraphQLEndpoint();
logger.log(`[Apollo] Using GraphQL endpoint: ${GRAPHQL_URI}`);

// Global error handling link with better error messages.
// Apollo Client 4 passes a single `error`: CombinedGraphQLErrors for GraphQL
// errors, anything else is a network/transport error.
const errorLink = onError(({ error, operation }) => {
  if (CombinedGraphQLErrors.is(error)) {
    if (error.errors.some(err => isAiKeyRequiredMessage(err.message))) {
      announceAiKeyRequired();
    }
    error.errors.forEach(err => {
      logger.error('[GraphQL error]', {
        message: err.message,
        locations: err.locations,
        path: err.path,
        extensions: err.extensions,
        operation: operation?.operationName,
      });
    });
    return;
  }

  const networkError = error;
  const statusCode =
    ServerError.is(networkError) || ServerParseError.is(networkError)
      ? networkError.statusCode
      : undefined;

  // Check for JSON parse errors (empty or incomplete responses)
  const isJsonParseError = networkError.message?.includes('JSON Parse error') ||
                         networkError.message?.includes('Unexpected EOF') ||
                         networkError.message?.includes('Unexpected end of JSON input');

  if (isJsonParseError) {
    logger.error('[JSON Parse error] - Empty or incomplete response', {
      message: networkError.message,
      statusCode,
      operation: operation?.operationName,
      endpoint: GRAPHQL_URI,
    });

    // Enhance the error message for JSON parse errors
    networkError.message = 'Server returned an empty or incomplete response. Please check your connection and try again.';
  } else {
    logger.error('[Network error]', {
      message: networkError.message,
      statusCode,
      result: ServerError.is(networkError) ? networkError.bodyText : undefined,
      operation: operation?.operationName,
      endpoint: GRAPHQL_URI,
    });
  }

  // Log helpful debugging info for production issues
  if (typeof window !== 'undefined') {
    logger.error('[Network error details]', {
      currentUrl: window.location.href,
      graphqlEndpoint: GRAPHQL_URI,
      hasToken: !!localStorage.getItem('access_token'),
    });
  }
});

const httpLink = createHttpLink({
  uri: GRAPHQL_URI,
  credentials: 'include',
});

const authLink = setContext((_, { headers }) => {
  const token =
    typeof window !== 'undefined'
      ? localStorage.getItem('access_token')
      : null;
  return {
    headers: buildSessionHeaders({
      ...(headers as Record<string, string>),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }),
  };
});

// Local vault mode (ADR 0011): the same operations are answered from Markdown files in a
// folder on this computer. The vault code loads only when this browser uses a vault.
const vaultLink = new ApolloLink(
  (operation) =>
    new Observable((observer) => {
      import('features/vault/runtime')
        .then(({ runOperation }) => runOperation(operation))
        .then(
          (result) => {
            observer.next(result as ApolloLink.Result);
            observer.complete();
          },
          (error) => observer.error(error),
        );
    }),
);

export const client = new ApolloClient({
  link: ApolloLink.split(() => isVaultMode(), from([errorLink, vaultLink]), from([errorLink, authLink, httpLink])),
  cache: new InMemoryCache({
    typePolicies: {
      Idea: { keyFields: ['ideaId'] },
      IdeaSummary: { keyFields: ['ideaId'] },
    },
  }),
  defaultOptions: {
    watchQuery: {
      fetchPolicy: 'cache-first',
      nextFetchPolicy: 'cache-first',
      // Polling queries (messaging, invitations, nav badge) skip their tick
      // while the tab is hidden — background tabs otherwise keep hitting
      // /graphql every 15-120s per the polling inventory in
      // docs/PERFORMANCE_MIGRATION_NOTES.md.
      skipPollAttempt: () =>
        typeof document !== 'undefined' && document.visibilityState === 'hidden',
    },
    query: {
      fetchPolicy: 'cache-first',
    },
  },
}); 