export type RequestStatus =
  | "ready"
  | "needs_info"
  | "rejected"
  | "failed"
  | "booked";

export type Extracted = {
  service_type: string | null;
  time_window: string | null;
  contact: string | null;
  in_scope: boolean;
  missing: string[];
  extraction_method?: "llm" | "rule_based";
  extraction_provider?: string | null;
  extraction_model?: string | null;
  fallback_reason?: string | null;
};

export type Citation = {
  source: string;
  text: string;
};

export type Execution = {
  id: number;
  ok: number;
  detail: string;
  at: string;
};

export type Req = {
  id: number;
  text: string;
  status: RequestStatus;
  extracted: Extracted;
  citations: Citation[];
  booking_id: string | null;
  error: string | null;
  executions?: Execution[];
};

export type BookingPreview = {
  preview_id: string;
  title: string;
  start: string;
  end: string;
  timezone: string;
};

async function call<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch("/api" + path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const detail = data?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail
          ? JSON.stringify(detail)
          : response.statusText;

    throw new Error(`${response.status}: ${message}`);
  }

  return data as T;
}

export const listRequests = () => call<Req[]>("/requests");

export const getRequest = (id: number) =>
  call<Req>(`/requests/${id}`);

export const createRequest = (text: string) =>
  call<Req>("/requests", "POST", { text });

export const clarify = (id: number, text: string) =>
  call<Req>(`/requests/${id}/clarify`, "POST", { text });

export const previewBooking = (id: number) =>
  call<BookingPreview>(`/requests/${id}/preview`, "POST");

export const approve = (id: number, previewId: string) =>
  call<Req>(`/requests/${id}/approve`, "POST", {
    preview_id: previewId,
  });

export const forceFail = () =>
  call<{ fail_next: number }>("/debug/fail-next", "POST");