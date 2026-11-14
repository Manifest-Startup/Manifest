const getGraphQLEndpoint = () => process.env.REACT_APP_GRAPHQL_URL || '/graphql';

export const getBackendOrigin = () => {
  if (typeof window === 'undefined') {
    return '';
  }

  try {
    return new URL(getGraphQLEndpoint(), window.location.origin).origin;
  } catch {
    return window.location.origin;
  }
};

export const resolveBackendAssetUrl = (assetUrl?: string | null) => {
  if (!assetUrl || typeof assetUrl !== 'string') {
    return '';
  }

  try {
    return new URL(assetUrl, getBackendOrigin() || undefined).toString();
  } catch {
    return assetUrl;
  }
};
