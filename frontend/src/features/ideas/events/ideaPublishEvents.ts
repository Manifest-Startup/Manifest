type IdeaPublishedCallback = (ideaId: string) => void;

const subscribers = new Set<IdeaPublishedCallback>();

export function subscribeToIdeaPublished(callback: IdeaPublishedCallback): () => void {
  subscribers.add(callback);
  return () => {
    subscribers.delete(callback);
  };
}

export function emitIdeaPublished(ideaId: string): void {
  subscribers.forEach((callback) => {
    try {
      callback(ideaId);
    } catch {
      // Individual subscriber failures should not break the publish event fan-out.
    }
  });
}
