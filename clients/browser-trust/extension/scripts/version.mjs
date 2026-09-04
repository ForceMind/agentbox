const MAX_MANIFEST_VERSION_COMPONENT = 65535;
const RC_VERSION =
  /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)-rc\.(0|[1-9]\d*)$/;

export function manifestVersionForPackage(packageVersion) {
  const match = RC_VERSION.exec(packageVersion);
  if (match === null) {
    throw new Error(
      `extension package version must use MAJOR.MINOR.PATCH-rc.CANDIDATE: ${packageVersion}`,
    );
  }

  const components = match.slice(1).map(Number);
  if (
    components.some((component) => component > MAX_MANIFEST_VERSION_COMPONENT)
  ) {
    throw new Error(
      `extension package version exceeds the MV3 component limit: ${packageVersion}`,
    );
  }
  return components.join(".");
}

export function packagedManifest(inertManifest, packageVersion) {
  const expectedVersion = manifestVersionForPackage(packageVersion);
  if (inertManifest.version !== expectedVersion) {
    throw new Error(
      `inert manifest version ${inertManifest.version} does not match package version ${packageVersion}`,
    );
  }
  return { ...inertManifest, version: expectedVersion };
}
