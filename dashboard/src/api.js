const DESKTOP_API = window.clawteamDesktop || null;

async function requestJson(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.error || body.message || `Request failed: ${response.status}`);
  }
  return body;
}

export const isDesktop = Boolean(DESKTOP_API);

export const dashboardApi = {
  listTeams() {
    return requestJson("/api/overview");
  },
  getTeam(team) {
    return requestJson(`/api/team/${encodeURIComponent(team)}`);
  },
  createTask(team, payload) {
    return requestJson(`/api/team/${encodeURIComponent(team)}/task`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  getRuntimeStatus() {
    if (DESKTOP_API) return DESKTOP_API.getRuntimeStatus();
    return requestJson("/api/runtime/status");
  },
  installClawTeam() {
    if (!DESKTOP_API) {
      return Promise.reject(new Error("Install is available in the desktop app."));
    }
    return DESKTOP_API.installClawTeam();
  },
  upgradeClawTeam() {
    if (!DESKTOP_API) {
      return Promise.reject(new Error("Upgrade is available in the desktop app."));
    }
    return DESKTOP_API.upgradeClawTeam();
  },
  listProfiles() {
    if (!DESKTOP_API) return Promise.resolve({});
    return DESKTOP_API.listProfiles();
  },
  saveProfile(name, profile) {
    if (!DESKTOP_API) {
      return Promise.reject(new Error("Profile editing is available in the desktop app."));
    }
    return DESKTOP_API.saveProfile(name, profile);
  },
  removeProfile(name) {
    if (!DESKTOP_API) {
      return Promise.reject(new Error("Profile editing is available in the desktop app."));
    }
    return DESKTOP_API.removeProfile(name);
  },
  testProfile(name) {
    if (!DESKTOP_API) {
      return Promise.reject(new Error("Profile testing is available in the desktop app."));
    }
    return DESKTOP_API.testProfile(name);
  },
  listPresets() {
    if (!DESKTOP_API) return Promise.resolve({});
    return DESKTOP_API.listPresets();
  },
  generateProfileFromPreset(payload) {
    if (!DESKTOP_API) {
      return Promise.reject(new Error("Profile generation is available in the desktop app."));
    }
    return DESKTOP_API.generateProfileFromPreset(payload);
  },
  listLaunchTargets() {
    if (!DESKTOP_API) return Promise.resolve([]);
    return DESKTOP_API.listLaunchTargets();
  },
  openSession(payload) {
    if (!DESKTOP_API) {
      return Promise.reject(new Error("Session opening is available in the desktop app."));
    }
    return DESKTOP_API.openSession(payload);
  },
  getBoardStatus() {
    if (!DESKTOP_API) return Promise.resolve({ status: "running", port: 0, url: "" });
    return DESKTOP_API.getBoardStatus();
  },
  ensureBoard() {
    if (!DESKTOP_API) return Promise.resolve({ status: "running", port: 0, url: "" });
    return DESKTOP_API.ensureBoard();
  },
  restartBoard() {
    if (!DESKTOP_API) {
      return Promise.reject(new Error("Board restart is available in the desktop app."));
    }
    return DESKTOP_API.restartBoard();
  },
};

export function subscribeTeam(team, onData, onError) {
  if (!team) return () => {};
  const source = new EventSource(`/api/events/${encodeURIComponent(team)}`);
  source.onmessage = (event) => {
    try {
      onData(JSON.parse(event.data));
    } catch (error) {
      onError?.(error);
    }
  };
  source.onerror = () => {
    onError?.(new Error("Live connection interrupted."));
  };
  return () => source.close();
}
