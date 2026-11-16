import { useMutation, useReactiveVar } from '@apollo/client/react';
import { useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import {
  CREATE_IDEA,
  DELETE_IDEA,
  GENERATE_PITCH_DECK,
  GENERATE_PRODUCT_REQUIREMENTS_DOCUMENT,
  GENERATE_PROVISIONAL_PATENT,
  GET_IDEA,
  GET_IDEAS,
  RUN_BACKGROUND_TASKS,
  TOGGLE_PUBLISH_IDEA,
  UPDATE_IDEA,
} from 'features/core/apollo/queries';
import { sidebarVar, userVar } from 'features/core/apollo/localState';
import { useMessage } from 'features/notifications/context/MessageContext';
import { emitIdeaPublished } from 'features/ideas/events/ideaPublishEvents';
import { safeNavigate } from 'utils/safeNavigate';
import { performLogout } from 'features/auth/logout';

import { VOICE_COMMAND_INLINE_HINTS } from './voiceCommandCatalog';
import {
  dispatchVoiceCollaborationCommand,
  dispatchVoiceSearchCommand,
  dispatchVoiceShortsCommand,
  dispatchVoiceWorkspaceLayoutCommand,
} from './voiceCommandEvents';
import { postVoiceAgentJson } from './voiceAgentApi';
import { parseVoiceCommand, type VoiceIdeaAspect } from './voiceCommandParser';

interface VoiceCommandExecution {
  response: string;
}

function htmlToPlainDescription(html: string | null | undefined): string {
  if (!html || !html.trim()) {
    return '';
  }
  const stripped = html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  return stripped || '';
}

const IDEA_TITLE_FALLBACK = 'Brand New Idea';

const IDEA_ASPECT_LABELS: Record<VoiceIdeaAspect, string> = {
  description: 'note',
  'business-model-canvas': 'canvas',
  'cost-structure': 'cost structure',
  'pitch-deck': 'pitch deck',
  'product-requirements-document': 'product requirements document',
  patent: 'patent',
};

const ROUTE_LABELS = {
  account: 'account',
  auth: 'sign in',
  docs: 'API docs',
  ideas: 'ideas',
  'learn-more': 'learn more',
  shorts: 'pitch reels',
  messages: 'messages',
} as const;

const routePathForDestination = (destination: keyof typeof ROUTE_LABELS) => {
  if (destination === 'account') {
    return '/account';
  }

  if (destination === 'auth') {
    return '/login';
  }

  if (destination === 'docs') {
    return '/docs/api';
  }

  if (destination === 'learn-more') {
    return '/learn-more';
  }

  if (destination === 'shorts') {
    // #25: voice "go to shorts" navigates to the canonical Pitch Reels URL.
    return '/pitch-reels';
  }

  if (destination === 'messages') {
    return '/messages';
  }

  return '/ideas';
};

export function useVoiceAppCommands() {
  const navigate = useNavigate();
  const location = useLocation();
  const { setMessage, clearMessage } = useMessage();
  const sidebarState = useReactiveVar(sidebarVar);
  const { isLoggedIn, isGuest } = useReactiveVar(userVar);
  const routeIdeaId = location.pathname.match(/^\/ideas\/([^/]+)/)?.[1] || null;
  const activeIdeaId = routeIdeaId || sidebarState.currentIdeaId || null;

  const [createIdea] = useMutation(CREATE_IDEA, {
    refetchQueries: [{ query: GET_IDEAS }],
  });
  const [updateIdea] = useMutation(UPDATE_IDEA, {
    refetchQueries: [{ query: GET_IDEAS }],
  });
  const [deleteIdea] = useMutation(DELETE_IDEA, {
    refetchQueries: [{ query: GET_IDEAS }],
  });
  const [togglePublishIdea] = useMutation(TOGGLE_PUBLISH_IDEA, {
    refetchQueries: [{ query: GET_IDEAS }],
  });
  const [generatePitchDeckMutation] = useMutation(GENERATE_PITCH_DECK);
  const [generatePrdMutation] = useMutation(GENERATE_PRODUCT_REQUIREMENTS_DOCUMENT);
  const [generatePatentMutation] = useMutation(GENERATE_PROVISIONAL_PATENT);
  const [runBackgroundTasksMutation] = useMutation(RUN_BACKGROUND_TASKS);

  const syncSidebarIdea = useCallback((ideaId: string, ideaAspect = 'description') => {
    const current = sidebarVar();
    sidebarVar({
      ...current,
      currentIdeaId: ideaId,
      currentIdeaAspect: ideaAspect,
      allIdeaIds: current.allIdeaIds.includes(ideaId)
        ? current.allIdeaIds
        : [ideaId, ...current.allIdeaIds],
    });
  }, []);

  const navigateToIdeaAspect = useCallback(
    (ideaId: string, ideaAspect: VoiceIdeaAspect) => {
      syncSidebarIdea(ideaId, ideaAspect);
      safeNavigate(navigate, setMessage, `/ideas/${ideaId}/${ideaAspect}`);
    },
    [navigate, setMessage, syncSidebarIdea],
  );

  const executeCommand = useCallback(
    async (
      spokenText: string,
      options: { ideaDescriptionHtml?: string | null } = {},
    ): Promise<VoiceCommandExecution | null> => {
      const command = parseVoiceCommand(spokenText);
      if (!command) {
        return null;
      }

      if (!isLoggedIn) {
        return {
          response: 'Sign in first, then I can control the workspace for you.',
        };
      }

      if (command.kind === 'open_integrations') {
        const query = command.focus === 'github' ? '?focusIntegration=github' : '';
        safeNavigate(navigate, setMessage, `/account${query}`);
        return {
          response:
            command.focus === 'github'
              ? 'Opening account integrations with GitHub in focus.'
              : 'Opening account integrations.',
        };
      }

      if (command.kind === 'github_bootstrap') {
        if (isGuest) {
          return {
            response:
              'Guest tryouts cannot create GitHub repositories. Say claim my account to continue with Open Media.',
          };
        }
        if (!activeIdeaId) {
          return { response: 'Open an idea first, then I can create a GitHub repository from it.' };
        }
        try {
          const data = await postVoiceAgentJson<{ html_url?: string | null; detail?: string }>(
            '/api/integrations/github/bootstrap',
            { idea_id: activeIdeaId, repo_name: command.repoName },
          );
          if (data.html_url) {
            return {
              response: `Created a private GitHub repository. You can open it at ${data.html_url}.`,
            };
          }
          return {
            response: data.detail || 'Could not create the GitHub repository. Connect GitHub under integrations and try again.',
          };
        } catch {
          return {
            response:
              'Could not create the GitHub repository. Connect GitHub in account integrations, then say the bootstrap command again with confirm bootstrap at the end.',
          };
        }
      }

      if (command.kind === 'generate_document') {
        if (isGuest) {
          return {
            response:
              'Guest tryouts cannot generate full documents yet. Say claim my account to continue with Open Media.',
          };
        }
        if (!activeIdeaId) {
          return { response: 'Open an idea first, then I can generate documents from your note.' };
        }

        const description = htmlToPlainDescription(options.ideaDescriptionHtml) || '';
        if (!description) {
          return {
            response:
              'Your idea note looks empty. Dictate a bit more into the note, then ask me to generate again.',
          };
        }

        const refetchIdea = { query: GET_IDEA, variables: { ideaId: activeIdeaId } };

        try {
          if (command.document === 'pitch_deck') {
            await generatePitchDeckMutation({
              variables: { ideaId: activeIdeaId, description },
              refetchQueries: [refetchIdea, { query: GET_IDEAS }],
            });
            navigateToIdeaAspect(activeIdeaId, 'pitch-deck');
            return { response: 'Started generating your pitch deck and opened that section.' };
          }
          if (command.document === 'prd') {
            await generatePrdMutation({
              variables: { ideaId: activeIdeaId, description },
              refetchQueries: [refetchIdea, { query: GET_IDEAS }],
            });
            navigateToIdeaAspect(activeIdeaId, 'product-requirements-document');
            return { response: 'Started generating your product requirements document and opened that section.' };
          }
          if (command.document === 'patent') {
            await generatePatentMutation({
              variables: { ideaId: activeIdeaId, description },
              refetchQueries: [refetchIdea, { query: GET_IDEAS }],
            });
            navigateToIdeaAspect(activeIdeaId, 'patent');
            return { response: 'Started generating your provisional patent draft and opened that section.' };
          }
          await runBackgroundTasksMutation({
            variables: { ideaId: activeIdeaId, description },
            refetchQueries: [refetchIdea, { query: GET_IDEAS }],
          });
          navigateToIdeaAspect(activeIdeaId, 'description');
          return { response: 'Started background generation tasks for this idea.' };
        } catch {
          return {
            response: 'Generation failed. Check your connection and try again from the workspace.',
          };
        }
      }

      if (command.kind === 'claim_account_navigate') {
        safeNavigate(navigate, setMessage, '/login');
        return {
          response: isGuest
            ? 'Opening sign-in. Continue with Open Media and this guest workspace moves into your account.'
            : 'Opening sign-in.',
        };
      }

      if (command.kind === 'help') {
        return {
          response: `You can say things like ${VOICE_COMMAND_INLINE_HINTS.slice(0, 4).join(', ')}.`,
        };
      }

      if (command.kind === 'logout') {
        await performLogout();
        clearMessage();
        navigate('/login', { replace: true });
        return { response: 'Signing you out now.' };
      }

      if (command.kind === 'navigate') {
        if (isGuest && command.destination === 'messages') {
          return {
            response:
              'Guest tryouts cannot open messages yet. Say claim my account to continue with Open Media.',
          };
        }
        const path = routePathForDestination(command.destination);
        safeNavigate(navigate, setMessage, path);
        return { response: `Opening ${ROUTE_LABELS[command.destination]}.` };
      }

      if (command.kind === 'search') {
        dispatchVoiceSearchCommand({ query: command.query || undefined });
        return {
          response: command.query
            ? `Searching Manifest for ${command.query}.`
            : 'Opening search.',
        };
      }

      if (command.kind === 'create_idea') {
        const title = command.title || IDEA_TITLE_FALLBACK;
        const { data } = await createIdea({
          variables: { title },
        });
        const ideaId = data?.createIdea?.ideaId;
        if (!ideaId) {
          throw new Error('Idea creation did not return an idea ID.');
        }

        navigateToIdeaAspect(ideaId, 'description');
        return { response: `Created a new idea called ${title} and opened the note.` };
      }

      if (command.kind === 'open_workspace') {
        // Accept both the canonical and legacy reels routes (#25).
        if (
          location.pathname.startsWith('/pitch-reels') ||
          location.pathname.startsWith('/shorts')
        ) {
          dispatchVoiceShortsCommand({ action: 'open_workspace' });
          return { response: 'Opening the current reel workspace.' };
        }

        if (!activeIdeaId) {
          safeNavigate(navigate, setMessage, '/ideas');
          return { response: 'Opening ideas. Pick an idea or create a new one to keep going.' };
        }

        navigateToIdeaAspect(activeIdeaId, 'description');
        return { response: 'Opening the current workspace.' };
      }

      if (command.kind === 'open_idea_aspect') {
        if (!activeIdeaId) {
          return { response: 'Open or create an idea first, then I can move between note sections for you.' };
        }

        navigateToIdeaAspect(activeIdeaId, command.aspect);
        return { response: `Opening the ${IDEA_ASPECT_LABELS[command.aspect]}.` };
      }

      if (command.kind === 'rename_idea') {
        if (!activeIdeaId) {
          return { response: 'Open an idea first, then tell me the new title.' };
        }

        await updateIdea({
          variables: {
            ideaId: activeIdeaId,
            title: command.title,
          },
        });
        syncSidebarIdea(activeIdeaId);
        return { response: `Renamed the idea to ${command.title}.` };
      }

      if (command.kind === 'delete_idea') {
        if (!activeIdeaId) {
          return { response: 'There is no current idea to delete.' };
        }

        await deleteIdea({ variables: { ideaId: activeIdeaId } });
        const current = sidebarVar();
        sidebarVar({
          ...current,
          currentIdeaId: null,
          allIdeaIds: current.allIdeaIds.filter((ideaId) => ideaId !== activeIdeaId),
        });
        safeNavigate(navigate, setMessage, '/ideas');
        return { response: 'Deleted the current idea and returned to ideas.' };
      }

      if (command.kind === 'toggle_publish') {
        if (isGuest) {
          return {
            response:
              'Guest tryouts cannot publish. Say claim my account to continue with Open Media.',
          };
        }
        if (!activeIdeaId) {
          return { response: 'Open an idea first, then I can change its publish state.' };
        }

        await togglePublishIdea({ variables: { ideaId: activeIdeaId } });
        if (command.published) {
          emitIdeaPublished(activeIdeaId);
        }
        return {
          response: command.published
            ? 'Published the current idea to discovery.'
            : 'Unpublished the current idea.',
        };
      }

      if (command.kind === 'workspace_layout') {
        if (!activeIdeaId) {
          return { response: 'Open an idea workspace first, then I can adjust the layout.' };
        }

        navigateToIdeaAspect(activeIdeaId, 'description');
        window.setTimeout(() => {
          dispatchVoiceWorkspaceLayoutCommand({ action: command.action });
        }, 80);

        const layoutResponses: Record<typeof command.action, string> = {
          collapse_context: 'Collapsing the context panel.',
          collapse_library: 'Collapsing the idea library.',
          disable_focus_mode: 'Turning off focus mode.',
          enable_focus_mode: 'Turning on focus mode.',
          expand_context: 'Expanding the context panel.',
          expand_library: 'Expanding the idea library.',
        };

        return { response: layoutResponses[command.action] };
      }

      if (command.kind === 'open_modal') {
        if (!activeIdeaId) {
          return {
            response:
              command.target === 'share'
                ? 'Open an idea first, then I can open sharing.'
                : 'Open an idea first, then I can open version history.',
          };
        }

        navigateToIdeaAspect(activeIdeaId, 'description');
        window.setTimeout(() => {
          dispatchVoiceCollaborationCommand({
            ideaId: activeIdeaId,
            target: command.target,
          });
        }, 80);

        return {
          response: command.target === 'share' ? 'Opening sharing.' : 'Opening version history.',
        };
      }

      if (command.kind === 'shorts') {
        // Accept both the canonical and legacy reels routes (#25).
        const onReels =
          location.pathname.startsWith('/pitch-reels') ||
          location.pathname.startsWith('/shorts');
        if (!onReels) {
          return { response: 'Open pitch reels first, then I can control the current reel.' };
        }

        if (
          isGuest &&
          ['open_invest', 'toggle_follow', 'toggle_like', 'toggle_reshare', 'comment', 'share'].includes(command.action)
        ) {
          return {
            response:
              'Guest tryouts cannot invest or use social actions on reels yet. Say claim my account to continue with Open Media.',
          };
        }

        dispatchVoiceShortsCommand({
          action: command.action,
          body: command.body,
        });

        const responses: Record<typeof command.action, string> = {
          close_comments: 'Closing comments.',
          comment: command.body ? `Posting your comment: ${command.body}.` : 'Posting the comment.',
          mute: 'Muting the reel.',
          next: 'Moving to the next reel.',
          open_comments: 'Opening comments.',
          open_invest: 'Opening invest.',
          open_workspace: 'Opening the current reel workspace.',
          previous: 'Moving to the previous reel.',
          share: 'Sharing the current reel.',
          toggle_follow: 'Updating the follow state for this creator.',
          toggle_like: 'Updating your like on this reel.',
          toggle_reshare: 'Updating your Open Media repost of this reel.',
          unmute: 'Turning sound back on.',
        };

        return { response: responses[command.action] };
      }

      return null;
    },
    [
      activeIdeaId,
      createIdea,
      deleteIdea,
      isGuest,
      isLoggedIn,
      location.pathname,
      navigate,
      navigateToIdeaAspect,
      clearMessage,
      setMessage,
      syncSidebarIdea,
      togglePublishIdea,
      updateIdea,
      generatePitchDeckMutation,
      generatePrdMutation,
      generatePatentMutation,
      runBackgroundTasksMutation,
    ],
  );

  return {
    executeCommand,
  };
}
