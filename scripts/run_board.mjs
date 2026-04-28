#!/usr/bin/env node
import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const REPO_ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");

function findClawTeam() {
  const candidates = [
    path.join(REPO_ROOT, ".venv", "bin", "clawteam"),
    path.join(os.homedir(), ".clawteam", ".venv", "bin", "clawteam"),
    path.join(os.homedir(), ".local", "bin", "clawteam"),
  ];
  for (const p of candidates) if (fs.existsSync(p)) return p;
  const which = spawnSync("/bin/sh", ["-lc", "command -v clawteam"], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  });
  if (which.status === 0) return String(which.stdout).trim().split(/\r?\n/).pop();
  return "";
}

const team = process.env.CLAWTEAM_TEAM || "demo";
const port = process.env.CLAWTEAM_BOARD_PORT || "8080";
const cmd = findClawTeam();

if (!cmd) {
  console.error("clawteam command not found. Install it (uv pip install -e . / pip install clawteam) or activate the project venv.");
  process.exit(1);
}

console.log(`[board] using ${cmd}`);
console.log(`[board] team=${team} port=${port}`);

const child = spawn(cmd, ["board", "serve", team, "--host", "127.0.0.1", "--port", port], {
  stdio: "inherit",
  env: process.env,
});

const stop = () => child.kill("SIGTERM");
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
child.on("exit", (code) => process.exit(code || 0));
