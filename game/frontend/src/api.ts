import { initData } from "./tg";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
  ) {
    super(code);
  }
}

function authHeader(): string {
  const data = initData();
  if (data) return `tma ${data}`;
  // Local development outside Telegram (backend must run with DEV_MODE=true).
  if (import.meta.env.DEV) {
    let id = "1000001";
    try {
      id = localStorage.getItem("devUserId") ?? id;
    } catch {
      /* storage unavailable */
    }
    return `dev ${id}`;
  }
  return "";
}

export async function api<T>(
  path: string,
  options: { method?: string; body?: unknown; keepalive?: boolean } = {},
): Promise<T> {
  const res = await fetch(`/api${path}`, {
    keepalive: options.keepalive,
    method: options.method ?? (options.body === undefined ? "GET" : "POST"),
    headers: {
      Authorization: authHeader(),
      ...(options.body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  if (!res.ok) {
    let code = `http_${res.status}`;
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") code = data.detail;
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, code);
  }
  return (await res.json()) as T;
}
