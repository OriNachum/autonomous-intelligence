/**
 * Build-time script: copies daemon.py, lib/, and requirements.txt
 * from the parent project into the daemon/ directory so they are
 * bundled into the VSIX package.
 */

const fs = require("fs");
const path = require("path");

const EXT_ROOT = path.resolve(__dirname, "..");
const PARENT_ROOT = path.resolve(EXT_ROOT, "..");
const DAEMON_DIR = path.join(EXT_ROOT, "daemon");

function copyFile(src, dest) {
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(src, dest);
  console.log(`  ${path.relative(EXT_ROOT, dest)}`);
}

function copyDir(src, dest) {
  if (!fs.existsSync(src)) {
    console.warn(`  WARN: source dir not found: ${src}`);
    return;
  }
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src)) {
    if (entry === "__pycache__") continue;
    const srcPath = path.join(src, entry);
    const destPath = path.join(dest, entry);
    if (fs.statSync(srcPath).isDirectory()) {
      copyDir(srcPath, destPath);
    } else {
      copyFile(srcPath, destPath);
    }
  }
}

console.log("Copying daemon files into daemon/...");

// Copy daemon.py
copyFile(
  path.join(PARENT_ROOT, "daemon.py"),
  path.join(DAEMON_DIR, "daemon.py")
);

// Copy requirements.txt
copyFile(
  path.join(PARENT_ROOT, "requirements.txt"),
  path.join(DAEMON_DIR, "requirements.txt")
);

// Copy lib/ directory
copyDir(
  path.join(PARENT_ROOT, "lib"),
  path.join(DAEMON_DIR, "lib")
);

console.log("Done.");
