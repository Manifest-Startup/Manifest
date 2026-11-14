let pitchShortsPagePromise: Promise<typeof import("./PitchReelsPage")> | null = null;

export const loadPitchReelsPage = () => {
  if (!pitchShortsPagePromise) {
    pitchShortsPagePromise = import("./PitchReelsPage");
  }
  return pitchShortsPagePromise;
};
