import { useEffect, useState } from "react";
import * as api from "./api";
import type { BookingPreview, Req, RequestStatus } from "./api";

const labels: Record<RequestStatus, string> = {
  ready: "Ready for review",
  needs_info: "Needs clarification",
  rejected: "Out of scope",
  failed: "Action blocked",
  booked: "Booked",
};

const missingLabels: Record<string, string> = {
  service_type: "Confirm one supported service type.",
  time_window: "Provide a day and morning or afternoon.",
  contact: "Provide a phone number or email.",
  specific_day_required: "Choose a specific day.",
  choose_monday_to_saturday: "Choose Monday through Saturday.",
  choose_morning_or_afternoon: "Choose morning or afternoon.",
  specify_morning_or_afternoon: "Specify morning or afternoon.",
  same_day_requires_staff_review_choose_future_day:
    "Same-day service requires staff review. Choose a future day.",
};

const css = `
*{box-sizing:border-box}
body{margin:0;background:#f4f6fa;color:#17233b;font-family:Inter,system-ui,sans-serif}
button,input,textarea{font:inherit}
button{cursor:pointer}
button:disabled{cursor:not-allowed;opacity:.55}
.shell{max-width:1320px;margin:auto;padding:32px}
.header{display:flex;justify-content:space-between;align-items:center;gap:16px}
.eyebrow{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#687792}
h1{font-size:30px;margin:8px 0}
h2{font-size:20px;margin:0 0 16px}
h3{font-size:15px;margin:0 0 12px}
.muted{color:#66748b;font-size:14px;line-height:1.6}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:26px 0}
.stat,.card{background:white;border:1px solid #e0e6ef;border-radius:14px}
.stat{padding:18px}
.stat strong{display:block;font-size:26px;margin-bottom:4px}
.workspace{display:grid;grid-template-columns:350px minmax(0,1fr);gap:22px;align-items:start}
.card{padding:22px;margin-bottom:18px}
textarea,input{width:100%;border:1px solid #ccd5e2;border-radius:8px;padding:12px;background:#fff;color:#17233b}
textarea{resize:vertical;min-height:100px}
textarea:focus,input:focus{outline:2px solid #b9cffb;outline-offset:2px}
.primary,.secondary{border-radius:8px;padding:11px 16px;font-weight:600}
.primary{background:#285de5;color:white;border:1px solid #285de5}
.secondary{background:white;color:#34445f;border:1px solid #ccd5e2}
.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
.inbox{max-height:560px;overflow-y:auto;padding-right:4px}
.request{display:block;width:100%;text-align:left;padding:15px;border:1px solid #e1e7f0;border-radius:9px;background:#fff;margin-top:10px}
.request.active{border-color:#285de5;background:#f0f5ff}
.request p{font-size:13px;line-height:1.5;margin:10px 0 0;color:#586780;overflow-wrap:anywhere}
.row{display:flex;justify-content:space-between;align-items:center;gap:10px}
.badge{font-size:11px;font-weight:700;padding:6px 9px;border-radius:20px;background:#eef1f6;color:#52617a}
.badge.booked{background:#e7f7ef;color:#17633e}
.badge.ready{background:#edf2ff;color:#285de5}
.badge.failed,.badge.needs_info{background:#fff1df;color:#8c540b}
.message{white-space:pre-wrap;line-height:1.7;overflow-wrap:anywhere}
.fields{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.field{background:#f5f7fb;padding:14px;border-radius:9px;overflow-wrap:anywhere}
.field span{display:block;font-size:12px;color:#66748b;margin-bottom:7px}
.field strong{font-size:14px}
.notice{padding:14px 16px;border-radius:9px;line-height:1.6;margin-bottom:16px;overflow-wrap:anywhere}
.error{background:#fff0ee;color:#99392f}
.success{background:#eaf8ef;color:#1a6844}
.info{background:#edf3ff;color:#315899}
.extraction{border:1px solid #dce5f3;background:#f8faff;border-radius:10px;padding:14px 16px;margin-bottom:18px}
.extraction strong{display:block;margin-bottom:5px}
.preview{background:#f2f6ff;border:1px solid #ccdafb;border-radius:10px;padding:18px}
.preview strong{display:block;font-size:18px;margin:8px 0}
.evidence{border-left:3px solid #cfdbef;padding-left:14px;margin:16px 0}
.evidence p{white-space:pre-wrap;line-height:1.6;font-size:14px}
.history{border-top:1px solid #e5eaf2;padding:14px 0;overflow-wrap:anywhere}
.history p{font-size:13px;line-height:1.5;margin:7px 0}
.demo{margin-top:20px}
.empty{padding:65px 24px;text-align:center}
label{display:block;font-size:13px;font-weight:600;margin-bottom:9px}
@media(max-width:850px){
  .workspace{grid-template-columns:1fr}
  .shell{padding:18px}
  .fields{grid-template-columns:1fr}
  .stats{grid-template-columns:repeat(2,1fr)}
  .header{align-items:flex-start;flex-direction:column}
  .inbox{max-height:320px}
}
`;

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function formatStart(preview: BookingPreview): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: preview.timezone,
    weekday: "long",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(preview.start));
}

function formatEnd(preview: BookingPreview): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: preview.timezone,
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(preview.end));
}

function formatHistoryTime(value: string): string {
  // SQLite CURRENT_TIMESTAMP is UTC.
  const date = new Date(value.replace(" ", "T") + "Z");
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function ExtractionIndicator({ request }: { request: Req }) {
  const info = request.extracted;

  if (info.extraction_method === "llm") {
    return (
      <div className="extraction">
        <strong>
          Extracted with {info.extraction_provider === "gemini"
            ? "Gemini"
            : info.extraction_provider || "AI"}
        </strong>
        <div className="muted">
          Model: {info.extraction_model || "Not recorded"}
          <br />
          AI extracted these fields. Review them before approval.
        </div>
      </div>
    );
  }

  if (info.extraction_method === "rule_based") {
    return (
      <div className="extraction">
        <strong>Fallback rules used</strong>
        <div className="muted">
          {info.fallback_reason === "no_api_key"
            ? "No Gemini API key was configured."
            : "Gemini extraction was unavailable or its output failed validation."}
          {info.fallback_reason && (
            <div>Reason: {info.fallback_reason}</div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="extraction">
      <strong>Extraction method not recorded</strong>
      <div className="muted">
        This older request was saved before extraction tracking was added.
      </div>
    </div>
  );
}

export default function App() {
  const [items, setItems] = useState<Req[]>([]);
  const [selected, setSelected] = useState<Req | null>(null);
  const [preview, setPreview] = useState<BookingPreview | null>(null);
  const [text, setText] = useState("");
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;

    api.listRequests()
      .then((requests) => {
        if (active) setItems(requests);
      })
      .catch((e: unknown) => {
        if (active) setError(errorMessage(e));
      });

    return () => {
      active = false;
    };
  }, []);

  async function loadRequest(id: number) {
    setPreview(null);
    const request = await api.getRequest(id);
    setSelected(request);

    if (request.status === "ready" || request.status === "failed") {
      const proposal = await api.previewBooking(id);
      setPreview(proposal);
    }
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");

    try {
      await action();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function refresh() {
    setItems(await api.listRequests());
  }

  const count = (statuses: RequestStatus[]) =>
    items.filter((item) => statuses.includes(item.status)).length;

  const conflict = Boolean(
    selected?.error?.includes("slot is already occupied"),
  );

  const stats: Array<{ label: string; value: number }> = [
    { label: "Total requests", value: items.length },
    { label: "Ready for review", value: count(["ready"]) },
    { label: "Need attention", value: count(["needs_info", "failed"]) },
    { label: "Booked", value: count(["booked"]) },
  ];

  const fields: Array<{ label: string; value: string | null }> =
    selected
      ? [
          { label: "Service", value: selected.extracted.service_type },
          {
            label: "Requested window",
            value: selected.extracted.time_window,
          },
          { label: "Contact", value: selected.extracted.contact },
        ]
      : [];

  return (
    <>
      <style>{css}</style>

      <main className="shell">
        <header className="header">
          <div>
            <div className="eyebrow">
              Service operations · Demo workspace
            </div>
            <h1>Request-to-Action</h1>
            <div className="muted">
              Review customer requests and approve calendar bookings.
            </div>
          </div>

          <button
            className="secondary"
            disabled={busy}
            onClick={() => run(async () => {
              await refresh();
              if (selected) await loadRequest(selected.id);
            })}
          >
            Refresh
          </button>
        </header>

        <section className="stats" aria-label="Request totals">
          {stats.map((stat) => (
            <div className="stat" key={stat.label}>
              <strong>{stat.value}</strong>
              <span className="muted">{stat.label}</span>
            </div>
          ))}
        </section>

        {error && (
          <div role="alert" className="notice error">
            {error}
          </div>
        )}

        {notice && (
          <div role="status" className="notice info">
            {notice}
          </div>
        )}

        <div className="workspace">
          <aside>
            <section className="card">
              <h2>New request</h2>

              <form onSubmit={(event) => {
                event.preventDefault();

                run(async () => {
                  const request = await api.createRequest(text.trim());
                  setText("");
                  setReply("");
                  await refresh();
                  await loadRequest(request.id);
                });
              }}>
                <label htmlFor="customer-message">
                  Customer message
                </label>

                <textarea
                  id="customer-message"
                  value={text}
                  maxLength={5000}
                  disabled={busy}
                  onChange={(event) => setText(event.target.value)}
                  placeholder="Need a plumber Friday morning. Call 312-555-0100."
                />

                <div className="actions">
                  <button
                    className="primary"
                    disabled={busy || !text.trim()}
                  >
                    {busy ? "Processing…" : "Analyze request"}
                  </button>
                </div>
              </form>
            </section>

            <section className="card">
              <h2>Request inbox</h2>

              {!items.length && (
                <p className="muted">No requests yet.</p>
              )}

              <div className="inbox">
                {items.map((request) => (
                  <button
                    className={`request ${
                      selected?.id === request.id ? "active" : ""
                    }`}
                    key={request.id}
                    disabled={busy}
                    aria-pressed={selected?.id === request.id}
                    onClick={() => run(async () => {
                      setSelected(null);
                      setReply("");
                      await loadRequest(request.id);
                    })}
                  >
                    <div className="row">
                      <strong>#{request.id}</strong>
                      <span className={`badge ${request.status}`}>
                        {labels[request.status]}
                      </span>
                    </div>

                    <p>
                      {request.text.length > 100
                        ? request.text.slice(0, 100) + "…"
                        : request.text}
                    </p>
                  </button>
                ))}
              </div>
            </section>
          </aside>

          <section aria-label="Selected request">
            {!selected ? (
              <div className="card empty">
                <h2>Your review workspace</h2>
                <p className="muted">
                  Select a request or submit a customer message to begin.
                </p>
              </div>
            ) : (
              <>
                <section className="card">
                  <div className="row">
                    <h2>Request #{selected.id}</h2>
                    <span className={`badge ${selected.status}`}>
                      {labels[selected.status]}
                    </span>
                  </div>

                  <p className="message">{selected.text}</p>

                  <ExtractionIndicator request={selected} />

                  <div className="fields">
                    {fields.map((field) => (
                      <div className="field" key={field.label}>
                        <span>{field.label}</span>
                        <strong>
                          {field.value || "Not provided"}
                        </strong>
                      </div>
                    ))}
                  </div>
                </section>

                {selected.status === "needs_info" && (
                  <section className="card">
                    <h2>Clarification required</h2>

                    <ul className="muted">
                      {selected.extracted.missing.map((field) => (
                        <li key={field}>
                          {missingLabels[field] ||
                            field.replace(/_/g, " ")}
                        </li>
                      ))}
                    </ul>

                    <form onSubmit={(event) => {
                      event.preventDefault();

                      run(async () => {
                        const updated = await api.clarify(
                          selected.id,
                          reply.trim(),
                        );

                        setReply("");
                        await refresh();
                        await loadRequest(updated.id);
                      });
                    }}>
                      <label htmlFor="clarification">
                        Customer’s reply
                      </label>

                      <input
                        id="clarification"
                        value={reply}
                        disabled={busy}
                        maxLength={5000}
                        onChange={(event) => setReply(event.target.value)}
                        placeholder="Friday morning. Call 312-555-0100."
                      />

                      <div className="actions">
                        <button
                          className="primary"
                          disabled={busy || !reply.trim()}
                        >
                          Update request
                        </button>
                      </div>
                    </form>
                  </section>
                )}

                {selected.status === "rejected" && (
                  <div className="notice info">
                    This message is outside the supported service-request
                    workflow. No booking will be created.
                  </div>
                )}

                {selected.status === "booked" && (
                  <section className="card">
                    <h2>Booking completed</h2>

                    <div className="notice success">
                      Booking recorded successfully.
                    </div>

                    <p
                      className="muted"
                      style={{ overflowWrap: "anywhere" }}
                    >
                      Event ID: {selected.booking_id}
                    </p>
                  </section>
                )}

                {(selected.status === "ready" ||
                  selected.status === "failed") && (
                  <section className="card">
                    <h2>Review proposed booking</h2>

                    {selected.error && (
                      <div className="notice error">
                        {selected.error}
                      </div>
                    )}

                    {preview ? (
                      <div className="preview">
                        <div className="eyebrow">
                          Proposed appointment
                        </div>

                        <strong>{formatStart(preview)}</strong>
                        <div>Ends at {formatEnd(preview)}</div>

                        <p className="muted">
                          Timezone: {preview.timezone}
                          <br />
                          Demo defaults: morning 9–10am; afternoon 1–2pm.
                          This proposal does not reserve the slot.
                        </p>
                      </div>
                    ) : (
                      <p className="muted">
                        A booking preview must load before approval.
                      </p>
                    )}

                    {conflict && (
                      <p className="muted">
                        Submit a new request for another day or window.
                        Retrying this proposal will check the same slot.
                      </p>
                    )}

                    <div className="actions">
                      <button
                        className="primary"
                        disabled={busy || !preview || conflict}
                        onClick={() => run(async () => {
                          if (!preview) return;

                          const updated = await api.approve(
                            selected.id,
                            preview.preview_id,
                          );

                          await refresh();
                          await loadRequest(updated.id);
                        })}
                      >
                        {selected.status === "failed"
                          ? "Retry approved booking"
                          : "Approve this booking"}
                      </button>

                      <button
                        className="secondary"
                        disabled={busy}
                        onClick={() =>
                          run(() => loadRequest(selected.id))
                        }
                      >
                        Reload preview
                      </button>
                    </div>

                    <p className="muted">
                      Approval creates a real event in the configured demo
                      calendar. Availability is checked before creation.
                    </p>
                  </section>
                )}

                {selected.citations.length > 0 && (
                  <section className="card">
                    <h2>Referenced policies</h2>

                    <p className="muted">
                      Document excerpts for review. Displaying a policy
                      does not mean every rule is automatically enforced.
                    </p>

                    {selected.citations.map((citation, index) => (
                      <div className="evidence" key={index}>
                        <strong className="muted">
                          {citation.source}
                        </strong>
                        <p>
                          {citation.text.replace(/^#+\s*/gm, "")}
                        </p>
                      </div>
                    ))}
                  </section>
                )}

                {!!selected.executions?.length && (
                  <section className="card">
                    <h2>Execution history</h2>

                    {selected.executions.map((execution) => (
                      <div className="history" key={execution.id}>
                        <strong>
                          {execution.ok
                            ? "✓ Completed"
                            : "× Unsuccessful"}
                        </strong>

                        <span className="muted">
                          {" · "}
                          {formatHistoryTime(execution.at)}
                        </span>

                        <p>{execution.detail}</p>
                      </div>
                    ))}
                  </section>
                )}
              </>
            )}

            <details className="card demo">
              <summary>Demo controls</summary>

              <p className="muted">
                Simulate one failure when creating a new calendar event.
              </p>

              <button
                className="secondary"
                disabled={busy}
                onClick={() => run(async () => {
                  await api.forceFail();
                  setNotice(
                    "Demo failure armed for the next new booking attempt.",
                  );
                })}
              >
                Simulate next failure
              </button>
            </details>
          </section>
        </div>
      </main>
    </>
  );
}