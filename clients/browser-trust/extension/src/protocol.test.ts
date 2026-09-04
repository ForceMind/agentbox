import { describe, expect, it } from "vitest";

import {
  canonicalExternalDocument,
  REQUEST_BYTES_MAX,
  validPageRequest,
  validProviderResponse,
} from "./protocol";

const request = (overrides: Record<string, unknown> = {}) => ({
  type: "OPEN",
  protocol_version: 1,
  page_nonce: "a".repeat(43),
  sequence: "1",
  correlation_id: `req_${"b".repeat(32)}`,
  ...overrides,
});

describe("managed trust bridge protocol", () => {
  it("accepts only the closed page request and uint64 sequence", () => {
    expect(validPageRequest(request())).toBe(true);
    for (const bad of [
      request({ extra: true }),
      request({ sequence: "01" }),
      request({ sequence: "18446744073709551616" }),
      request({ page_nonce: "a".repeat(42) }),
      request({ correlation_id: `req_${"Z".repeat(32)}` }),
    ]) {
      expect(validPageRequest(bad)).toBe(false);
    }
    expect(
      validPageRequest(
        request({ correlation_id: "x".repeat(REQUEST_BYTES_MAX) }),
      ),
    ).toBe(false);
  });

  it("binds a top-level exact workspace URL to its browser origin", () => {
    const sender = {
      origin: "https://agentbox.example:8443",
      url: `https://agentbox.example:8443/workspace/aws_${"1".repeat(32)}`,
      frameId: 0,
      documentId: "12345678-abcd-4321-abcd-123456789abc",
      tab: { incognito: false },
    };
    expect(canonicalExternalDocument(sender)).toEqual({
      origin: sender.origin,
      documentId: sender.documentId,
    });
    for (const bad of [
      { ...sender, frameId: 1 },
      { ...sender, origin: "https://other.example:8443" },
      { ...sender, url: "https://agentbox.example:8443/projects" },
      { ...sender, url: "http://agentbox.example:8443/workspace" },
      { ...sender, tab: { incognito: true } },
      { ...sender, tab: undefined },
    ]) {
      expect(canonicalExternalDocument(bad)).toBeNull();
    }
  });

  it("bounds and validates provider responses before page publication", () => {
    expect(
      validProviderResponse({
        type: "OPENED",
        protocol_version: 1,
        page_nonce: "a".repeat(43),
        sequence: "1",
      }),
    ).toBe(true);
    expect(
      validProviderResponse({
        type: "UNKNOWN",
        protocol_version: 1,
        page_nonce: "a".repeat(43),
        sequence: "1",
      }),
    ).toBe(false);
  });
});
