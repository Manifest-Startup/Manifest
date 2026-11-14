import React, { lazy, Suspense, useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useReactiveVar } from "@apollo/client/react";
import { useMutation } from '@apollo/client/react';
import { useSafeQuery } from 'features/common-ui/api/useSafeQuery';
import { GET_IDEAS, CREATE_IDEA } from 'features/core/apollo/queries';
import { sidebarVar, similarIdeasVar, getSimilarIdeasEntry } from "features/core/apollo/localState";
import { createLogger } from 'features/core/logError';
import { useMessage } from "features/notifications/context/MessageContext";
import IOSPageWrapper from "../components/IOSPageWrapper";
import SimilarIdeas from "features/ideas/components/SimilarIdeas";
import PublishTick from "features/social/components/PublishTick";

const Idea = lazy(() => import("features/ideas/components/Idea").then((module) => ({ default: module.Idea })));

const logger = createLogger('IOSIdeasPage');

interface IdeaType {
  ideaId: string;
  title: string;
  description?: string;
  isPublished?: boolean;
}

const IOSIdeasPage: React.FC = () => {
  logger.log('rendered');
  const { idea_id } = useParams<{ idea_id: string }>();
  const navigate = useNavigate();
  const similarIdeasState = useReactiveVar(similarIdeasVar);
  const similarIdeasEntry = idea_id ? getSimilarIdeasEntry(similarIdeasState, idea_id) : null;
  const similarIdeas =
    similarIdeasEntry?.data ||
    (similarIdeasState.ideaId === idea_id ? similarIdeasState.data : '');
  const [showSimilarIdeas, setShowSimilarIdeas] = useState(false);

  const { data: ideasData, loading, error, refetch } = useSafeQuery(GET_IDEAS, {
    fetchPolicy: "cache-first",
    nextFetchPolicy: "cache-first",
  });
  const ideas = ideasData?.ideas || [];
  const { setMessage } = useMessage();
  const [createIdea] = useMutation(CREATE_IDEA, {
    refetchQueries: [{ query: GET_IDEAS }],
  });

  useEffect(() => {
    logger.log('useEffect: setCurrentIdeaId', { idea_id });
    sidebarVar({ ...sidebarVar(), currentIdeaId: idea_id || null });
  }, [idea_id]);

  const handleCreateIdea = async () => {
    try {
      const { data } = await createIdea({ variables: { title: 'Brand New Idea' } });
      const createdIdeaId = data?.createIdea?.ideaId;
      if (createdIdeaId) {
        sidebarVar({ ...sidebarVar(), allIdeaIds: [...(sidebarVar().allIdeaIds || []), createdIdeaId], currentIdeaId: createdIdeaId });
        navigate(`/ideas/${createdIdeaId}/description`);
      }
    } catch (error) {
      setMessage('Failed to create idea. Please try again.', 'error');
    }
  };

  if (!idea_id) {
    return (
      <IOSPageWrapper>
        <div className="mx-auto px-4 py-3">
          <div className="flex items-center justify-between mb-6">
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">My Ideas</h1>
            <button
              onClick={handleCreateIdea}
              className="manifest-control manifest-control-primary h-11 w-11 p-0 text-xl"
              title="Create New Idea"
            >
              +
            </button>
          </div>
          <div className="divide-y divide-gray-200 dark:divide-neutral700">
            {ideas.map((idea: IdeaType) => (
              <button
                key={idea.ideaId}
                onClick={() => navigate(`/ideas/${idea.ideaId}/description`)}
                className="w-full bg-white dark:bg-neutral900 px-0 py-3 text-left"
              >
                <div className="flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-lg font-semibold text-gray-900 dark:text-white truncate">
                        {idea.title || 'Untitled Idea'}
                      </h3>
                      <PublishTick
                        ideaId={idea.ideaId}
                        isPublished={idea.isPublished || false}
                        size="sm"
                      />
                    </div>
                    {idea.description && (
                      <p className="text-sm text-gray-500 dark:text-gray-400 line-clamp-2">
                        {idea.description.replace(/<[^>]*>/g, '').substring(0, 100)}...
                      </p>
                    )}
                  </div>
                  <svg className="w-5 h-5 text-gray-400 dark:text-gray-500 flex-shrink-0 mt-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </div>
              </button>
            ))}
            {loading && ideas.length === 0 && <p role="status" className="py-6">Loading ideas…</p>}
            {error && ideas.length === 0 && <div role="alert" className="py-6">Could not load your ideas. <button onClick={() => void refetch()}>Try again</button></div>}
            {!loading && !error && ideas.length === 0 && (
              <div className="text-center py-12">
                <svg className="w-16 h-16 mx-auto mb-4 text-gray-300 dark:text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 18v-5.25m0 0a6.01 6.01 0 001.5-.189m-1.5.189a6.01 6.01 0 01-1.5-.189m3.75 7.478a12.06 12.06 0 01-4.5 0m3.75 2.383a14.406 14.406 0 01-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 10-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
                </svg>
                <p className="text-gray-500 dark:text-gray-400 mb-4">No ideas yet</p>
                <button
                  onClick={handleCreateIdea}
                  className="px-6 py-3 bg-accent-600 text-white rounded-full font-medium active:scale-95 transition-transform"
                >
                  Create Your First Idea
                </button>
              </div>
            )}
          </div>
        </div>
      </IOSPageWrapper>
    );
  }

  return (
    <IOSPageWrapper>
      <div className="w-full h-full flex flex-col">
        <div className="flex-1 overflow-hidden">
          <div className="h-full overflow-y-auto">
            <Suspense fallback={<p role="status" className="p-4">Opening idea…</p>}><Idea /></Suspense>
          </div>
        </div>

        <div className="border-t border-gray-200 dark:border-neutral700 bg-white dark:bg-neutral800 transition-colors">
          <button
            onClick={() => setShowSimilarIdeas(!showSimilarIdeas)}
            className="w-full px-4 py-3 flex items-center justify-between text-gray-700 dark:text-gray-300 active:bg-gray-50 dark:active:bg-neutral700 transition-colors"
          >
            <span className="font-medium">Similar Ideas</span>
            <span className={`transform transition-transform ${showSimilarIdeas ? 'rotate-180' : ''}`}>
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </span>
          </button>
          {showSimilarIdeas && (
            <div className="px-4 pb-4 max-h-64 overflow-y-auto">
              <SimilarIdeas compact ideaId={idea_id} similarIdeas={similarIdeas} />
            </div>
          )}
        </div>
      </div>
    </IOSPageWrapper>
  );
};

export default IOSIdeasPage;
