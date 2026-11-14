import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { gql } from '@apollo/client';
import { MockedProvider } from '@apollo/client/testing/react';
import { useSafeQuery } from '../useSafeQuery';

const mockSetMessage = jest.fn();
jest.mock('features/notifications/context/MessageContext', () => ({
  useMessage: () => ({ setMessage: mockSetMessage }),
}));
const QUERY = gql`query LoadingRegression { profile { userId } }`;
const data = { profile: { __typename: 'AuthUser', userId: 'synthetic-user' } };

it('delivers completion with the real Apollo 4 client without repeating on rerender', async () => {
  const onCompleted = jest.fn();
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <React.StrictMode><MockedProvider mocks={[{ request: { query: QUERY }, result: { data }, delay: 1 }]}>{children}</MockedProvider></React.StrictMode>
  );
  const { result, rerender } = renderHook(() => useSafeQuery(QUERY, { onCompleted }), { wrapper });
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(onCompleted).toHaveBeenCalledWith(data);
  rerender();
  expect(onCompleted).toHaveBeenCalledTimes(1);
});

it('delivers network errors so session loading can settle', async () => {
  const onError = jest.fn();
  const error = new Error('Synthetic offline response');
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <MockedProvider mocks={[{ request: { query: QUERY }, error, delay: 1 }]}>{children}</MockedProvider>
  );
  const { result } = renderHook(() => useSafeQuery(QUERY, { onError }), { wrapper });
  await waitFor(() => expect(result.current.error).toBeDefined());
  expect(onError).toHaveBeenCalledWith(error);
});

it('delivers completion again after refetching unchanged data', async () => {
  const onCompleted = jest.fn();
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <MockedProvider mocks={[{ request: { query: QUERY }, result: { data }, delay: 1, maxUsageCount: 2 }]}>{children}</MockedProvider>
  );
  const { result } = renderHook(() => useSafeQuery(QUERY, { onCompleted }), { wrapper });
  await waitFor(() => expect(onCompleted).toHaveBeenCalledTimes(1));
  await act(async () => { await result.current.refetch(); });
  await waitFor(() => expect(onCompleted).toHaveBeenCalledTimes(2));
});
