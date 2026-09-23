export type RoomSession = {
  id: string;
  token: string;
  invite?: string;
  title: string;
};
export type LiveTask = {
  id: string;
  description: string;
  responsible_name: string | null;
  responsible_participant_id: string | null;
  deadline: string | null;
  status: string;
  priority: string;
  source_quote: string;
  confidence: number;
};
export type RoomSnapshot = {
  id: string;
  title: string;
  date: string;
  created_at: string;
  started_at: string;
  server_time: string;
  me: string;
  is_host: boolean;
  recording: boolean;
  recording_version: number;
  ended_at: string | null;
  analysis_status: string;
  analysis_error: string | null;
  analysis_version: number;
  analysis_stale: boolean;
  summary: string;
  topics: string[];
  decisions: string[];
  audio: { pending: number; done: number; failed: number };
  participants: {
    id: string;
    name: string;
    is_host: boolean;
    online: boolean;
    muted?: boolean;
    camera?: boolean;
    sharing?: boolean;
  }[];
  transcript: {
    id: string;
    ordinal: number;
    speaker_id: string;
    speaker_name: string | null;
    start: number;
    end: number;
    text: string;
  }[];
  tasks: LiveTask[];
  messages: {
    id: string;
    member_id: string;
    name: string;
    text: string;
    at: string;
  }[];
};
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function conferenceApi<T>(
  path: string,
  token?: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (typeof init.body === "string")
    headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`/api/v1/conferences${path}`, {
      ...init,
      headers,
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "Нет связи с сервером. Проверьте сеть и повторите.");
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: unknown;
    } | null;
    const message =
      typeof body?.detail === "string"
        ? body.detail
        : response.status === 422
          ? "Проверьте заполнение полей и согласие на запись."
          : `Ошибка сервера (${response.status}). Проверьте запуск Docker.`;
    throw new ApiError(response.status, message);
  }
  if (response.headers.get("Content-Type")?.includes("application/json"))
    return response.json();
  return (await response.blob()) as T;
}
const KEY = "protocol-conference-sessions-v1";
export function savedRooms(): RoomSession[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "[]");
  } catch {
    return [];
  }
}
export function saveRoom(session: RoomSession) {
  localStorage.setItem(
    KEY,
    JSON.stringify(
      [session, ...savedRooms().filter((s) => s.id !== session.id)].slice(
        0,
        100,
      ),
    ),
  );
}
export function forgetRoom(id: string) {
  localStorage.setItem(
    KEY,
    JSON.stringify(savedRooms().filter((s) => s.id !== id)),
  );
}
export function invitationLink(session: RoomSession) {
  return `${location.origin}/?room=${encodeURIComponent(session.id)}#invite=${encodeURIComponent(session.invite || "")}`;
}
export async function downloadRoom(
  session: RoomSession,
  path: string,
  filename: string,
) {
  const blob = await conferenceApi<Blob>(
    `/${session.id}/${path}`,
    session.token,
  );
  const url = URL.createObjectURL(blob),
    link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
