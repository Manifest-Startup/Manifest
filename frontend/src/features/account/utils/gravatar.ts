import { resolveBackendAssetUrl } from "features/core/network/urls";

const DEFAULT_GRAVATAR_BASE = "https://www.gravatar.com/avatar";

export function normalizeGravatarInput(input: string) {
  const trimmed = input.trim();

  if (!trimmed) {
    return "";
  }

  try {
    const parsed = new URL(trimmed);
    if (parsed.hostname.includes("gravatar.com")) {
      const segments = parsed.pathname.split("/").filter(Boolean);
      const avatarIndex = segments.findIndex((segment) => segment === "avatar");
      const rawValue = avatarIndex >= 0 ? segments[avatarIndex + 1] || "" : segments[segments.length - 1] || "";
      return decodeURIComponent(rawValue).trim();
    }
  } catch {
    // Plain hashes are expected, so URL parsing failures can be ignored.
  }

  return trimmed;
}

export function getGravatarUrl(input: string, size = 120) {
  const normalizedInput = normalizeGravatarInput(input);

  if (!normalizedInput) {
    return `${DEFAULT_GRAVATAR_BASE}/?d=mp&s=${size}`;
  }

  return `${DEFAULT_GRAVATAR_BASE}/${encodeURIComponent(normalizedInput)}?d=mp&s=${size}`;
}

export function isPersistedProfilePictureUrl(input?: string | null): input is string {
  if (!input) {
    return false;
  }

  const trimmed = input.trim();
  if (!trimmed || trimmed.startsWith("blob:")) {
    return false;
  }

  if (trimmed.startsWith("data:image/") || trimmed.startsWith("/")) {
    return true;
  }

  try {
    const parsed = new URL(trimmed);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export function getAvatarUrl({
  profilePictureUrl,
  gravatarHash,
  size = 120,
}: {
  profilePictureUrl?: string | null;
  gravatarHash?: string | null;
  size?: number;
}) {
  if (isPersistedProfilePictureUrl(profilePictureUrl)) {
    return resolveBackendAssetUrl(profilePictureUrl.trim());
  }

  return getGravatarUrl(gravatarHash || "", size);
}
