import {
  canonicalExternalDocument,
  EXTERNAL_PORT_NAME,
  NATIVE_HOST_NAME,
  validPageRequest,
  validProviderResponse,
} from "./protocol.js";

const POLICY_KEYS = [
  "provider_installation_key_fingerprint",
  "allowed_origins",
] as const;

function nonce(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  let binary = "";
  for (const value of bytes) binary += String.fromCharCode(value);
  return btoa(binary)
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replace(/=+$/, "");
}

function disconnect(port: AgentBoxChromePort): void {
  try {
    port.disconnect();
  } catch {
    // A dead peer is already closed.
  }
}

chrome.runtime.onConnectExternal.addListener((page) => {
  const sender = page.sender;
  const document = sender && canonicalExternalDocument(sender);
  if (page.name !== EXTERNAL_PORT_NAME || !document) {
    disconnect(page);
    return;
  }

  let native: AgentBoxChromePort | null = null;
  let closed = false;
  let pendingOpen: import("./protocol.js").PageRequest | null = null;
  let expectedPageSequence = 1n;
  let expectedProviderSequence = 1n;
  const close = () => {
    if (closed) return;
    closed = true;
    if (native) disconnect(native);
    disconnect(page);
  };

  void chrome.storage.managed
    .get(POLICY_KEYS)
    .then((policy) => {
      if (closed) return;
      const fingerprint = policy.provider_installation_key_fingerprint;
      const origins = policy.allowed_origins;
      if (
        typeof fingerprint !== "string" ||
        !/^[0-9a-f]{64}$/.test(fingerprint) ||
        !Array.isArray(origins) ||
        origins.length < 1 ||
        origins.length > 32 ||
        !origins.every((origin) => typeof origin === "string") ||
        !origins.includes(document.origin)
      ) {
        close();
        return;
      }
      native = chrome.runtime.connectNative(NATIVE_HOST_NAME);
      native.onDisconnect.addListener(close);
      native.onMessage.addListener((message) => {
        if (!validProviderResponse(message)) {
          close();
          return;
        }
        const sequence = BigInt((message as { sequence: string }).sequence);
        if (sequence !== expectedProviderSequence) {
          close();
          return;
        }
        expectedProviderSequence += 1n;
        page.postMessage(message);
      });
      native.postMessage({
        type: "BROKER_OPEN",
        protocol_version: 1,
        origin: document.origin,
        document_id: document.documentId,
        native_nonce: nonce(),
        provider_installation_key_fingerprint: fingerprint,
      });
      if (pendingOpen) {
        native.postMessage(pendingOpen);
        pendingOpen = null;
      }
    })
    .catch(close);

  page.onDisconnect.addListener(close);
  page.onMessage.addListener((message) => {
    if (closed || !validPageRequest(message)) {
      close();
      return;
    }
    const sequence = BigInt(message.sequence);
    if (sequence !== expectedPageSequence) {
      close();
      return;
    }
    expectedPageSequence += 1n;
    if (!native) {
      if (message.type !== "OPEN" || pendingOpen !== null) {
        close();
        return;
      }
      pendingOpen = message;
      return;
    }
    native.postMessage(message);
    if (message.type === "CLOSE") close();
  });
});
