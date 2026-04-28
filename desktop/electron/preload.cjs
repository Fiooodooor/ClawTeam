const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("clawteamDesktop", {
  getRuntimeStatus: () => ipcRenderer.invoke("runtime:status"),
  installClawTeam: () => ipcRenderer.invoke("runtime:install"),
  upgradeClawTeam: () => ipcRenderer.invoke("runtime:upgrade"),
  listProfiles: () => ipcRenderer.invoke("profiles:list"),
  saveProfile: (name, profile) => ipcRenderer.invoke("profiles:save", { name, profile }),
  removeProfile: (name) => ipcRenderer.invoke("profiles:remove", { name }),
  testProfile: (name) => ipcRenderer.invoke("profiles:test", { name }),
  listPresets: () => ipcRenderer.invoke("presets:list"),
  generateProfileFromPreset: (payload) => ipcRenderer.invoke("presets:generate", payload),
  listLaunchTargets: () => ipcRenderer.invoke("sessions:list-launch-targets"),
  openSession: (payload) => ipcRenderer.invoke("sessions:open", payload),
  getBoardStatus: () => ipcRenderer.invoke("board:status"),
  ensureBoard: () => ipcRenderer.invoke("board:ensure"),
  restartBoard: () => ipcRenderer.invoke("board:restart"),
});
