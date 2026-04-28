import { useEffect, useMemo, useState } from "react";
import { dashboardApi, isDesktop, subscribeTeam } from "./api.js";
import logoUrl from "./assets/logo.png";
import terminalIcon from "./assets/client/terminal.png";
import itermIcon from "./assets/client/iterm.png";
import ghosttyIcon from "./assets/client/ghostty.png";
import vscodeIcon from "./assets/client/vscode.png";
import cursorIcon from "./assets/client/cursor.png";
import claudeIcon from "./assets/agent/claude-code.png";
import codexIcon from "./assets/agent/codex.png";
import geminiIcon from "./assets/agent/gemini.png";
import nanobotIcon from "./assets/agent/nanobot.png";

function StatusGlyph({ status }) {
  const common = {
    width: 12,
    height: 12,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2.4,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
  };
  switch (status) {
    case "pending":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 2" />
        </svg>
      );
    case "in_progress":
      return (
        <svg {...common}>
          <path d="M21 12a9 9 0 1 1-9-9" />
          <path d="M21 4v5h-5" />
        </svg>
      );
    case "completed":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" />
          <path d="M8 12.5l3 3 5-6" />
        </svg>
      );
    case "blocked":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" />
          <path d="M5.5 5.5l13 13" />
        </svg>
      );
    default:
      return null;
  }
}

const STATUSES = [
  { key: "pending", label: "Pending" },
  { key: "in_progress", label: "In progress" },
  { key: "completed", label: "Completed" },
  { key: "blocked", label: "Blocked" },
];

// The five clients clawteam knows how to spawn. Mirror of the wizard list in
// clawteam/cli/commands.py::profile_wizard. New clients must be added here
// AND in clawteam's `_normalize_client` / preset client_overrides.
const PROFILE_CLIENTS = [
  { id: "claude", label: "Claude Code", icon: claudeIcon, hint: "Anthropic CLI" },
  { id: "codex", label: "Codex", icon: codexIcon, hint: "OpenAI Codex CLI" },
  { id: "gemini", label: "Gemini", icon: geminiIcon, hint: "Google Gemini CLI" },
  { id: "kimi", label: "Kimi", icon: null, hint: "Moonshot Kimi CLI" },
  { id: "nanobot", label: "Nanobot", icon: nanobotIcon, hint: "Nanobot harness" },
];

const CLIENT_ICONS = {
  terminal: terminalIcon,
  iterm: itermIcon,
  ghostty: ghosttyIcon,
  vscode: vscodeIcon,
  cursor: cursorIcon,
};

const NAV_ITEMS = ["board", "agents", "profiles"];

const EMPTY_TEAM = {
  team: null,
  members: [],
  tasks: { pending: [], in_progress: [], completed: [], blocked: [] },
  taskSummary: { pending: 0, in_progress: 0, completed: 0, blocked: 0, total: 0 },
  messages: [],
  sessions: [],
  cost: {},
  conflicts: {},
};

function formatTime(value) {
  if (!value) return "never";
  const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    day: "2-digit",
  }).format(date);
}

function priorityRank(priority) {
  return { urgent: 0, high: 1, medium: 2, low: 3 }[priority] ?? 4;
}

function sortTasks(tasks) {
  return [...(tasks || [])].sort((left, right) => {
    const byPriority = priorityRank(left.priority) - priorityRank(right.priority);
    if (byPriority !== 0) return byPriority;
    return String(right.updatedAt || "").localeCompare(String(left.updatedAt || ""));
  });
}

export function App() {
  const [view, setView] = useState("board");
  const [teams, setTeams] = useState([]);
  const [selectedTeam, setSelectedTeam] = useState("");
  const [teamData, setTeamData] = useState(EMPTY_TEAM);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [runtime, setRuntime] = useState(null);
  const [runtimeLogs, setRuntimeLogs] = useState([]);
  const [profiles, setProfiles] = useState({});
  const [presets, setPresets] = useState({});
  const [wizardClient, setWizardClient] = useState("");
  const [wizardPreset, setWizardPreset] = useState("");
  const [wizardName, setWizardName] = useState("");
  const [wizardBusy, setWizardBusy] = useState(false);
  const [wizardNotice, setWizardNotice] = useState("");
  const [launchTargets, setLaunchTargets] = useState([]);
  const [profileDraft, setProfileDraft] = useState(defaultProfileDraft());
  const [profileName, setProfileName] = useState("");
  const [profileNotice, setProfileNotice] = useState("");
  const [sessionNotice, setSessionNotice] = useState("");
  const [taskDraft, setTaskDraft] = useState({ subject: "", owner: "", description: "" });
  const [taskModalOpen, setTaskModalOpen] = useState(false);
  const [taskNotice, setTaskNotice] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);

  useEffect(() => {
    let mounted = true;
    async function loadInitial() {
      try {
        const [overview, status, profileMap, targets, presetMap] = await Promise.all([
          dashboardApi.listTeams(),
          dashboardApi.getRuntimeStatus().catch(() => null),
          dashboardApi.listProfiles().catch(() => ({})),
          dashboardApi.listLaunchTargets().catch(() => []),
          dashboardApi.listPresets().catch(() => ({})),
        ]);
        if (!mounted) return;
        setTeams(overview);
        setRuntime(status);
        setProfiles(profileMap);
        setLaunchTargets(targets);
        setPresets(presetMap);
        if (overview.length > 0) {
          setSelectedTeam(overview[0].name);
        } else {
          setLoading(false);
        }
      } catch (err) {
        if (!mounted) return;
        setError(err.message);
        setLoading(false);
      }
    }
    loadInitial();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedTeam) return undefined;
    setLoading(true);
    setError("");
    dashboardApi
      .getTeam(selectedTeam)
      .then((data) => {
        setTeamData({ ...EMPTY_TEAM, ...data });
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setTeamData(EMPTY_TEAM);
        setLoading(false);
      });

    return subscribeTeam(
      selectedTeam,
      (data) => {
        if (!data.error) {
          setTeamData({ ...EMPTY_TEAM, ...data });
          setLoading(false);
        }
      },
      (err) => setError(err.message),
    );
  }, [selectedTeam]);

  useEffect(() => {
    if (!taskModalOpen && !settingsOpen) return undefined;
    const onKey = (event) => {
      if (event.key !== "Escape") return;
      if (taskModalOpen) setTaskModalOpen(false);
      else if (settingsOpen) setSettingsOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [taskModalOpen, settingsOpen]);

  const sessionsByName = useMemo(() => {
    const map = new Map();
    for (const session of teamData.sessions || []) map.set(session.agentName, session);
    return map;
  }, [teamData.sessions]);

  const metrics = useMemo(() => {
    const summary = teamData.taskSummary || {};
    const sessions = teamData.sessions || [];
    return [
      { label: "Tasks", value: summary.total || 0 },
      { label: "Agents", value: teamData.members?.length || 0 },
      { label: "Live sessions", value: sessions.filter((item) => item.alive === true).length },
      { label: "Conflicts", value: teamData.conflicts?.totalOverlaps || 0 },
    ];
  }, [teamData]);

  async function refreshRuntime() {
    const status = await dashboardApi.getRuntimeStatus();
    setRuntime(status);
  }

  async function runRuntimeAction(action) {
    setRuntimeLogs([`Starting ${action}...`]);
    try {
      const result =
        action === "install"
          ? await dashboardApi.installClawTeam()
          : await dashboardApi.upgradeClawTeam();
      setRuntimeLogs(result.logs || []);
      await refreshRuntime();
    } catch (err) {
      setRuntimeLogs((logs) => [...logs, `Error: ${err.message}`]);
    }
  }

  async function saveProfile() {
    if (!profileName.trim()) return;
    const result = await dashboardApi.saveProfile(profileName.trim(), normalizeProfile(profileDraft));
    setProfiles(result.profiles || (await dashboardApi.listProfiles()));
  }

  async function deleteProfile(name) {
    const result = await dashboardApi.removeProfile(name);
    setProfiles(result.profiles || (await dashboardApi.listProfiles()));
    if (profileName === name) {
      setProfileName("");
      setProfileDraft(defaultProfileDraft());
    }
  }

  async function testProfile(name) {
    setProfileNotice("");
    try {
      const result = await dashboardApi.testProfile(name);
      const code = result?.result?.returncode;
      setProfileNotice(code === 0 ? `Profile '${name}' passed.` : `Profile '${name}' returned ${code}.`);
    } catch (err) {
      setProfileNotice(err.message);
    }
  }

  function editProfile(name, profile) {
    setProfileName(name);
    setProfileDraft({
      description: profile.description || "",
      agent: profile.agent || "",
      command: (profile.command || []).join(" "),
      model: profile.model || "",
      base_url: profile.base_url || "",
      base_url_env: profile.base_url_env || "",
      api_key_env: profile.api_key_env || "",
      api_key_target_env: profile.api_key_target_env || "",
      env: mapToLines(profile.env),
      env_map: mapToLines(profile.env_map),
      args: (profile.args || []).join("\n"),
    });
  }

  function pickWizardClient(clientId) {
    setWizardNotice("");
    setWizardClient((prev) => {
      if (prev === clientId) return prev;
      setWizardPreset("");
      setWizardName("");
      return clientId;
    });
  }

  function pickWizardPreset(presetName) {
    setWizardNotice("");
    setWizardPreset(presetName);
    setWizardName(`${wizardClient}-${presetName}`);
  }

  async function generateFromWizard() {
    if (!wizardClient || !wizardPreset) return;
    setWizardBusy(true);
    setWizardNotice("");
    try {
      const result = await dashboardApi.generateProfileFromPreset({
        preset: wizardPreset,
        client: wizardClient,
        name: wizardName.trim() || undefined,
      });
      const next = result.profiles || (await dashboardApi.listProfiles());
      setProfiles(next);
      const generated = result.result?.profile || wizardName.trim() || `${wizardClient}-${wizardPreset}`;
      setWizardNotice(`Saved profile '${generated}'.`);
      const fresh = next[generated];
      if (fresh) editProfile(generated, fresh);
      setWizardClient("");
      setWizardPreset("");
      setWizardName("");
    } catch (err) {
      setWizardNotice(err.message);
    } finally {
      setWizardBusy(false);
    }
  }

  async function createTask() {
    if (!selectedTeam || !taskDraft.subject.trim()) {
      setTaskNotice("Subject is required.");
      return;
    }
    try {
      await dashboardApi.createTask(selectedTeam, taskDraft);
      setTaskDraft({ subject: "", owner: "", description: "" });
      setTaskNotice("");
      setTaskModalOpen(false);
      const next = await dashboardApi.getTeam(selectedTeam);
      setTeamData({ ...EMPTY_TEAM, ...next });
    } catch (err) {
      setTaskNotice(err.message);
    }
  }

  async function openSession(session, target) {
    setSessionNotice("");
    if (session?.alive !== true && ["terminal", "iterm", "ghostty"].includes(target)) {
      setSessionNotice(`Session '${session?.agentName || "agent"}' is offline.`);
      return;
    }
    try {
      const result = await dashboardApi.openSession({
        team: selectedTeam,
        session,
        target,
      });
      setSessionNotice(result.message || "Opened session.");
    } catch (err) {
      setSessionNotice(err.message);
    }
  }

  function openTeam(teamName) {
    setSelectedTeam(teamName);
    setView("board");
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <span className="brand-mark">
            <img src={logoUrl} alt="ClawTeam" />
          </span>
          <div>
            <div className="brand-title">ClawTeam</div>
            <div className="brand-subtitle">Operator Console</div>
          </div>
        </div>

        <nav className="nav-stack" aria-label="Dashboard views">
          {NAV_ITEMS.map((item) => (
            <button
              className={view === item ? "nav-item active" : "nav-item"}
              key={item}
              type="button"
              onClick={() => setView(item)}
            >
              <span>{item}</span>
            </button>
          ))}
        </nav>

        <div className="team-list">
          <div className="eyebrow">Teams</div>
          {teams.length === 0 ? (
            <p className="muted">No teams yet.</p>
          ) : (
            teams.map((team) => (
              <button
                className={selectedTeam === team.name ? "team-row selected" : "team-row"}
                key={team.name}
                type="button"
                onClick={() => openTeam(team.name)}
              >
                <span className="team-row-main">{team.name}</span>
                <span className="team-row-meta">{team.tasks} tasks</span>
              </button>
            ))
          )}
        </div>

        <SettingsFabTrigger
          runtime={runtime}
          open={settingsOpen}
          onToggle={() => setSettingsOpen((value) => !value)}
        />
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div>
            <div className="eyebrow">{viewEyebrow(view)}</div>
            <h1>{topbarTitle(view, teamData, selectedTeam)}</h1>
          </div>
          <div className="topbar-actions">
            {view === "board" ? (
              <button
                type="button"
                className="primary-action"
                disabled={!selectedTeam}
                onClick={() => {
                  setTaskNotice("");
                  setTaskModalOpen(true);
                }}
              >
                <span className="plus-glyph" aria-hidden="true">+</span>
                <span>Task</span>
              </button>
            ) : null}
          </div>
        </header>

        {error ? <div className="notice danger">{error}</div> : null}
        {loading && view === "board" ? <div className="notice">Loading board data...</div> : null}

        {view === "board" && (
          <BoardView
            data={teamData}
            metrics={metrics}
            sessionsByName={sessionsByName}
          />
        )}
        {view === "agents" && (
          <AgentsView
            data={teamData}
            launchTargets={launchTargets}
            onOpenSession={openSession}
            notice={sessionNotice}
          />
        )}
        {view === "profiles" && (
          <ProfilesView
            profiles={profiles}
            profileName={profileName}
            setProfileName={setProfileName}
            profileDraft={profileDraft}
            setProfileDraft={setProfileDraft}
            editProfile={editProfile}
            saveProfile={saveProfile}
            deleteProfile={deleteProfile}
            testProfile={testProfile}
            profileNotice={profileNotice}
            presets={presets}
            wizardClient={wizardClient}
            wizardPreset={wizardPreset}
            wizardName={wizardName}
            setWizardName={setWizardName}
            pickWizardClient={pickWizardClient}
            pickWizardPreset={pickWizardPreset}
            wizardNotice={wizardNotice}
            wizardBusy={wizardBusy}
            generateFromWizard={generateFromWizard}
          />
        )}
      </main>

      {settingsOpen ? (
        <SettingsPopover onClose={() => setSettingsOpen(false)}>
          <SettingsView
            runtime={runtime}
            launchTargets={launchTargets}
            logs={runtimeLogs}
            refreshRuntime={refreshRuntime}
            runRuntimeAction={runRuntimeAction}
          />
        </SettingsPopover>
      ) : null}

      {taskModalOpen ? (
        <NewTaskModal
          team={selectedTeam}
          draft={taskDraft}
          setDraft={setTaskDraft}
          notice={taskNotice}
          onCancel={() => setTaskModalOpen(false)}
          onSubmit={createTask}
        />
      ) : null}
    </div>
  );
}

function viewEyebrow(view) {
  switch (view) {
    case "board":
      return "Kanban command center";
    case "agents":
      return "Agent sessions";
    case "profiles":
      return "Agent profiles";
    case "settings":
      return "Runtime & launchers";
    default:
      return "";
  }
}

function topbarTitle(view, teamData, selectedTeam) {
  if (view === "board") {
    return teamData.team?.name || selectedTeam || "No team selected";
  }
  return view.charAt(0).toUpperCase() + view.slice(1);
}

function displayVersion(value) {
  const text = String(value || "").trim();
  if (!text || text === "unknown") return "unknown";
  const twoPart = text.match(/^([1-9]\d*)\.(\d+)$/);
  if (twoPart) return `0.${twoPart[1]}.${twoPart[2]}`;
  return text;
}

function BoardView({ data, metrics, sessionsByName }) {
  return (
    <div className="board-layout">
      <section className="metrics-band">
        {metrics.map((metric) => (
          <div className="metric" key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
          </div>
        ))}
      </section>

      <section className="kanban">
        {STATUSES.map((status) => (
          <div className={`kanban-column ${status.key}`} key={status.key}>
            <div className="column-header">
              <span className={`column-code status-${status.key}`}>
                <StatusGlyph status={status.key} />
              </span>
              <h2>{status.label}</h2>
              <span>{data.taskSummary?.[status.key] || 0}</span>
            </div>
            <div className="task-stack">
              {sortTasks(data.tasks?.[status.key]).map((task) => {
                const session = sessionsByName.get(task.owner);
                return <TaskCard key={task.id} task={task} session={session} />;
              })}
            </div>
          </div>
        ))}
      </section>

      <aside className="inspector single">
        <section className="panel-section">
          <div className="section-heading">
            <h3>Messages</h3>
            <span>{data.messages?.length || 0}</span>
          </div>
          <div className="message-feed">
            {(data.messages || []).slice(-8).reverse().map((message, index) => (
              <div className="message-row" key={`${message.timestamp}-${index}`}>
                <div>
                  <strong>{message.fromLabel || message.from || "system"}</strong>
                  <span>{message.toLabel || message.to || "all"}</span>
                </div>
                <p>{message.content || message.type || "event"}</p>
              </div>
            ))}
            {(data.messages || []).length === 0 ? (
              <p className="muted">No activity yet.</p>
            ) : null}
          </div>
        </section>
      </aside>
    </div>
  );
}

function TaskCard({ task, session }) {
  return (
    <article className="task-card">
      <div className="task-meta">
        <span>{task.priority || "medium"}</span>
        <span>{task.id}</span>
      </div>
      <h3>{task.subject}</h3>
      {task.description ? <p>{task.description}</p> : null}
      <div className="task-footer">
        <span>{task.owner || "unassigned"}</span>
        <span className={session?.alive ? "live-pill" : "live-pill off"}>
          {session?.alive ? "live" : "idle"}
        </span>
      </div>
      {task.blockedBy?.length ? <div className="blocked-by">blocked by {task.blockedBy.join(", ")}</div> : null}
    </article>
  );
}

function AgentsView({ data, launchTargets, onOpenSession, notice }) {
  return (
    <div className="wide-grid">
      <section className="table-panel">
        <div className="section-heading">
          <h3>Agent sessions</h3>
          <span>{data.sessions?.length || 0} registered</span>
        </div>
        <div className="agent-table">
          {(data.sessions || []).length === 0 ? (
            <p className="muted">No registered sessions.</p>
          ) : (
            (data.sessions || []).map((session) => {
              const sessionAlive = session.alive === true;
              const canAttach = (target) =>
                sessionAlive || !["terminal", "iterm", "ghostty"].includes(target.id);
              const sessionRef = session.sessionId
                ? `session ${session.sessionId}`
                : session.target || session.pid || "";
              const sessionMeta = session.sessionId
                ? [
                    session.sessionClient,
                    session.sessionConfidence,
                    session.sessionSource,
                  ].filter(Boolean).join(" · ")
                : "";
              return (
                <div className={sessionAlive ? "agent-row" : "agent-row offline"} key={session.agentName}>
                  <div>
                    <strong>{session.agentName}</strong>
                    <span>{session.backend} {sessionRef}</span>
                    {sessionMeta ? <span className="session-meta">{sessionMeta}</span> : null}
                  </div>
                  <span className={sessionAlive ? "live-pill" : "live-pill off"}>
                    {sessionAlive ? "running" : "offline"}
                  </span>
                  <div className="row-actions">
                    {launchTargets.map((target) => (
                      <button
                        disabled={!target.available || !canAttach(target)}
                        key={target.id}
                        type="button"
                        title={!canAttach(target) ? "Session is offline" : target.description}
                        onClick={() => onOpenSession(session, target.id)}
                      >
                        {target.label}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })
          )}
        </div>
        {notice ? <div className="notice">{notice}</div> : null}
      </section>
    </div>
  );
}

function ProfilesView({
  profiles,
  profileName,
  setProfileName,
  profileDraft,
  setProfileDraft,
  editProfile,
  saveProfile,
  deleteProfile,
  testProfile,
  profileNotice,
  presets,
  wizardClient,
  wizardPreset,
  wizardName,
  setWizardName,
  pickWizardClient,
  pickWizardPreset,
  wizardNotice,
  wizardBusy,
  generateFromWizard,
}) {
  const presetEntries = useMemo(() => Object.entries(presets || {}), [presets]);

  const compatiblePresets = useMemo(() => {
    if (!wizardClient) return [];
    return presetEntries
      .filter(([, item]) => Boolean(item?.preset?.client_overrides?.[wizardClient]))
      .sort(([a], [b]) => a.localeCompare(b));
  }, [presetEntries, wizardClient]);

  return (
    <div className="profile-grid">
      <section className="table-panel">
        <div className="section-heading">
          <h3>New profile</h3>
          <span>preset → client</span>
        </div>

        <div className="wizard-step">
          <div className="wizard-step-head">
            <span className="step-index">1</span>
            <span className="eyebrow">Choose a client</span>
          </div>
          <div className="wizard-grid">
            {PROFILE_CLIENTS.map((client) => (
              <button
                type="button"
                key={client.id}
                className={
                  wizardClient === client.id ? "wizard-tile selected" : "wizard-tile"
                }
                disabled={!isDesktop}
                onClick={() => pickWizardClient(client.id)}
                title={client.hint}
              >
                <span className="wizard-icon">
                  {client.icon ? (
                    <img src={client.icon} alt="" />
                  ) : (
                    <span className="wizard-fallback">{client.label.slice(0, 2)}</span>
                  )}
                </span>
                <span className="wizard-meta">
                  <strong>{client.label}</strong>
                  <span>{client.hint}</span>
                </span>
              </button>
            ))}
          </div>
        </div>

        <div className={wizardClient ? "wizard-step" : "wizard-step disabled"}>
          <div className="wizard-step-head">
            <span className="step-index">2</span>
            <span className="eyebrow">Choose a provider</span>
            {wizardClient ? (
              <span className="muted" style={{ marginLeft: "auto" }}>
                {compatiblePresets.length} support {wizardClient}
              </span>
            ) : null}
          </div>
          {wizardClient ? (
            compatiblePresets.length === 0 ? (
              <p className="muted">No presets define a {wizardClient} override. Use Advanced below.</p>
            ) : (
              <div className="preset-list">
                {compatiblePresets.map(([name, item]) => {
                  const preset = item.preset || {};
                  const selected = wizardPreset === name;
                  return (
                    <button
                      type="button"
                      key={name}
                      className={selected ? "preset-row selected" : "preset-row"}
                      disabled={!isDesktop}
                      onClick={() => pickWizardPreset(name)}
                    >
                      <div className="preset-row-main">
                        <strong>{name}</strong>
                        <span className="preset-source">{item.source || "builtin"}</span>
                      </div>
                      <p className="preset-row-desc">
                        {preset.description || "Recommended provider setup"}
                      </p>
                      <div className="preset-row-meta">
                        {preset.auth_env ? (
                          <span>
                            <em>auth</em> {preset.auth_env}
                          </span>
                        ) : null}
                        {preset.client_overrides?.[wizardClient]?.model ? (
                          <span>
                            <em>model</em> {preset.client_overrides[wizardClient].model}
                          </span>
                        ) : null}
                        {preset.client_overrides?.[wizardClient]?.base_url || preset.base_url ? (
                          <span>
                            <em>endpoint</em>{" "}
                            {preset.client_overrides[wizardClient]?.base_url ||
                              preset.base_url}
                          </span>
                        ) : null}
                      </div>
                    </button>
                  );
                })}
              </div>
            )
          ) : (
            <p className="muted">Pick a client first.</p>
          )}
        </div>

        <div className={wizardPreset ? "wizard-step" : "wizard-step disabled"}>
          <div className="wizard-step-head">
            <span className="step-index">3</span>
            <span className="eyebrow">Profile name</span>
          </div>
          <div className="wizard-name-row">
            <input
              value={wizardName}
              disabled={!wizardPreset || !isDesktop}
              onChange={(event) => setWizardName(event.target.value)}
              placeholder={wizardClient && wizardPreset ? `${wizardClient}-${wizardPreset}` : "name"}
            />
            <button
              type="button"
              className="primary-action"
              disabled={!isDesktop || !wizardClient || !wizardPreset || wizardBusy}
              onClick={generateFromWizard}
            >
              {wizardBusy ? "Generating…" : "Generate"}
            </button>
          </div>
          {wizardNotice ? <div className="notice">{wizardNotice}</div> : null}
        </div>

        <div className="section-heading" style={{ marginTop: 18 }}>
          <h3>Saved profiles</h3>
          <span>{Object.keys(profiles).length} configured</span>
        </div>
        {Object.keys(profiles).length === 0 ? (
          <p className="muted">
            No saved profiles yet — pick a client + provider above, or use Advanced for a custom command.
          </p>
        ) : null}
        {Object.entries(profiles).map(([name, profile]) => (
          <div className="profile-row" key={name}>
            <div>
              <strong>{name}</strong>
              <span>
                {profile.agent || profile.command?.join(" ") || "custom command"}
                {profile.model ? ` · ${profile.model}` : ""}
              </span>
            </div>
            <button type="button" onClick={() => editProfile(name, profile)}>
              Edit
            </button>
            <button disabled={!isDesktop} type="button" onClick={() => testProfile(name)}>
              Test
            </button>
            <button type="button" onClick={() => deleteProfile(name)}>
              Delete
            </button>
          </div>
        ))}
        {profileNotice ? <div className="notice">{profileNotice}</div> : null}
        {!isDesktop ? <div className="notice">Profile editing is enabled in the desktop app.</div> : null}
      </section>

      <section className="editor-panel">
        <div className="section-heading">
          <h3>Advanced editor</h3>
          <span>raw fields</span>
        </div>
        <p className="muted" style={{ fontSize: 12, margin: 0 }}>
          Hand-tune any AgentProfile field. Useful for custom endpoints, extra env, or
          tweaking a generated profile.
        </p>
        <input value={profileName} onChange={(e) => setProfileName(e.target.value)} placeholder="profile name" />
        {Object.keys(profileDraft).map((key) =>
          key === "env" || key === "env_map" || key === "args" ? (
            <textarea
              key={key}
              rows={key === "args" ? 3 : 5}
              value={profileDraft[key]}
              onChange={(e) => setProfileDraft({ ...profileDraft, [key]: e.target.value })}
              placeholder={key === "args" ? "one arg per line" : "KEY=VALUE, one per line"}
            />
          ) : (
            <input
              key={key}
              value={profileDraft[key]}
              onChange={(e) => setProfileDraft({ ...profileDraft, [key]: e.target.value })}
              placeholder={key}
            />
          ),
        )}
        <button disabled={!isDesktop} type="button" onClick={saveProfile}>
          Save profile
        </button>
      </section>
    </div>
  );
}

function SettingsView({ runtime, launchTargets, logs, refreshRuntime, runRuntimeAction }) {
  const upgradeAvailable = runtime?.upgrade_available;
  const installed = runtime?.installed;
  const currentVersion = displayVersion(runtime?.current_version || runtime?.latest_version);
  return (
    <div className="settings-stack">
      <section className="runtime-card">
        <div className="runtime-card-head">
          <div>
            <div className="eyebrow">ClawTeam runtime</div>
            <h2 className="runtime-version">
              {installed ? `v${currentVersion}` : "Not installed"}
            </h2>
            {installed ? (
              <p className="muted">
                {upgradeAvailable ? `Update available: v${displayVersion(runtime?.latest_version)}` : "Runtime is current."}
              </p>
            ) : (
              <p className="muted">Install ClawTeam to start serving the board.</p>
            )}
          </div>
          <div className="runtime-card-actions">
            <button type="button" onClick={refreshRuntime}>
              Check
            </button>
            {!installed ? (
              <button
                type="button"
                className="primary-action"
                disabled={!isDesktop}
                onClick={() => runRuntimeAction("install")}
              >
                Install
              </button>
            ) : (
              <button
                type="button"
                className={upgradeAvailable ? "primary-action" : ""}
                disabled={!isDesktop || !upgradeAvailable}
                onClick={() => runRuntimeAction("upgrade")}
              >
                {upgradeAvailable ? "Upgrade" : "Up to date"}
              </button>
            )}
          </div>
        </div>

        {logs.length ? (
          <details className="install-log">
            <summary>Install log</summary>
            <pre>{logs.join("\n")}</pre>
          </details>
        ) : null}

        {!isDesktop ? (
          <div className="notice">Install and upgrade run only in the desktop app.</div>
        ) : null}
      </section>

      <section className="settings-section">
        <div className="section-heading">
          <h3>Launch with</h3>
          <span>open agent sessions</span>
        </div>
        <div className="client-grid">
          {launchTargets.map((target) => (
            <ClientTile key={target.id} target={target} />
          ))}
          {launchTargets.length === 0 ? (
            <p className="muted">No launchers detected.</p>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function ClientTile({ target }) {
  const icon = CLIENT_ICONS[target.id];
  const initials = target.label.slice(0, 2).toUpperCase();
  return (
    <div className={target.available ? "client-tile" : "client-tile unavailable"}>
      <div className="client-icon" aria-hidden="true">
        {icon ? <img src={icon} alt="" /> : <span className="client-fallback">{initials}</span>}
      </div>
      <div className="client-meta">
        <strong>{target.label}</strong>
        <span>{target.description}</span>
      </div>
      <span className={target.available ? "client-status" : "client-status off"}>
        {target.available ? "ready" : "missing"}
      </span>
    </div>
  );
}

function SettingsFabTrigger({ runtime, open, onToggle }) {
  const status = !runtime?.installed
    ? "off"
    : runtime?.upgrade_available
    ? "warn"
    : "ok";
  const label = runtime?.installed
    ? `v${displayVersion(runtime?.current_version)}`
    : "not installed";
  return (
    <button
      id="settings-trigger"
      type="button"
      className={open ? "settings-trigger open" : "settings-trigger"}
      aria-label="Open settings"
      aria-expanded={open}
      onClick={onToggle}
    >
      <span className={`status-dot ${status === "ok" ? "" : status}`.trim()} />
      <span className="settings-trigger-label">{label}</span>
      <span className="settings-trigger-glyph" aria-hidden="true">⚙</span>
    </button>
  );
}

function SettingsPopover({ onClose, children }) {
  useEffect(() => {
    const onDown = (event) => {
      const popover = document.getElementById("settings-popover");
      const trigger = document.getElementById("settings-trigger");
      if (popover && popover.contains(event.target)) return;
      if (trigger && trigger.contains(event.target)) return;
      onClose();
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [onClose]);

  return (
    <div
      id="settings-popover"
      className="settings-popover"
      role="dialog"
      aria-label="Settings"
    >
      <div className="settings-popover-head">
        <span className="eyebrow">Runtime &amp; launchers</span>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>
      <div className="settings-popover-body">{children}</div>
    </div>
  );
}

function NewTaskModal({ team, draft, setDraft, notice, onCancel, onSubmit }) {
  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <div className="modal">
        <header className="modal-head">
          <div>
            <div className="eyebrow">{team || "no team"}</div>
            <h2>New task</h2>
          </div>
          <button type="button" className="icon-button" onClick={onCancel} aria-label="Close">
            ×
          </button>
        </header>
        <div className="modal-body">
          <label className="field">
            <span>Subject</span>
            <input
              autoFocus
              value={draft.subject}
              onChange={(event) => setDraft({ ...draft, subject: event.target.value })}
              placeholder="What needs doing?"
            />
          </label>
          <label className="field">
            <span>Owner</span>
            <input
              value={draft.owner}
              onChange={(event) => setDraft({ ...draft, owner: event.target.value })}
              placeholder="Agent name"
            />
          </label>
          <label className="field">
            <span>Description</span>
            <textarea
              rows={5}
              value={draft.description}
              onChange={(event) => setDraft({ ...draft, description: event.target.value })}
              placeholder="Context, acceptance criteria, links…"
            />
          </label>
          {notice ? <div className="notice danger">{notice}</div> : null}
        </div>
        <footer className="modal-foot">
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            className="primary-action"
            disabled={!team || !draft.subject.trim()}
            onClick={onSubmit}
          >
            Create task
          </button>
        </footer>
      </div>
    </div>
  );
}

function defaultProfileDraft() {
  return {
    description: "",
    agent: "",
    command: "",
    model: "",
    base_url: "",
    base_url_env: "",
    api_key_env: "",
    api_key_target_env: "",
    env: "",
    env_map: "",
    args: "",
  };
}

function linesToMap(raw) {
  const result = {};
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || !trimmed.includes("=")) continue;
    const [key, ...rest] = trimmed.split("=");
    result[key] = rest.join("=");
  }
  return result;
}

function mapToLines(map = {}) {
  return Object.entries(map).map(([key, value]) => `${key}=${value}`).join("\n");
}

function normalizeProfile(draft) {
  return {
    description: draft.description,
    agent: draft.agent,
    command: splitCommand(draft.command),
    model: draft.model,
    base_url: draft.base_url,
    base_url_env: draft.base_url_env,
    api_key_env: draft.api_key_env,
    api_key_target_env: draft.api_key_target_env,
    env: linesToMap(draft.env),
    env_map: linesToMap(draft.env_map),
    args: draft.args.split(/\r?\n/).map((line) => line.trim()).filter(Boolean),
  };
}

function splitCommand(command) {
  return command.match(/(?:[^\s"']+|"[^"]*"|'[^']*')+/g)?.map((part) => part.replace(/^["']|["']$/g, "")) || [];
}
