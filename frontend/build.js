const fs = require("node:fs");
const path = require("node:path");

const sourceDir = __dirname;
const outputDir = path.join(sourceDir, "dist");
const apiBaseUrl = process.env.RENDER_API_BASE_URL;

if (!apiBaseUrl) {
  throw new Error("Set RENDER_API_BASE_URL to the Render service origin.");
}

let apiUrl;
try {
  apiUrl = new URL(apiBaseUrl);
} catch {
  throw new Error("RENDER_API_BASE_URL must be a valid absolute URL.");
}

const localHost = ["localhost", "127.0.0.1", "::1"].includes(apiUrl.hostname);
if (
  !["https:", ...(localHost ? ["http:"] : [])].includes(apiUrl.protocol)
  || apiUrl.username
  || apiUrl.password
  || (apiUrl.pathname !== "/" && apiUrl.pathname !== "")
  || apiUrl.search
  || apiUrl.hash
) {
  throw new Error(
    "RENDER_API_BASE_URL must be a service origin (HTTPS, except localhost)."
  );
}

fs.rmSync(outputDir, { recursive: true, force: true });
fs.mkdirSync(outputDir, { recursive: true });
for (const filename of ["index.html", "app.js", "styles.css", "agriweather-icon.svg"]) {
  fs.copyFileSync(path.join(sourceDir, filename), path.join(outputDir, filename));
}

const normalizedApiUrl = apiUrl.origin.replace(/\/$/, "");
fs.writeFileSync(
  path.join(outputDir, "config.js"),
  `window.SWA_CONFIG = Object.freeze({ apiBaseUrl: ${JSON.stringify(normalizedApiUrl)} });\n`
);
