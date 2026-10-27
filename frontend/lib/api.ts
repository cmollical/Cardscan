import { firebaseIdToken } from "./firebase";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export function token() {
  return typeof window === "undefined"
    ? ""
    : localStorage.getItem("tallybinder.accessToken") || "";
}
export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("X-TallyBinder-Client", "web");
  const identity = await firebaseIdToken();
  if (identity || token()) headers.set("Authorization", "Bearer " + (identity || token()));
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const response = await fetch("/api/backend" + path, {
    ...options,
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    let code = "request_failed";
    try {
      const body = await response.json();
      code =
        body.detail?.code ||
        (typeof body.detail === "string"
          ? body.detail
          : "Check the entered fields.");
    } catch {}
    throw new ApiError(response.status, code.replaceAll("_", " "));
  }
  return response.json();
}
export async function download(path: string) {
  const headers = new Headers();
  const identity = await firebaseIdToken();
  if (identity || token()) headers.set("Authorization", "Bearer " + (identity || token()));
  const response = await fetch("/api/backend" + path, {
    headers,
    cache: "no-store",
  });
  if (!response.ok)
    throw new Error(
      "Download unavailable. Check your connection and sign-in status.",
    );
  return response.blob();
}
export async function upload(blob: Blob) {
  const form = new FormData();
  form.append("file", blob, "card.jpg");
  return request<{ id: string }>("/media/upload", {
    method: "POST",
    body: form,
  });
}
