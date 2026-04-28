import fs from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync } from "node:child_process";
import { app, BrowserWindow, ipcMain, shell } from "electron";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..", "..");
const DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL;
const PYPI_URL = "https://pypi.org/pypi/clawteam/json";
const CLAWTEAM_HOME = path.join(os.homedir(), ".clawteam");
const VENV_PATH = path.join(CLAWTEAM_HOME, ".venv");
const BIN_DIR = path.join(os.homedir(), ".local", "bin");
const BOARD_HOST = "127.0.0.1";
const BOARD_PREFERRED_PORT = Number(process.env.CLAWTEAM_BOARD_PORT) || 8780;
const BOARD_LOG_LIMIT = 200;

let mainWindow = null;

if (!app.requestSingleInstanceLock()) {
  app.quit();
}

const boardManager = createBoardManager();

function createBoardManager() {
  const state = {
    child: null,
    port: 0,
    status: "idle", // idle | starting | running | stopped | failed
    error: null,
    logs: [],
    startingPromise: null,
  };

  function appendLog(line) {
    if (!line) return;
    state.logs.push(line);
    if (state.logs.length > BOARD_LOG_LIMIT) {
      state.logs.splice(0, state.logs.length - BOARD_LOG_LIMIT);
    }
  }

  function snapshot() {
    return {
      status: state.status,
      port: state.port,
      url: state.port ? `http://${BOARD_HOST}:${state.port}/` : "",
      error: state.error,
      logs: state.logs.slice(-50),
    };
  }

  async function ensure() {
    if (state.status === "running" && state.child && !state.child.killed) {
      return snapshot();
    }
    if (state.startingPromise) return state.startingPromise;

    state.startingPromise = (async () => {
      const cmd = resolveClawTeamCommand();
      if (!cmd) {
        state.status = "failed";
        state.error = "clawteam command was not found. Install it from the Settings panel.";
        appendLog(state.error);
        return snapshot();
      }

      state.status = "starting";
      state.error = null;

      const port = await pickPort(BOARD_PREFERRED_PORT);
      state.port = port;

      const child = spawn(
        cmd,
        ["board", "serve", "--host", BOARD_HOST, "--port", String(port), "--interval", "2"],
        {
          env: commandEnv(),
          cwd: REPO_ROOT,
          stdio: ["ignore", "pipe", "pipe"],
        },
      );
      state.child = child;
      appendLog(`spawn ${cmd} board serve --host ${BOARD_HOST} --port ${port}`);

      child.stdout.on("data", (chunk) => appendLog(`[board] ${String(chunk).trimEnd()}`));
      child.stderr.on("data", (chunk) => appendLog(`[board:err] ${String(chunk).trimEnd()}`));
      child.on("error", (error) => {
        appendLog(`[board:error] ${error.message}`);
      });
      child.on("exit", (code, signal) => {
        appendLog(`[board] exited code=${code ?? "null"} signal=${signal ?? "null"}`);
        if (state.child === child) {
          state.child = null;
          if (state.status !== "stopped") {
            state.status = code === 0 ? "stopped" : "failed";
            if (state.status === "failed") {
              state.error = `board server exited (code=${code ?? "?"})`;
            }
          }
        }
      });

      try {
        await waitForBoardReady(port, 15_000);
        state.status = "running";
      } catch (error) {
        state.status = "failed";
        state.error = error.message;
        appendLog(`[board:ready] ${error.message}`);
        try {
          child.kill("SIGTERM");
        } catch {
          /* ignore */
        }
      }

      return snapshot();
    })();

    try {
      return await state.startingPromise;
    } finally {
      state.startingPromise = null;
    }
  }

  function stop() {
    const child = state.child;
    if (!child || child.killed) {
      state.status = "stopped";
      state.child = null;
      return;
    }
    state.status = "stopped";
    try {
      child.kill("SIGTERM");
    } catch {
      /* ignore */
    }
    setTimeout(() => {
      if (state.child === child && !child.killed) {
        try {
          child.kill("SIGKILL");
        } catch {
          /* ignore */
        }
      }
    }, 1500);
  }

  return { ensure, stop, snapshot };
}

function pickPort(preferred) {
  return tryPort(preferred).catch(() => tryPort(0));
}

function tryPort(port) {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once("error", reject);
    server.listen({ host: BOARD_HOST, port }, () => {
      const address = server.address();
      const chosen = typeof address === "object" && address ? address.port : port;
      server.close(() => resolve(chosen));
    });
  });
}

async function waitForBoardReady(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`http://${BOARD_HOST}:${port}/api/overview`, {
        signal: AbortSignal.timeout(2000),
      });
      if (response.ok) return;
      lastError = new Error(`HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`board server did not become ready: ${lastError?.message || "timeout"}`);
}

function loadRendererURL(win) {
  if (DEV_SERVER_URL) {
    void win.loadURL(DEV_SERVER_URL);
    return;
  }
  const snap = boardManager.snapshot();
  if (snap.url) {
    void win.loadURL(snap.url);
  } else {
    void win.loadFile(path.join(REPO_ROOT, "clawteam", "board", "static", "index.html"));
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1320,
    height: 860,
    minWidth: 1040,
    minHeight: 720,
    backgroundColor: "#f6f4ef",
    title: "ClawTeam",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  loadRendererURL(mainWindow);
}

app.whenReady().then(async () => {
  await boardManager.ensure().catch(() => null);
  createWindow();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

app.on("before-quit", () => {
  boardManager.stop();
});

for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(signal, () => {
    boardManager.stop();
    app.quit();
  });
}

function buildShellPath() {
  const home = os.homedir();
  const segments = [
    path.join(REPO_ROOT, ".venv", "bin"),
    path.join(home, ".clawteam", ".venv", "bin"),
    path.join(home, ".local", "bin"),
    path.join(home, "bin"),
    "/opt/homebrew/bin",
    "/opt/homebrew/sbin",
    "/usr/local/bin",
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
  ];
  if (process.env.PATH) segments.push(...process.env.PATH.split(":"));
  return [...new Set(segments.filter(Boolean))].join(":");
}

function commandEnv() {
  return { ...process.env, PATH: buildShellPath() };
}

function resolveCommandPath(command) {
  if (!command) return "";
  const result = spawnSync("/bin/sh", ["-lc", `command -v ${shellQuote(command)}`], {
    env: commandEnv(),
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  });
  if (result.status !== 0) return "";
  return String(result.stdout || "").trim().split(/\r?\n/).pop() || "";
}

function resolveClawTeamCommand() {
  const candidates = [
    path.join(REPO_ROOT, ".venv", "bin", "clawteam"),
    path.join(VENV_PATH, "bin", "clawteam"),
    path.join(BIN_DIR, "clawteam"),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return resolveCommandPath("clawteam");
}

function shellQuote(value) {
  return `'${String(value).replace(/'/g, "'\\''")}'`;
}

function parseVersion(raw) {
  // Accept output like "clawteam v0.3.0" — `v` butts against the digits, so we
  // can't anchor on `\b` before the number; instead require a non-digit (or
  // start of string) immediately before, which keeps numbers inside paths from
  // matching while still capturing the leading "0".
  const match = String(raw || "").match(/(?:^|[^\d.])(\d+\.\d+(?:\.\d+)?(?:[\w.+-]*)?)/);
  return match ? match[1] : null;
}

function projectVersion() {
  try {
    const pyproject = fs.readFileSync(path.join(REPO_ROOT, "pyproject.toml"), "utf8");
    return pyproject.match(/^version\s*=\s*"([^"]+)"/m)?.[1] || "";
  } catch {
    return "";
  }
}

function normalizeRuntimeVersion(value) {
  const text = String(value || "").trim();
  const local = projectVersion();
  if (local && text && local.endsWith(text)) return local;
  return text || null;
}

function versionKey(value) {
  return String(value || "")
    .match(/\d+/g)
    ?.slice(0, 4)
    .map((part) => Number(part)) || [];
}

function isNewer(latest, current) {
  const l = versionKey(latest);
  const c = versionKey(current);
  if (!l.length || !c.length) return false;
  for (let index = 0; index < Math.max(l.length, c.length); index += 1) {
    const diff = (l[index] || 0) - (c[index] || 0);
    if (diff !== 0) return diff > 0;
  }
  return false;
}

function currentVersion() {
  const cmd = resolveClawTeamCommand();
  if (!cmd) return null;
  const result = spawnSync(cmd, ["--version"], {
    env: commandEnv(),
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout: 8000,
  });
  return normalizeRuntimeVersion(parseVersion(`${result.stdout || ""} ${result.stderr || ""}`));
}

async function latestVersion() {
  try {
    const response = await fetch(PYPI_URL, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(4000),
    });
    if (!response.ok) return null;
    const payload = await response.json();
    return normalizeRuntimeVersion(payload?.info?.version);
  } catch {
    return null;
  }
}

async function runtimeStatus() {
  const commandPath = resolveClawTeamCommand();
  const current = currentVersion();
  const latest = await latestVersion();
  const displayLatest = isNewer(current, latest) ? current : latest;
  return {
    installed: Boolean(commandPath || current),
    current_version: current,
    latest_version: displayLatest,
    upgrade_available: isNewer(latest, current),
    command_path: commandPath,
    install_root: CLAWTEAM_HOME,
    platform: process.platform,
    source: "pypi",
  };
}

function runLogged(file, args, logs, options = {}) {
  return new Promise((resolve) => {
    const child = spawn(file, args, {
      env: commandEnv(),
      cwd: options.cwd || REPO_ROOT,
      stdio: ["ignore", "pipe", "pipe"],
    });
    child.stdout.on("data", (chunk) => logs.push(String(chunk).trimEnd()));
    child.stderr.on("data", (chunk) => logs.push(String(chunk).trimEnd()));
    child.on("error", (error) => {
      logs.push(`Error: ${error.message}`);
      resolve({ code: 1 });
    });
    child.on("close", (code) => resolve({ code: code || 0 }));
  });
}

function findPython() {
  for (const candidate of ["python3.12", "python3.11", "python3.10", "python3"]) {
    const resolved = resolveCommandPath(candidate);
    if (!resolved) continue;
    const result = spawnSync(resolved, ["-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"]);
    if (result.status === 0) return resolved;
  }
  return "";
}

async function installOrUpgradeClawTeam() {
  const logs = [];
  const python = findPython();
  if (!python) {
    return { ok: false, logs: ["Python 3.10+ was not found. Install Python and retry."] };
  }
  fs.mkdirSync(CLAWTEAM_HOME, { recursive: true });
  fs.mkdirSync(BIN_DIR, { recursive: true });
  logs.push(`Using Python: ${python}`);

  if (!fs.existsSync(path.join(VENV_PATH, "bin", "python"))) {
    logs.push(`Creating virtual environment at ${VENV_PATH}`);
    const venv = await runLogged(python, ["-m", "venv", VENV_PATH], logs);
    if (venv.code !== 0) return { ok: false, logs };
  }

  const pip = path.join(VENV_PATH, "bin", "pip");
  logs.push("Upgrading pip");
  const pipResult = await runLogged(pip, ["install", "--upgrade", "pip"], logs);
  if (pipResult.code !== 0) return { ok: false, logs };

  logs.push("Installing latest clawteam from PyPI");
  const install = await runLogged(pip, ["install", "--upgrade", "clawteam"], logs);
  if (install.code !== 0) return { ok: false, logs };

  const target = path.join(VENV_PATH, "bin", "clawteam");
  const link = path.join(BIN_DIR, "clawteam");
  try {
    fs.rmSync(link, { force: true });
    fs.symlinkSync(target, link);
    logs.push(`Linked ${link} -> ${target}`);
  } catch (error) {
    logs.push(`Could not link ${link}: ${error.message}`);
  }
  logs.push("ClawTeam runtime is ready.");
  return { ok: true, logs };
}

function runClawTeam(args) {
  const cmd = resolveClawTeamCommand();
  if (!cmd) throw new Error("clawteam command was not found. Install ClawTeam first.");
  const result = spawnSync(cmd, args, {
    env: commandEnv(),
    cwd: REPO_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout: 20_000,
  });
  if (result.status !== 0) {
    throw new Error((result.stderr || result.stdout || "clawteam command failed").trim());
  }
  return result.stdout;
}

function jsonClawTeam(args) {
  const stdout = runClawTeam(["--json", ...args]);
  return JSON.parse(stdout || "{}");
}

function profileArgs(name, profile) {
  const args = ["profile", "set", name];
  const stringFields = [
    ["agent", "--agent"],
    ["description", "--description"],
    ["model", "--model"],
    ["base_url", "--base-url"],
    ["base_url_env", "--base-url-env"],
    ["api_key_env", "--api-key-env"],
    ["api_key_target_env", "--api-key-target-env"],
  ];
  for (const [field, flag] of stringFields) {
    if (profile[field]) args.push(flag, String(profile[field]));
  }
  if (Array.isArray(profile.command) && profile.command.length) {
    args.push("--command", profile.command.join(" "));
  }
  for (const [key, value] of Object.entries(profile.env || {})) args.push("--env", `${key}=${value}`);
  for (const [key, value] of Object.entries(profile.env_map || {})) args.push("--env-map", `${key}=${value}`);
  for (const value of profile.args || []) args.push("--arg", String(value));
  return args;
}

function appExists(name) {
  return (
    fs.existsSync(`/Applications/${name}.app`) ||
    fs.existsSync(path.join(os.homedir(), "Applications", `${name}.app`))
  );
}

function launchTargets() {
  return [
    { id: "terminal", label: "Terminal", description: "Attach tmux in Terminal.app", available: process.platform === "darwin" },
    { id: "iterm", label: "iTerm2", description: "Attach tmux in iTerm2", available: appExists("iTerm") || appExists("iTerm2") },
    { id: "ghostty", label: "Ghostty", description: "Attach tmux in Ghostty", available: appExists("Ghostty") || Boolean(resolveCommandPath("ghostty")) },
    { id: "vscode", label: "VS Code", description: "Open the repository in VS Code", available: Boolean(resolveCommandPath("code")) || appExists("Visual Studio Code") },
    { id: "cursor", label: "Cursor", description: "Open the repository in Cursor", available: Boolean(resolveCommandPath("cursor")) || appExists("Cursor") },
  ];
}

function appleScriptString(value) {
  return `"${String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

function tmuxAttachCommand(payload) {
  const team = payload?.team || "default";
  const session = payload?.session || {};
  const target = session.tmuxTarget || session.target || `clawteam-${team}`;
  const tmuxSession = String(target).split(":")[0] || `clawteam-${team}`;
  return `tmux attach -t ${shellQuote(tmuxSession)}`;
}

function openTerminalCommand(command, terminal) {
  if (terminal === "iterm") {
    const script = [
      'tell application "iTerm"',
      "activate",
      "create window with default profile",
      `tell current session of current window to write text ${appleScriptString(command)}`,
      "end tell",
    ];
    return spawnSync("osascript", script.flatMap((line) => ["-e", line]), { env: commandEnv() });
  }
  const script = [
    'tell application "Terminal"',
    "activate",
    `do script ${appleScriptString(command)}`,
    "end tell",
  ];
  return spawnSync("osascript", script.flatMap((line) => ["-e", line]), { env: commandEnv() });
}

function openApp(appName, targetPath = REPO_ROOT) {
  return spawnSync("open", ["-a", appName, targetPath], { env: commandEnv() });
}

ipcMain.handle("runtime:status", runtimeStatus);
ipcMain.handle("runtime:install", async () => {
  const result = await installOrUpgradeClawTeam();
  if (result.ok) {
    boardManager.ensure().catch(() => null);
  }
  return result;
});
ipcMain.handle("runtime:upgrade", async () => {
  const result = await installOrUpgradeClawTeam();
  if (result.ok) {
    boardManager.ensure().catch(() => null);
  }
  return result;
});
ipcMain.handle("board:status", () => boardManager.snapshot());
ipcMain.handle("board:ensure", () => boardManager.ensure());
ipcMain.handle("board:restart", async () => {
  boardManager.stop();
  await new Promise((r) => setTimeout(r, 300));
  return boardManager.ensure();
});
ipcMain.handle("profiles:list", () => jsonClawTeam(["profile", "list"]));
ipcMain.handle("profiles:save", (_event, payload) => {
  const name = String(payload?.name || "").trim();
  if (!name) throw new Error("Profile name is required.");
  runClawTeam(profileArgs(name, payload.profile || {}));
  return { ok: true, profiles: jsonClawTeam(["profile", "list"]) };
});
ipcMain.handle("profiles:remove", (_event, payload) => {
  const name = String(payload?.name || "").trim();
  if (!name) throw new Error("Profile name is required.");
  runClawTeam(["profile", "remove", name]);
  return { ok: true, profiles: jsonClawTeam(["profile", "list"]) };
});
ipcMain.handle("profiles:test", (_event, payload) => {
  const name = String(payload?.name || "").trim();
  if (!name) throw new Error("Profile name is required.");
  return { ok: true, result: jsonClawTeam(["profile", "test", name]) };
});
ipcMain.handle("presets:list", () => jsonClawTeam(["preset", "list"]));
ipcMain.handle("presets:generate", (_event, payload) => {
  const presetName = String(payload?.preset || "").trim();
  const client = String(payload?.client || "").trim();
  const name = String(payload?.name || "").trim();
  if (!presetName) throw new Error("Preset name is required.");
  if (!client) throw new Error("Client is required.");
  const args = ["preset", "generate-profile", presetName, client, "--force"];
  if (name) args.push("--name", name);
  const result = jsonClawTeam(args);
  return { ok: true, result, profiles: jsonClawTeam(["profile", "list"]) };
});
ipcMain.handle("sessions:list-launch-targets", launchTargets);
ipcMain.handle("sessions:open", async (_event, payload) => {
  const target = String(payload?.target || "");
  const session = payload?.session || {};
  if (session.alive !== true && (target === "terminal" || target === "iterm" || target === "ghostty")) {
    throw new Error(`Session '${session.agentName || "agent"}' is offline.`);
  }
  if (target === "terminal" || target === "iterm") {
    if (session.backend !== "tmux") {
      throw new Error("Terminal attach is available for tmux sessions.");
    }
    const result = openTerminalCommand(tmuxAttachCommand(payload), target);
    if (result.status !== 0) throw new Error(result.stderr?.toString() || "Failed to open terminal.");
    return { ok: true, message: `Opening ${session.agentName || "agent"} in ${target}.` };
  }
  if (target === "ghostty") {
    if (session.backend !== "tmux") {
      throw new Error("Ghostty attach is available for tmux sessions.");
    }
    if (!appExists("Ghostty")) {
      throw new Error("Ghostty is not installed.");
    }
    const command = tmuxAttachCommand(payload);
    spawnSync("osascript", [
      "-e",
      'tell application "Ghostty" to activate',
      "-e",
      "delay 0.3",
      "-e",
      'tell application "System Events" to keystroke "t" using command down',
      "-e",
      "delay 0.2",
      "-e",
      `tell application "System Events" to keystroke "${command.replace(/"/g, '\\"')}"`,
      "-e",
      'tell application "System Events" to key code 36',
    ], { env: commandEnv() });
    return { ok: true, message: `Opening ${session.agentName || "agent"} in Ghostty.` };
  }
  if (target === "vscode") {
    const code = resolveCommandPath("code");
    if (code) spawn(code, [REPO_ROOT], { detached: true, stdio: "ignore", env: commandEnv() }).unref();
    else openApp("Visual Studio Code", REPO_ROOT);
    return { ok: true, message: "Opening repository in VS Code." };
  }
  if (target === "cursor") {
    const cursor = resolveCommandPath("cursor");
    if (cursor) spawn(cursor, [REPO_ROOT], { detached: true, stdio: "ignore", env: commandEnv() }).unref();
    else openApp("Cursor", REPO_ROOT);
    return { ok: true, message: "Opening repository in Cursor." };
  }
  await shell.openPath(REPO_ROOT);
  return { ok: true, message: "Opening repository folder." };
});
