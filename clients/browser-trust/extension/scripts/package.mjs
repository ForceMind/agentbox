import { cp, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { packagedManifest } from "./version.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dist = resolve(root, "dist");
const inertManifest = JSON.parse(
  await readFile(resolve(root, "manifest.inert.json"), "utf8"),
);
const packageMetadata = JSON.parse(
  await readFile(resolve(root, "package.json"), "utf8"),
);
const manifest = packagedManifest(inertManifest, packageMetadata.version);
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
