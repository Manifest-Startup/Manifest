import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { bridgeNotReadyMessage, probeBridge, VOICE_SETUP_COMMAND, type BridgeInfo } from './localAgent';

/** How often to look for the bridge while the setup card is open. */
export const SETUP_POLL_MS = 2000;

/**
 * Voice isn't set up on this computer yet: one command (copy, paste in Terminal) installs
 * the bridge to Claude Code or Codex, and voice connects by itself as soon as it's running.
 * Or add an OpenAI key instead. No other choices to make.
 */
const VoiceSetup: React.FC<{ onReady: (bridge: BridgeInfo) => void; signIn?: boolean }> = ({ onReady, signIn }) => {
  const [copied, setCopied] = useState(false);
  // The bridge runs but its agent can't answer yet (e.g. Codex needs a project): what to do.
  const [notReady, setNotReady] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let timer: number | null = null;
    const look = async () => {
      // One probe at a time: the first may wait on Chrome asking about this computer.
      const bridge = await probeBridge();
      if (!alive) return;
      const problem = bridge ? bridgeNotReadyMessage(bridge) : null;
      setNotReady(problem);
      if (bridge && !problem) onReady(bridge);
      else timer = window.setTimeout(() => void look(), SETUP_POLL_MS);
    };
    void look();
    return () => {
      alive = false;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [onReady]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(VOICE_SETUP_COMMAND);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard blocked: the command is selectable.
    }
  };

  return (
    <div className="lv-setup" data-testid="voice-setup">
      <p className="lv-setup__lead">Talk with Claude Code or Codex on this Mac. Paste this in Terminal once:</p>
      <div className="lv-setup__cmd">
        <code>{VOICE_SETUP_COMMAND}</code>
        <button className="lv-setup__copy" onClick={() => void copy()} type="button">
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      {notReady ? (
        <p className="lv-setup__wait" role="status">
          {notReady} Then run <code>manifest bridge --restart</code>; voice connects by itself.
        </p>
      ) : (
        <p className="lv-setup__wait" role="status">
          <span aria-hidden="true" className="lv-spin" /> Waiting for your Mac · connects by itself
        </p>
      )}
      <p className="lv-setup__alt">
        Or{' '}
        {signIn ? (
          <Link to="/login">sign in</Link>
        ) : (
          <Link to="/account#ai-key">add an OpenAI key</Link>
        )}{' '}
        to use Manifest&apos;s own voice.
      </p>
    </div>
  );
};

export default VoiceSetup;
