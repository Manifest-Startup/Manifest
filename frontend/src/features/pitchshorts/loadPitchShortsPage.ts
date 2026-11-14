let pitchShortsPagePromise: Promise<typeof import("./PitchShortsPage")> | null = null;

export const loadPitchShortsPage = () => {
  if (!pitchShortsPagePromise) {
    pitchShortsPagePromise = import("./PitchShortsPage");
  }
  return pitchShortsPagePromise;
};
