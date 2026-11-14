import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { ApolloClient, ApolloLink, InMemoryCache, Observable } from '@apollo/client';
import { ApolloProvider, useQuery } from '@apollo/client/react';
import { MemoryRouter } from 'react-router-dom';
import { print } from 'graphql';
import { GET_IDEA_CORE } from 'features/core/apollo/queries';
import { sidebarVar } from 'features/core/apollo/localState';
import { useVoiceIdeaSession } from '../useVoiceIdeaSession';

jest.mock('../useVoiceAppCommands', () => ({
  useVoiceAppCommands: () => ({ executeCommand: jest.fn() }),
}));

it('shares the editor note request without downloading generated documents for idle voice', async () => {
  const requests: string[] = [];
  const client = new ApolloClient({
    cache: new InMemoryCache({ typePolicies: { Idea: { keyFields: ['ideaId'] } } }),
    link: new ApolloLink(operation => new Observable(observer => {
      requests.push(print(operation.query));
      const timer = setTimeout(() => {
        observer.next({ data: { idea: {
          __typename: 'Idea', ideaId: 'synthetic-note', userId: 'synthetic-user',
          title: 'Saved note', description: '<p>Saved words</p>', isPublished: false,
        } } });
        observer.complete();
      }, 5);
      return () => clearTimeout(timer);
    })),
  });
  sidebarVar({ ...sidebarVar(), currentIdeaId: 'synthetic-note' });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <ApolloProvider client={client}>
      <MemoryRouter initialEntries={['/ideas/synthetic-note/description']}>{children}</MemoryRouter>
    </ApolloProvider>
  );
  const { result, unmount } = renderHook(() => {
    const voice = useVoiceIdeaSession();
    const note = useQuery(GET_IDEA_CORE, { variables: { ideaId: 'synthetic-note' } });
    return { voice, note };
  }, { wrapper });
  await waitFor(() => expect(result.current.note.loading).toBe(false));
  expect(requests).toHaveLength(1);
  expect(requests[0]).toContain('description');
  expect(requests[0]).not.toMatch(/pitchDeck|provisionalPatent|businessModelCanvas|productRequirementsDocument/);
  expect(result.current.voice.state.isActive).toBe(false);
  unmount();
  client.stop();
  sidebarVar({ ...sidebarVar(), currentIdeaId: null });
});
