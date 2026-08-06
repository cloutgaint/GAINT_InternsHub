const crypto = require("crypto");
const path = require("path");
const { exec } = require("child_process");
const vscode = require("vscode");

const TOKEN_PREFIX = "gaint.workspace.";
const EXCLUDED = new Set([
  "node_modules", ".venv", "venv", ".git", "__pycache__", ".pytest_cache",
  "dist", "build", ".next", "target", ".idea",
]);
const PACKAGE_EXCLUDED = new Set([...EXCLUDED, "gaint_checkpoints", "gaint-extension", ".vscode"]);
const EVIDENCE_EXTENSIONS = new Set([
  ".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".java",
  ".html", ".css", ".scss", ".json", ".sql", ".md", ".xml", ".yml", ".yaml",
]);

function languageFor(document) {
  return ({ python: "python", javascript: "javascript", javascriptreact: "javascript", java: "java" })[document.languageId];
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body.detail || `GAINT request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return body;
}

async function manifestExists(folder) {
  try {
    await vscode.workspace.fs.stat(vscode.Uri.joinPath(folder, "gaint-project.json"));
    return true;
  } catch {
    return false;
  }
}

async function findProjectRoot(activeUri) {
  if (activeUri?.scheme === "file") {
    let current = vscode.Uri.file(path.dirname(activeUri.fsPath));
    while (true) {
      if (await manifestExists(current)) return current;
      const parent = vscode.Uri.file(path.dirname(current.fsPath));
      if (parent.fsPath === current.fsPath) break;
      current = parent;
    }
  }
  const manifests = await vscode.workspace.findFiles(
    "**/gaint-project.json",
    "**/{node_modules,.venv,venv,dist,build,.next,__pycache__,.pytest_cache,.git,target}/**",
    20,
  );
  if (manifests.length === 1) return vscode.Uri.file(path.dirname(manifests[0].fsPath));
  if (manifests.length > 1) throw new Error("Open only one GAINT project in this VS Code window.");
  throw new Error("Open the extracted GAINT project folder in VS Code first.");
}

async function readManifest(root) {
  const raw = await vscode.workspace.fs.readFile(vscode.Uri.joinPath(root, "gaint-project.json"));
  return JSON.parse(Buffer.from(raw).toString("utf8"));
}

async function ensureConnection(context, root) {
  const manifest = await readManifest(root);
  const apiUrl = String(manifest.api_url || "http://localhost:8000/api").replace(/\/$/, "");
  const key = `${TOKEN_PREFIX}${manifest.assignment_id}`;
  let token = await context.secrets.get(key);
  if (!token) {
    if (!manifest.workspace_bootstrap) {
      throw new Error("Automatic connection information is missing. Download a fresh project from the Student Dashboard.");
    }
    const result = await requestJson(`${apiUrl}/vscode/bootstrap`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-GAINT-Client": "vscode-extension" },
      body: JSON.stringify({ token: manifest.workspace_bootstrap }),
    });
    token = result.token;
    await context.secrets.store(key, token);
    vscode.window.showInformationMessage("GAINT connected automatically for this project.");
  }
  return {
    manifest,
    apiUrl,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      "X-GAINT-Client": "vscode-extension",
    },
  };
}

async function loadAssignment(context, root) {
  let connection = await ensureConnection(context, root);
  try {
    const assignment = await requestJson(
      `${connection.apiUrl}/vscode/assignment`,
      { headers: connection.headers },
    );
    return { connection, assignment };
  } catch (error) {
    if (error.status !== 401) throw error;
    const key = `${TOKEN_PREFIX}${connection.manifest.assignment_id}`;
    await context.secrets.delete(key);
    connection = await ensureConnection(context, root);
    const assignment = await requestJson(
      `${connection.apiUrl}/vscode/assignment`,
      { headers: connection.headers },
    );
    vscode.window.showInformationMessage("GAINT repaired the project connection automatically.");
    return { connection, assignment };
  }
}

function currentTaskFrom(assignment) {
  return assignment.tasks.find((task) => task.unlocked && task.status !== "PASSED");
}

async function writeCurrentTask(root, task) {
  const sample = task.judge0_sample
    ? `\n## Visible example\n\nInput:\n\`\`\`\n${task.judge0_sample.stdin}\`\`\`\nExpected:\n\`\`\`\n${task.judge0_sample.expected_output}\`\`\`\n`
    : "";
  const text = [
    `# Task ${task.order_no}: ${task.title}`,
    "",
    task.description,
    "",
    "## Project milestone",
    ...(task.deliverables || []).map((item) => `- ${item}`),
    "",
    "## Checkpoint question",
    task.challenge_prompt,
    sample,
    "Save the required checkpoint file, then run **GAINT: Submit Current Task**.",
  ].join("\n");
  await vscode.workspace.fs.writeFile(vscode.Uri.joinPath(root, "CURRENT_TASK.md"), Buffer.from(text));
}

async function openCurrentTask(context) {
  const root = await findProjectRoot(vscode.window.activeTextEditor?.document.uri);
  const { assignment } = await loadAssignment(context, root);
  const task = currentTaskFrom(assignment);
  if (!task) {
    if (assignment.all_tasks_passed) {
      vscode.window.showInformationMessage("All tasks passed. Your certificate and completed project package are ready.");
      return;
    }
    throw new Error("No current task is available.");
  }
  await writeCurrentTask(root, task);
  const document = await vscode.workspace.openTextDocument(
    vscode.Uri.joinPath(root, ...task.checkpoint_file.split("/")),
  );
  await vscode.window.showTextDocument(document);
}

function ignored(relative, packageMode = false) {
  const parts = relative.replaceAll("\\", "/").split("/");
  const loweredParts = parts.map((part) => part.toLowerCase());
  if (loweredParts.some((part) => (packageMode ? PACKAGE_EXCLUDED : EXCLUDED).has(part))) return true;
  const base = parts.at(-1);
  const loweredBase = base.toLowerCase();
  return Boolean(packageMode && (
    base === "gaint-project.json" ||
    base === "CURRENT_TASK.md" ||
    base === "TASKS.md" ||
    base === "OPEN_IN_VSCODE.bat" ||
    base === "STUDENT_PROJECT_GUIDE.md" ||
    (base.startsWith("GAINT-Interns-Hub-") && base.endsWith(".vsix")) ||
    (loweredBase.startsWith(".env") && loweredBase !== ".env.example") ||
    ["id_rsa", "id_ed25519", "credentials.json", "service-account.json"].includes(loweredBase) ||
    [".pem", ".key", ".p12", ".pfx"].some((suffix) => loweredBase.endsWith(suffix))
  ));
}

async function projectFiles(root, packageMode = false) {
  const files = await vscode.workspace.findFiles(new vscode.RelativePattern(root, "**/*"), undefined, 10000);
  return files
    .map((uri) => ({ uri, relative: path.relative(root.fsPath, uri.fsPath).replaceAll("\\", "/") }))
    .filter((item) => !ignored(item.relative, packageMode))
    .sort((left, right) => left.relative.localeCompare(right.relative));
}

async function evidenceBundle(root, requiredPaths) {
  const entries = await projectFiles(root, false);
  const required = (requiredPaths || []).map((item) => item.replaceAll("\\", "/").replace(/\/$/, ""));
  const selected = entries.filter(({ relative }) =>
    EVIDENCE_EXTENSIONS.has(path.extname(relative).toLowerCase()) &&
    required.some((item) => relative === item || relative.startsWith(`${item}/`)),
  );
  if (selected.length > 180) throw new Error("Required project evidence has more than 180 source files.");
  const hashes = {};
  const contents = {};
  let totalBytes = 0;
  for (const item of selected) {
    const data = Buffer.from(await vscode.workspace.fs.readFile(item.uri));
    if (data.length > 256 * 1024) throw new Error(`Required source file is too large: ${item.relative}`);
    totalBytes += data.length;
    if (totalBytes > 3 * 1024 * 1024) throw new Error("Required project source is larger than 3 MB.");
    if (data.includes(0)) throw new Error(`Required source file is not plain text: ${item.relative}`);
    hashes[item.relative] = crypto.createHash("sha256").update(data).digest("hex");
    contents[item.relative] = data.toString("utf8");
  }
  return { hashes, contents };
}

function runCommand(command, cwd) {
  return new Promise((resolve) => {
    exec(command, { cwd, timeout: 120000, windowsHide: true }, (error, stdout, stderr) => {
      resolve({
        command,
        passed: !error,
        exit_code: error && Number.isInteger(error.code) ? error.code : 0,
        output: `${stdout || ""}${stderr || ""}`.slice(-4000),
      });
    });
  });
}

async function runLocalChecks(root, commands, progress) {
  const results = [];
  for (const command of commands || []) {
    progress.report({ message: `Local check: ${command}` });
    const result = await runCommand(command, root.fsPath);
    results.push(result);
    if (!result.passed) {
      const choice = await vscode.window.showErrorMessage(`Local check failed: ${command}`, "Show Output");
      if (choice === "Show Output") {
        const channel = vscode.window.createOutputChannel("GAINT Interns Hub");
        channel.appendLine(result.output || "No command output.");
        channel.show();
      }
      break;
    }
  }
  return results;
}

function makeCrcTable() {
  const table = [];
  for (let number = 0; number < 256; number += 1) {
    let value = number;
    for (let bit = 0; bit < 8; bit += 1) value = (value & 1) ? (0xEDB88320 ^ (value >>> 1)) : (value >>> 1);
    table[number] = value >>> 0;
  }
  return table;
}
const CRC_TABLE = makeCrcTable();

function crc32(data) {
  let crc = 0xFFFFFFFF;
  for (const byte of data) crc = CRC_TABLE[(crc ^ byte) & 0xFF] ^ (crc >>> 8);
  return (crc ^ 0xFFFFFFFF) >>> 0;
}

function zipStore(entries) {
  const localParts = [];
  const centralParts = [];
  let offset = 0;
  for (const entry of entries) {
    const name = Buffer.from(entry.name.replaceAll("\\", "/"), "utf8");
    const data = Buffer.from(entry.data);
    const crc = crc32(data);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0x0800, 6);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(name.length, 26);
    localParts.push(local, name, data);

    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt16LE(0x0800, 8);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(data.length, 20);
    central.writeUInt32LE(data.length, 24);
    central.writeUInt16LE(name.length, 28);
    central.writeUInt32LE(offset, 42);
    centralParts.push(central, name);
    offset += local.length + name.length + data.length;
  }
  const directory = Buffer.concat(centralParts);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(entries.length, 8);
  end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(directory.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...localParts, directory, end]);
}

async function packageCompletedProject(root, connection, assignment, progress = { report() {} }) {
  if (!assignment.all_tasks_passed) throw new Error("Every task must pass before the completed project can be packaged.");
  progress.report({ message: "Running final whole-project checks…" });
  const localCheckResults = await runLocalChecks(root, assignment.final_local_checks || [], progress);
  if (localCheckResults.some((item) => !item.passed)) {
    throw new Error("The final project checks did not pass. Correct the project and submit again.");
  }
  const evidence = await evidenceBundle(root, assignment.final_required_paths || []);
  const files = await projectFiles(root, true);
  if (!files.length) throw new Error("No project source files were found for packaging.");
  const folderName = path.basename(root.fsPath).replace(/[^A-Za-z0-9_-]+/g, "_");
  const entries = [];
  for (const item of files) {
    entries.push({ name: `${folderName}/${item.relative}`, data: await vscode.workspace.fs.readFile(item.uri) });
  }
  const zip = zipStore(entries);
  const hash = crypto.createHash("sha256").update(zip).digest("hex");
  const filename = `GAINT_${connection.manifest.student_id}_${folderName}_Completed.zip`;
  const destination = vscode.Uri.file(path.join(path.dirname(root.fsPath), filename));
  await requestJson(`${connection.apiUrl}/vscode/final-package`, {
    method: "POST",
    headers: connection.headers,
    body: JSON.stringify({
      fingerprint: hash,
      filename,
      required_file_hashes: evidence.hashes,
      project_file_contents: evidence.contents,
      local_check_results: localCheckResults,
    }),
  });
  await vscode.workspace.fs.writeFile(destination, zip);
  const action = await vscode.window.showInformationMessage(
    `Completed project ZIP created: ${filename}. Your verified certificate is enabled in the Student Dashboard.`,
    "Show ZIP",
  );
  if (action === "Show ZIP") await vscode.commands.executeCommand("revealFileInOS", destination);
}

async function evaluate(context) {
  const root = await findProjectRoot(vscode.window.activeTextEditor?.document.uri);
  const { connection, assignment } = await loadAssignment(context, root);
  const currentTask = currentTaskFrom(assignment);
  if (!currentTask) {
    if (assignment.all_tasks_passed) return packageCompletedProject(root, connection, assignment);
    throw new Error("No unlocked task is available.");
  }
  await writeCurrentTask(root, currentTask);
  const requiredUri = vscode.Uri.joinPath(root, ...currentTask.checkpoint_file.split("/"));
  let document;
  try {
    document = await vscode.workspace.openTextDocument(requiredUri);
  } catch {
    throw new Error(`Required checkpoint file is missing: ${currentTask.checkpoint_file}`);
  }
  if (vscode.window.activeTextEditor?.document.uri.fsPath !== requiredUri.fsPath) {
    await vscode.window.showTextDocument(document);
    vscode.window.showInformationMessage(`Task ${currentTask.order_no} opened. Write the code, save it, then submit again.`);
    return;
  }
  const language = languageFor(document);
  if (!language) throw new Error("The checkpoint must be Python, JavaScript or Java.");
  await document.save();

  await vscode.window.withProgress({
    location: vscode.ProgressLocation.Notification,
    title: `GAINT Task ${currentTask.order_no}`,
    cancellable: false,
  }, async (progress) => {
    const localCheckResults = await runLocalChecks(root, currentTask.local_checks, progress);
    if (localCheckResults.some((item) => !item.passed)) return;
    progress.report({ message: "Checking project files…" });
    const evidence = await evidenceBundle(root, currentTask.required_paths);
    progress.report({ message: "Running visible and hidden Judge0 checks…" });
    let result = await requestJson(`${connection.apiUrl}/vscode/tasks/${currentTask.id}/evaluate`, {
      method: "POST",
      headers: connection.headers,
      body: JSON.stringify({
        language,
        source_code: document.getText(),
        file_name: currentTask.checkpoint_file,
        explanation: "Submitted from the required local project checkpoint.",
        required_file_hashes: evidence.hashes,
        project_file_contents: evidence.contents,
        local_check_results: localCheckResults,
      }),
    });
    for (let attempt = 0; attempt < 30 && ["QUEUED", "PROCESSING"].includes(result.status); attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1200));
      result = await requestJson(`${connection.apiUrl}/vscode/evaluations/${result.id}`, { headers: connection.headers });
    }
    if (result.status !== "PASSED") {
      vscode.window.showErrorMessage(
        `Task ${currentTask.order_no} failed (${result.passed_cases}/${result.total_cases} checks). Correct it and submit again.`,
      );
      return;
    }
    const refreshed = await requestJson(`${connection.apiUrl}/vscode/assignment`, { headers: connection.headers });
    if (refreshed.all_tasks_passed) {
      progress.report({ message: "Creating your clean runnable project ZIP…" });
      await packageCompletedProject(root, connection, refreshed, progress);
    } else {
      const next = currentTaskFrom(refreshed);
      if (next) await writeCurrentTask(root, next);
      vscode.window.showInformationMessage(
        `Task ${currentTask.order_no} passed all ${result.total_cases} checks. Task ${next?.order_no || "next"} is now enabled.`,
      );
    }
  });
}

async function activateWorkspace(context) {
  try {
    const root = await findProjectRoot();
    await ensureConnection(context, root);
  } catch {
    // Non-GAINT workspaces remain unaffected.
  }
}

async function repairConnection(context) {
  const root = await findProjectRoot(vscode.window.activeTextEditor?.document.uri);
  const manifest = await readManifest(root);
  await context.secrets.delete(`${TOKEN_PREFIX}${manifest.assignment_id}`);
  await loadAssignment(context, root);
  vscode.window.showInformationMessage("GAINT connection is ready.");
}

function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand("gaint.openCurrentTask", () =>
      openCurrentTask(context).catch((error) => vscode.window.showErrorMessage(error.message))),
    vscode.commands.registerCommand("gaint.submitCurrentTask", () =>
      evaluate(context).catch((error) => vscode.window.showErrorMessage(error.message))),
    vscode.commands.registerCommand("gaint.packageCompletedProject", async () => {
      try {
        const root = await findProjectRoot(vscode.window.activeTextEditor?.document.uri);
        const { connection, assignment } = await loadAssignment(context, root);
        await packageCompletedProject(root, connection, assignment);
      } catch (error) {
        vscode.window.showErrorMessage(error.message);
      }
    }),
    vscode.commands.registerCommand("gaint.repairConnection", () =>
      repairConnection(context).catch((error) => vscode.window.showErrorMessage(error.message))),
  );
  activateWorkspace(context);
}

function deactivate() {}

module.exports = { activate, deactivate };
