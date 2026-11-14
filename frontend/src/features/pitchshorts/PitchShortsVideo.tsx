import React, { forwardRef, useEffect, useRef } from "react";

const HLS_SOURCE_RE = /\.m3u8(?:$|\?)/i;

const safeLoad = (video: HTMLVideoElement) => {
  try {
    video.load();
  } catch {
    // jsdom does not implement media loading; production browsers do.
  }
};

type PitchShortsVideoProps = Omit<React.VideoHTMLAttributes<HTMLVideoElement>, "src"> & {
  src?: string;
};

const PitchShortsVideo = forwardRef<HTMLVideoElement, PitchShortsVideoProps>(({ src, ...props }, forwardedRef) => {
  const innerRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    const video = innerRef.current;
    if (!video) {
      return;
    }

    let cleanup: (() => void) | undefined;
    let cancelled = false;

    const resetSource = () => {
      if (!innerRef.current) {
        return;
      }
      innerRef.current.pause();
      innerRef.current.removeAttribute("src");
      safeLoad(innerRef.current);
    };

    if (!src) {
      resetSource();
      return;
    }

    const attachDirectSource = () => {
      if (!innerRef.current) {
        return;
      }
      innerRef.current.src = src;
      safeLoad(innerRef.current);
    };

    if (!HLS_SOURCE_RE.test(src)) {
      attachDirectSource();
      return () => resetSource();
    }

    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      attachDirectSource();
      return () => resetSource();
    }

    void import("hls.js")
      .then(({ default: Hls }) => {
        if (cancelled || !innerRef.current) {
          return;
        }

        if (!Hls.isSupported()) {
          attachDirectSource();
          return;
        }

        const hls = new Hls({
          enableWorker: true,
          backBufferLength: 30,
          lowLatencyMode: true,
        });
        hls.loadSource(src);
        hls.attachMedia(innerRef.current);
        cleanup = () => hls.destroy();
      })
      .catch(() => {
        if (!cancelled) {
          attachDirectSource();
        }
      });

    return () => {
      cancelled = true;
      cleanup?.();
      resetSource();
    };
  }, [src]);

  return (
    <video
      {...props}
      ref={(node) => {
        innerRef.current = node;
        if (typeof forwardedRef === "function") {
          forwardedRef(node);
          return;
        }
        if (forwardedRef) {
          forwardedRef.current = node;
        }
      }}
    />
  );
});

PitchShortsVideo.displayName = "PitchShortsVideo";

export default PitchShortsVideo;
