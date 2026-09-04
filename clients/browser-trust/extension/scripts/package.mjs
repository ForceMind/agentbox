import { cp, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dist = resolve(root, "dist");
const manifest = JSON.parse(
  await readFile(resolve(root, "manifest.inert.json"), "utf8"),
);
if ("externally_connectable" in manifest) {
  throw new Error("the ordinary software build must remain externally inert");
}
await mkdir(dist, { recursive: true });
await Promise.all([
  writeFile(
    resolve(dist, "manifest.json"),
    `${JSON.stringify(manifest, null, 2)}\n`,
    "utf8",
  ),
  cp(
    resolve(root, "managed_schema.json"),
    resolve(dist, "managed_schema.json"),
  ),
]);
