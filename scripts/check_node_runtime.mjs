// Node is copied from the official image, so OS package scanners cannot see it.
// This guard covers the two advisories that prompted the runtime change; the
// release process must still review newer Node security releases separately.
const versions = process.versions;

function atLeast(actual, minimum) {
  const parts = actual?.split(".").map(Number);
  if (!parts || parts.length < minimum.length || parts.some(
    (part) => !Number.isInteger(part) || part < 0,
  )) return false;
  for (const [index, part] of minimum.entries()) {
    if (parts[index] > part) return true;
    if (parts[index] < part) return false;
  }
  return true;
}

if (!versions.node?.startsWith("24.") || !atLeast(versions.node, [24, 17, 0])) {
  throw new Error(`Expected patched Node 24 LTS, found ${versions.node}`);
}
if (!atLeast(versions.undici, [7, 29, 0])) {
  throw new Error(`Expected patched Undici 7.29.0+, found ${versions.undici}`);
}
console.log(`Node ${versions.node}; Undici ${versions.undici}; OpenSSL ${versions.openssl}`);
