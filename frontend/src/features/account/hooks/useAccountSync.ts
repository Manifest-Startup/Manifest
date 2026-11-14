// No need for useEffect when we can rely on Apollo onCompleted callback
import { useReactiveVar } from "@apollo/client/react";
import { useSafeQuery } from "../../common-ui/api/useSafeQuery";

import { GET_ACCOUNT } from "features/core/apollo/queries";
import { createLogger } from "features/core/logError";
import { accountVar, userVar } from "features/core/apollo/localState";

const logger = createLogger('useAccountSync');

/**
 * Keeps Redux account slice in sync with server account data once the user is logged in.
 */
export const useAccountSync = () => {
  const { isLoggedIn } = useReactiveVar(userVar);

  useSafeQuery(GET_ACCOUNT, {
    skip: !isLoggedIn,
    fetchPolicy: "cache-first",
    nextFetchPolicy: "cache-first",
    onCompleted: (data) => {
      if (data?.account) {
        logger.debug('Updating account data (onCompleted)', data.account);
        accountVar({ accountData: data.account, loading: false, error: null });
      }
    },
    onError: (err) => logger.error('GET_ACCOUNT failed', err),
  });
}; 