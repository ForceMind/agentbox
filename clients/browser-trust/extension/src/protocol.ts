export const TRUST_PROTOCOL_VERSION = 1 as const;
export const EXTERNAL_PORT_NAME = "agentbox-waw-trust-v1" as const;
export const NATIVE_HOST_NAME = "com.forcemind.agentbox.waw_trust" as const;
export const REQUEST_BYTES_MAX = 4096;
export const RESPONSE_BYTES_MAX = 512 * 1024;

export type PageRequestType =
  "OPEN" | "SNAPSHOT_GET" | "CONFIRM_CURRENT" | "PING" | "CLOSE";

export type ProviderResponseType =
  "OPENED" | "SNAPSHOT" | "CONFIRMED" | "INVALIDATE" | "PONG" | "CLOSE";

export interface PageRequest {
  readonly type: PageRequestType;
  readonly protocol_version: 1;
  readonly page_nonce: string;
  readonly sequence: string;
  readonly correlation_id: string;
}

const REQUEST_TYPES = new Set<PageRequestType>([
  "OPEN",
  "SNAPSHOT_GET",
  "CONFIRM_CURRENT",
  "PING",
  "CLOSE",
]);
const RESPONSE_TYPES = new Set<ProviderResponseType>([
  "OPENED",
  "SNAPSHOT",
  "CONFIRMED",
  "INVALIDATE",
  "PONG",
  "CLOSE",
]);
const DECIMAL_U64 = /^(?:0|[1-9][0-9]{0,19})$/;
const ID = /^[a-z]+_[0-9a-f]{32}$/;
const NONCE = /^[A-Za-z0-9_-]{43}$/;

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function encodedSize(value: unknown): number {
  try {
    return new TextEncoder().encode(JSON.stringify(value)).byteLength;
  } catch {
    return Number.POSITIVE_INFINITY;
  }
}

export function validPageRequest(value: unknown): value is PageRequest {
  const item = record(value);
  if (!item || encodedSize(item) > REQUEST_BYTES_MAX) return false;
  if (
    Object.keys(item).some(
      (key) =>
        ![
          "type",
          "protocol_version",
          "page_nonce",
          "sequence",
          "correlation_id",
        ].includes(key),
    ) ||
    Object.keys(item).length !== 5
  ) {
    return false;
  }
  return (
    typeof item.type === "string" &&
    REQUEST_TYPES.has(item.type as PageRequestType) &&
    item.protocol_version === TRUST_PROTOCOL_VERSION &&
    typeof item.page_nonce === "string" &&
    NONCE.test(item.page_nonce) &&
    typeof item.sequence === "string" &&
    DECIMAL_U64.test(item.sequence) &&
    BigInt(item.sequence) <= 0xffffffffffffffffn &&
    typeof item.correlation_id === "string" &&
    ID.test(item.correlation_id)
  );
}

export function validProviderResponse(value: unknown): boolean {
  const item = record(value);
  if (!item || encodedSize(item) > RESPONSE_BYTES_MAX) return false;
  return (
    item.protocol_version === TRUST_PROTOCOL_VERSION &&
    typeof item.type === "string" &&
    RESPONSE_TYPES.has(item.type as ProviderResponseType) &&
    typeof item.page_nonce === "string" &&
    NONCE.test(item.page_nonce) &&
    typeof item.sequence === "string" &&
    DECIMAL_U64.test(item.sequence) &&
    BigInt(item.sequence) <= 0xffffffffffffffffn
  );
}

export function canonicalExternalDocument(
  sender: AgentBoxChromeMessageSender,
): {
  readonly origin: string;
  readonly documentId: string;
} | null {
  if (
    sender.frameId !== 0 ||
    sender.tab?.incognito !== false ||
    typeof sender.origin !== "string" ||
    typeof sender.url !== "string" ||
    typeof sender.documentId !== "string" ||
    !/^[0-9a-f-]{16,128}$/i.test(sender.documentId)
  ) {
    return null;
  }
  try {
    const url = new URL(sender.url);
    if (
      url.origin !== sender.origin ||
      url.protocol !== "https:" ||
      (url.pathname !== "/workspace" &&
        !/^\/workspace\/aws_[0-9a-f]{32}$/.test(url.pathname)) ||
      url.username ||
      url.password ||
      url.hash
    ) {
      return null;
    }
    return Object.freeze({ origin: url.origin, documentId: sender.documentId });
  } catch {
    return null;
  }
}
