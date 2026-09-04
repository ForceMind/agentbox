import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { manifestVersionForPackage, packagedManifest } from "./version.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");

describe("MV3 package version", () => {
  it("derives the packaged rc5 manifest version from package metadata", async () => {
    const packageMetadata = JSON.parse(
      await readFile(resolve(root, "package.json"), "utf8"),
    );
    const inertManifest = JSON.parse(
      await readFile(resolve(root, "manifest.inert.json"), "utf8"),
    );

    expect(packageMetadata.version).toBe("0.3.0-rc.5");
    expect(manifestVersionForPackage(packageMetadata.version)).toBe("0.3.0.5");
    expect(
      packagedManifest(inertManifest, packageMetadata.version).version,
    ).toBe("0.3.0.5");
  });

  it("rejects package and manifest versions that cannot produce the fixed MV3 identity", () => {
    expect(() => manifestVersionForPackage("0.3.0")).toThrow("must use");
    expect(() =>
      packagedManifest({ version: "0.3.0.4" }, "0.3.0-rc.5"),
    ).toThrow("does not match");
  });
});
