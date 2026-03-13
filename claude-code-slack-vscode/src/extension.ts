import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";
import * as cp from "child_process";
import * as os from "os";
import { SessionManager } from "./cli/session-manager";
import { ChatWebviewProvider } from "./webview/webview-provider";
import { SlackClient } from "./slack/slack-client";
import { SlackThread } from "./slack/slack-thread";
import type { WebviewToExtensionMessage } from "./types";

const DAEMON_PID_FILE = path.join(os.homedir(), ".claude", "ipc", "slack", "daemon.pid");
const DOCKER_CONTAINER_NAME = "claude-slack-daemon";

/**
 * Load .env file from the extension's parent directory (the slack app root).
 * Checks VSIX layout (daemon/.env) as well as dev-mode parent.
 */
function loadDotEnv(): string | null {
  const candidates = [
    path.resolve(__dirname, "..", "daemon", ".env"),  // VSIX layout
    path.resolve(__dirname, "..", ".env"),
    path.resolve(__dirname, "..", "..", ".env"),
  ];
  for (const folder of vscode.workspace.workspaceFolders ?? []) {
    candidates.push(path.join(folder.uri.fsPath, ".env"));
  }

  for (const envPath of candidates) {
    try {
      if (!fs.existsSync(envPath)) continue;
      const content = fs.readFileSync(envPath, "utf-8");
      for (const line of content.split("\n")) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith("#")) continue;
        const eqIdx = trimmed.indexOf("=");
        if (eqIdx < 0) continue;
        const key = trimmed.slice(0, eqIdx).trim();
        let val = trimmed.slice(eqIdx + 1).trim();
        if (
          (val.startsWith('"') && val.endsWith('"')) ||
          (val.startsWith("'") && val.endsWith("'"))
        ) {
          val = val.slice(1, -1);
        }
        if (!process.env[key]) {
          process.env[key] = val;
        }
      }
      return envPath;
    } catch {
      // Ignore read errors
    }
  }
  return null;
}

/**
 * Load all Slack tokens from VS Code SecretStorage into process.env.
 */
async function loadSecretsIntoEnv(secrets: vscode.SecretStorage): Promise<void> {
  const mapping: Record<string, string> = {
    "claudeSlack.slackBotToken": "SLACK_BOT_TOKEN_XOXB_TIPI",
    "claudeSlack.slackAppToken": "SLACK_APP_LEVEL_TOKEN_XAPP_TIPI",
    "claudeSlack.slackSigningSecret": "SLACK_SIGNING_SECRET_TIPI",
  };
  for (const [secretKey, envKey] of Object.entries(mapping)) {
    const val = await secrets.get(secretKey);
    if (val && !process.env[envKey]) {
      process.env[envKey] = val;
    }
  }
  // Also load userId from VS Code settings into env if not set
  const userId = vscode.workspace
    .getConfiguration("claudeSlack")
    .get<string>("slackUserId", "");
  if (userId && !process.env.SLACK_USER_ID) {
    process.env.SLACK_USER_ID = userId;
  }
}

/**
 * Find the daemon/ directory containing Dockerfile and docker-compose.yml.
 * Checks VSIX layout first, then dev-mode parent.
 */
function findDaemonDir(): string | null {
  const candidates = [
    path.resolve(__dirname, "..", "daemon"),        // VSIX layout: dist/../daemon
    path.resolve(__dirname, "..", "..", "daemon"),   // dev-mode fallback
  ];
  for (const dir of candidates) {
    if (
      fs.existsSync(path.join(dir, "docker-compose.yml")) &&
      fs.existsSync(path.join(dir, "Dockerfile"))
    ) {
      return dir;
    }
  }
  return null;
}

/**
 * Find the daemon.py script path (dev-mode fallback when Docker unavailable).
 */
function findDaemonScript(): string | null {
  const candidates = [
    path.resolve(__dirname, "..", "daemon.py"),
    path.resolve(__dirname, "..", "..", "daemon.py"),
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

/**
 * Resolve the Python interpreter — prefer the project's virtualenv.
 */
function findPython(daemonScript: string): string {
  const projectRoot = path.dirname(daemonScript);
  const venvPython = path.join(projectRoot, ".venv", "bin", "python3");
  if (fs.existsSync(venvPython)) return venvPython;
  const venvPython2 = path.join(projectRoot, "venv", "bin", "python3");
  if (fs.existsSync(venvPython2)) return venvPython2;
  return "python3";
}

/**
 * Check if Docker is available on the system.
 */
function isDockerAvailable(): boolean {
  try {
    cp.execSync("docker info", { stdio: "ignore", timeout: 5000 });
    return true;
  } catch {
    return false;
  }
}

/**
 * Check if the daemon Docker container is running.
 */
function isDockerDaemonRunning(): boolean {
  try {
    const result = cp.execSync(
      `docker ps --filter name=${DOCKER_CONTAINER_NAME} --format '{{.ID}}'`,
      { encoding: "utf-8", timeout: 5000 }
    ).trim();
    return result.length > 0;
  } catch {
    return false;
  }
}

/**
 * Check if the daemon is running (Docker container or local PID).
 */
function isDaemonRunning(): boolean {
  // Check Docker first
  if (isDockerDaemonRunning()) return true;
  // Fall back to PID file check
  try {
    if (!fs.existsSync(DAEMON_PID_FILE)) return false;
    const data = JSON.parse(fs.readFileSync(DAEMON_PID_FILE, "utf-8"));
    const pid = data?.pid;
    if (!pid) return false;
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

/**
 * Start the daemon via Docker Compose, falling back to direct Python spawn.
 */
function ensureDaemonRunning(log: (msg: string) => void): boolean {
  if (isDaemonRunning()) {
    log("Daemon already running");
    return true;
  }

  const ipcDir = path.dirname(DAEMON_PID_FILE);
  fs.mkdirSync(ipcDir, { recursive: true });

  // Try Docker first
  const daemonDir = findDaemonDir();
  if (daemonDir && isDockerAvailable()) {
    log(`Starting daemon via Docker Compose in ${daemonDir}`);

    // Build env args for tokens that exist in process.env
    const tokenKeys = [
      "SLACK_APP_LEVEL_TOKEN_XAPP_TIPI",
      "SLACK_BOT_TOKEN_XOXB_TIPI",
      "SLACK_SIGNING_SECRET_TIPI",
      "SLACK_USER_ID",
    ];
    const envArgs: string[] = [];
    for (const key of tokenKeys) {
      if (process.env[key]) {
        envArgs.push("-e", `${key}=${process.env[key]}`);
      }
    }

    try {
      // Write a temporary .env in daemon dir so docker-compose env_file doesn't fail
      const envFilePath = path.join(daemonDir, ".env");
      if (!fs.existsSync(envFilePath)) {
        const envContent = tokenKeys
          .filter((k) => process.env[k])
          .map((k) => `${k}=${process.env[k]}`)
          .join("\n");
        fs.writeFileSync(envFilePath, envContent + "\n");
      }

      cp.execSync(
        `docker compose -f ${path.join(daemonDir, "docker-compose.yml")} up -d --build`,
        {
          stdio: "pipe",
          timeout: 120000,
          env: { ...process.env },
        }
      );
      log("Docker daemon started");

      // Wait for container to be healthy
      const deadline = Date.now() + 15000;
      while (Date.now() < deadline) {
        if (isDockerDaemonRunning()) {
          log("Docker daemon is ready");
          return true;
        }
        const waitEnd = Date.now() + 500;
        while (Date.now() < waitEnd) { /* spin */ }
      }
      log("Docker daemon may not be ready yet");
      return true; // container started, just not confirmed running yet
    } catch (err) {
      log(`Docker daemon start failed: ${err} — falling back to Python`);
    }
  }

  // Fallback: direct Python spawn (dev mode)
  const daemonScript = findDaemonScript();
  if (!daemonScript) {
    log("Could not find daemon.py or daemon/ directory");
    return false;
  }

  const pythonBin = findPython(daemonScript);
  log(`Starting daemon (Python fallback): ${pythonBin} ${daemonScript}`);

  const logFile = path.join(ipcDir, "daemon.log");
  const logFd = fs.openSync(logFile, "a");

  const child = cp.spawn(pythonBin, [daemonScript], {
    detached: true,
    stdio: ["ignore", logFd, logFd],
    env: { ...process.env },
    cwd: path.dirname(daemonScript),
  });
  child.unref();
  fs.closeSync(logFd);

  log(`Daemon spawned (child PID ${child.pid})`);

  // Wait briefly for daemon to write its PID file
  const deadline = Date.now() + 5000;
  const checkReady = (): boolean => {
    if (isDaemonRunning()) return true;
    if (Date.now() > deadline) return false;
    const waitMs = 200;
    const end = Date.now() + waitMs;
    while (Date.now() < end) { /* spin */ }
    return checkReady();
  };

  const ready = checkReady();
  if (ready) {
    log("Daemon is ready");
  } else {
    log("Daemon may not be ready yet (PID file not found in time)");
  }
  return ready;
}

let sessionManager: SessionManager;
let slackClient: SlackClient | null = null;
let slackThread: SlackThread | null = null;
let webviewProvider: ChatWebviewProvider;
let outputChannel: vscode.OutputChannel;

// Track most recent pending permission for first-response-wins
let lastPendingPermissionId: string | null = null;

export async function activate(context: vscode.ExtensionContext) {
  outputChannel = vscode.window.createOutputChannel("Claude + Slack");
  log("Extension activating...");

  const envFile = loadDotEnv();
  log(envFile ? `Loaded .env from ${envFile}` : "No .env file found");

  // Load secrets from VS Code SecretStorage into process.env
  await loadSecretsIntoEnv(context.secrets);

  // Initialize session manager
  sessionManager = new SessionManager();

  // Initialize webview provider
  webviewProvider = new ChatWebviewProvider(context.extensionUri);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      ChatWebviewProvider.viewType,
      webviewProvider
    )
  );

  // Unified handler for all session manager → webview messages.
  sessionManager.onWebviewMessage((msg) => {
    // Always forward to webview
    webviewProvider.postMessage(msg);

    // Track pending permissions for first-response-wins with Slack
    if (msg.type === "permissionRequest") {
      lastPendingPermissionId = (msg as any).id;
    } else if (msg.type === "permissionResolved") {
      if (lastPendingPermissionId === (msg as any).id) {
        lastPendingPermissionId = null;
      }
    }
  });

  // Wire webview → session manager
  webviewProvider.onDidReceiveMessage((msg: WebviewToExtensionMessage) => {
    handleWebviewMessage(msg);
  });

  // Initialize Slack (if enabled and tokens available)
  await initSlack(context);

  // Register commands
  context.subscriptions.push(
    vscode.commands.registerCommand("claudeSlack.newSession", async () => {
      await startNewSession();
    }),
    vscode.commands.registerCommand("claudeSlack.stopSession", async () => {
      await stopSession();
    }),
    vscode.commands.registerCommand("claudeSlack.focusChat", () => {
      webviewProvider.reveal();
    }),
    vscode.commands.registerCommand("claudeSlack.setTokens", async () => {
      await configureTokens(context);
    })
  );

  // Listen for configuration changes
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration(async (e) => {
      if (e.affectsConfiguration("claudeSlack.slackEnabled")) {
        const enabled = vscode.workspace
          .getConfiguration("claudeSlack")
          .get<boolean>("slackEnabled");
        if (enabled && !slackClient) {
          await initSlack(context);
        } else if (!enabled && slackClient) {
          await teardownSlack();
        }
      }
    })
  );

  log("Extension activated");
}

export function deactivate() {
  sessionManager?.dispose();
  // Clean up session (don't stop daemon — other sessions may need it)
  slackThread?.end().catch(() => {});
  slackClient?.disconnect().catch(() => {});
}

async function handleWebviewMessage(msg: WebviewToExtensionMessage) {
  switch (msg.type) {
    case "sendMessage":
      try {
        await sessionManager.sendMessage(msg.text, "webview");
      } catch (err) {
        log(`Error sending webview message: ${err}`);
      }
      break;
    case "approvePermission":
      sessionManager.resolvePermission(msg.id, true, "webview");
      break;
    case "denyPermission":
      sessionManager.resolvePermission(msg.id, false, "webview");
      break;
    case "stopSession":
      await stopSession();
      break;
    case "newSession":
      await startNewSession();
      break;
    case "setModel":
      await sessionManager.setModel(msg.model);
      break;
    case "ready":
      webviewProvider.postMessage({
        type: "system",
        text: "Claude + Slack ready. Type a message to begin.",
      });
      if (slackClient) {
        webviewProvider.postMessage({
          type: "slackStatus",
          connected: slackClient.connected,
        });
      }
      break;
  }
}

let slackWiringDone = false;

async function initSlack(context: vscode.ExtensionContext) {
  // Prevent double-init
  if (slackClient) return;

  const config = vscode.workspace.getConfiguration("claudeSlack");
  const enabled = config.get<boolean>("slackEnabled", true);
  if (!enabled) return;

  const userId =
    config.get<string>("slackUserId", "") ||
    process.env.SLACK_USER_ID ||
    "";
  const botToken =
    process.env.SLACK_BOT_TOKEN_XOXB_TIPI ||
    (await context.secrets.get("claudeSlack.slackBotToken")) ||
    "";

  log(
    `Slack config: userId=${userId ? userId.slice(0, 3) + "..." : "(empty)"}, botToken=${botToken ? botToken.slice(0, 8) + "..." : "(empty)"}`
  );

  if (!botToken || !userId) {
    log("Slack bot token or user ID not configured.");
    return;
  }

  try {
    // Ensure daemon is running (single Socket Mode connection)
    const daemonReady = ensureDaemonRunning(log);
    if (!daemonReady) {
      log("Warning: daemon may not be running — inbound messages may be delayed");
    }

    slackClient = new SlackClient({ botToken, userId });

    slackClient.on("connected", () => {
      log("Slack connected");
      webviewProvider.postMessage({ type: "slackStatus", connected: true });
    });
    slackClient.on("disconnected", () => {
      log("Slack disconnected");
      webviewProvider.postMessage({ type: "slackStatus", connected: false });
    });
    slackClient.on("error", (err) => {
      log(`Slack error: ${err}`);
    });
    slackClient.on("debug", (msg: string) => {
      log(`[Slack debug] ${msg}`);
    });

    await slackClient.connect();

    // Inject file downloader so SDK can fetch Slack-hosted files
    const sc = slackClient;
    sessionManager.setFileDownloader((url) => sc.downloadFile(url));

    // Wire session manager → Slack thread (only once)
    if (!slackWiringDone) {
      slackWiringDone = true;

      sessionManager.onSlackMessage((text) => {
        if (slackThread) {
          slackThread.post(text);
        }
      });

      sessionManager.onSlackPermission((requestId, toolName, inputStr, toolInput) => {
        if (slackThread) {
          slackThread.postPermissionRequest(requestId, toolName, inputStr, toolInput).catch((err) => {
            log(`Error posting permission to Slack: ${err}`);
          });
        }
      });

      sessionManager.onSlackQuestion((questionId, question, options) => {
        if (slackThread) {
          slackThread.postQuestion(questionId, question, options).catch((err) => {
            log(`Error posting question to Slack: ${err}`);
          });
        }
      });
    }

    // Create initial Slack thread immediately
    await openSlackThread();

    log("Slack initialized successfully");
  } catch (err) {
    log(`Failed to initialize Slack: ${err}`);
    slackClient = null;
  }
}

/**
 * Open a new Slack thread. Called on startup and on "New Session".
 */
async function openSlackThread() {
  if (!slackClient) return;

  // End previous thread if any
  if (slackThread) {
    await slackThread.end();
    slackThread = null;
  }

  const config = vscode.workspace.getConfiguration("claudeSlack");
  const bufferInterval = config.get<number>("slackBufferIntervalMs", 1500);
  const cwd =
    vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? process.cwd();

  slackThread = new SlackThread(slackClient, { bufferInterval });

  slackThread.on("debug", (msg: string) => {
    log(`[Thread debug] ${msg}`);
  });

  try {
    const ts = await slackThread.start(cwd);
    if (ts) log(`Slack thread started: ${ts}`);
  } catch (err) {
    log(`Failed to start Slack thread: ${err}`);
  }

  // Slack replies → send to Claude (fire-and-forget, don't block the event)
  // Note: sendMessage() already echoes to webview, so no extra postMessage here.
  slackThread.on("userReply", (text: string, files?: import("./slack/slack-client").SlackFileMetadata[]) => {
    const fileInfo = files?.length ? ` (+${files.length} file(s))` : "";
    log(`Slack reply received: ${text}${fileInfo}`);
    sessionManager.sendMessage(text, "slack", files).then(() => {
      log("Slack message processed by Claude");
      slackThread?.ackMessages().catch(() => {});
    }).catch((err) => {
      log(`Error processing Slack message: ${err}`);
      webviewProvider.postMessage({
        type: "system",
        text: `Error: ${err instanceof Error ? err.message : String(err)}`,
      });
    });
  });

  // Permission responses from Slack (first-response-wins)
  slackThread.on(
    "permissionResponse",
    ({ approved }: { approved: boolean }) => {
      if (lastPendingPermissionId) {
        log(
          `Slack permission response for ${lastPendingPermissionId}: ${approved ? "approved" : "denied"}`
        );
        sessionManager.resolvePermission(
          lastPendingPermissionId,
          approved,
          "slack"
        );
        lastPendingPermissionId = null;
      }
    }
  );

  // Question responses from Slack (text replies → resolve AskUserQuestion)
  slackThread.on(
    "questionResponse",
    ({ questionId, answer }: { questionId: string; answer: string }) => {
      log(`Slack question response for ${questionId}: "${answer}"`);
      sessionManager.resolveQuestion(questionId, answer);
    }
  );
}

async function startNewSession() {
  await sessionManager.newSession();
  // Open a fresh Slack thread for the new session
  await openSlackThread();
}

async function stopSession() {
  if (slackThread) {
    await slackThread.flush();
    await slackThread.end();
    slackThread = null;
  }
  await sessionManager.stopSession();
}

async function teardownSlack() {
  if (slackThread) {
    await slackThread.end();
    slackThread = null;
  }
  if (slackClient) {
    await slackClient.disconnect();
    slackClient = null;
  }
  slackWiringDone = false;
  webviewProvider.postMessage({ type: "slackStatus", connected: false });
}

async function configureTokens(context: vscode.ExtensionContext) {
  const steps: Array<{
    key: string;
    title: string;
    prompt: string;
    placeholder: string;
    password: boolean;
    settingsKey?: string;
  }> = [
    {
      key: "claudeSlack.slackBotToken",
      title: "Slack Bot Token (1/4)",
      prompt: "Enter your Slack bot token (xoxb-...)",
      placeholder: "xoxb-...",
      password: true,
    },
    {
      key: "claudeSlack.slackAppToken",
      title: "Slack App-Level Token (2/4)",
      prompt: "Enter your Slack app-level token for Socket Mode (xapp-...)",
      placeholder: "xapp-...",
      password: true,
    },
    {
      key: "claudeSlack.slackSigningSecret",
      title: "Slack Signing Secret (3/4)",
      prompt: "Enter your Slack signing secret",
      placeholder: "abc123...",
      password: true,
    },
    {
      key: "slackUserId",
      title: "Slack User ID (4/4)",
      prompt: "Enter your Slack user ID (e.g. UEQ6BFG9E)",
      placeholder: "U...",
      password: false,
      settingsKey: "claudeSlack.slackUserId",
    },
  ];

  for (const step of steps) {
    const value = await vscode.window.showInputBox({
      title: step.title,
      prompt: step.prompt,
      password: step.password,
      placeHolder: step.placeholder,
    });
    if (value === undefined) return; // user cancelled
    if (!value) continue; // empty = skip (keep existing)

    if (step.settingsKey) {
      // Store in VS Code settings (non-secret)
      await vscode.workspace
        .getConfiguration()
        .update(step.settingsKey, value, vscode.ConfigurationTarget.Global);
    } else {
      // Store in VS Code SecretStorage
      await context.secrets.store(step.key, value);
    }
  }

  const reload = await vscode.window.showInformationMessage(
    "Slack tokens saved. Reload window to apply?",
    "Reload"
  );
  if (reload === "Reload") {
    await vscode.commands.executeCommand("workbench.action.reloadWindow");
  }
}

function log(message: string) {
  const ts = new Date().toISOString();
  outputChannel.appendLine(`[${ts}] ${message}`);
}
