/** POST multipart profile image; backend persists file and updates users.profile_picture_url. */
import { buildSessionHeaders } from "features/auth/session";

export async function uploadProfilePicture(file: File): Promise<string> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch("/api/account/profile-picture", {
    method: "POST",
    body: formData,
    credentials: "include",
    headers: buildSessionHeaders(),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const err = (await res.json()) as { detail?: string | Array<{ msg?: string }> };
      if (typeof err?.detail === "string") {
        detail = err.detail;
      } else if (Array.isArray(err?.detail) && err.detail[0]?.msg) {
        detail = err.detail[0].msg;
      }
    } catch {
      // ignore
    }
    throw new Error(detail || "Upload failed");
  }
  const json = (await res.json()) as { profilePictureUrl?: string };
  if (!json.profilePictureUrl) {
    throw new Error("Invalid upload response");
  }
  return json.profilePictureUrl;
}
