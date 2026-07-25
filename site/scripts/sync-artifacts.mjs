import { copyFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const siteRoot = resolve(here, "..");
const source = resolve(siteRoot, "..", "artifacts", "site-data.json");
const destination = resolve(siteRoot, "src", "generated", "site-data.json");

await mkdir(dirname(destination), { recursive: true });
try {
  await copyFile(source, destination);
} catch (error) {
  if (error && error.code === "ENOENT") {
    throw new Error(`Verified site data is missing at ${source}. Run paperkit build first.`);
  }
  throw error;
}

console.log(`Synced verified site data to ${destination}`);
