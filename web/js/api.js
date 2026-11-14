const JSON_HEADERS = { "Content-Type": "application/json" };

async function request(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      detail = data.detail || detail;
    } catch (_) {
      /* ignore */
    }
    throw new Error(detail);
  }
  const type = response.headers.get("content-type") || "";
  return type.includes("application/json") ? response.json() : response.text();
}

/* 所有 JSON POST 共用一套 header/body 组装。 */
function postJson(path, body, options = {}) {
  return request(path, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
    ...options,
  });
}

export const api = {
  bootstrap: () => request("/api/bootstrap"),
  today: () => request("/api/today"),
  characters: () => request("/api/characters"),
  character: (char) => request(`/api/characters/${encodeURIComponent(char)}`),
  poems: () => request("/api/poems"),
  poem: (id) => request(`/api/poems/${encodeURIComponent(id)}`),
  poemRead: (id) => postJson(`/api/poems/${encodeURIComponent(id)}/read`, { mode: "read" }),
  lessons: () => request("/api/lessons"),
  startSession: () => postJson("/api/sessions", { app_version: "0.1.0" }),
  endSession: (id, completed = false) =>
    request(`/api/sessions/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: JSON_HEADERS,
      body: JSON.stringify({ completed: Boolean(completed) }),
      keepalive: true,
    }),
  achievements: () => request("/api/achievements"),
  achievementsSeen: (ids = []) => postJson("/api/achievements/seen", { ids }),
  submitAttempts: (sessionId, attempts) =>
    postJson("/api/attempts", { session_id: sessionId, attempts }, { keepalive: true }),
  stats: () => request("/api/stats/summary"),
  weekly: () => request("/api/parent/weekly"),
  polyphonic: () => request("/api/polyphonic"),
  progress: () => request("/api/progress"),
  recognitionSummary: () => request("/api/recognition/summary"),
  recognitionToday: () => request("/api/recognition/today"),
  recognitionStartRun: (scope, restart = false) =>
    postJson("/api/recognition/runs", { scope, restart }),
  recognitionReport: (runId, char, report) =>
    postJson(`/api/recognition/runs/${encodeURIComponent(runId)}/reports`, {
      char,
      report,
    }),
  recognitionRunItem: (runId, index) =>
    request(
      `/api/recognition/runs/${encodeURIComponent(runId)}/items/${encodeURIComponent(index)}`,
    ),
  recognitionPrint: () => request("/api/recognition/print"),
  recognitionItems: (query = "", limit = 60) =>
    request(
      `/api/recognition/items?query=${encodeURIComponent(query)}&limit=${encodeURIComponent(limit)}`,
    ),
  recognitionUpdateItem: (char, selfReport) =>
    request(`/api/recognition/items/${encodeURIComponent(char)}`, {
      method: "PATCH",
      headers: JSON_HEADERS,
      body: JSON.stringify({ self_report: selfReport }),
    }),
  recognitionAttempt: (char, correct, responseMs) =>
    postJson("/api/recognition/attempts", {
      char,
      correct,
      response_ms: responseMs,
    }),
  settings: () => request("/api/settings"),
  saveSettings: (values) => postJson("/api/settings", values),
  reset: () => request("/api/reset", { method: "POST" }),
};
