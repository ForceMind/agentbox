import { afterEach, describe, expect, it, vi } from "vitest";

class Event<T extends (...args: never[]) => void> {
  readonly listeners: T[] = [];

  addListener(listener: T): void {
    this.listeners.push(listener);
  }
}

class Port {
  readonly onMessage = new Event<(message: unknown) => void>();
  readonly onDisconnect = new Event<() => void>();
  readonly sent: unknown[] = [];
  disconnected = false;

  constructor(
    readonly name: string,
    readonly sender?: AgentBoxChromeMessageSender,
  ) {}

  postMessage(message: unknown): void {
    this.sent.push(message);
  }

  disconnect(): void {
    this.disconnected = true;
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe("MV3 trust bridge initialization", () => {
  it("holds exactly one validated OPEN until managed policy and native port are ready", async () => {
    let resolvePolicy!: (value: Record<string, unknown>) => void;
    const policy = new Promise<Record<string, unknown>>((resolve) => {
      resolvePolicy = resolve;
    });
    const external = new Event<(port: AgentBoxChromePort) => void>();
    const native = new Port("native");
    vi.stubGlobal("chrome", {
      runtime: {
        onConnectExternal: external,
        connectNative: vi.fn(() => native),
      },
      storage: { managed: { get: vi.fn(() => policy) } },
    });
    await import("./serviceWorker");
    const page = new Port("agentbox-waw-trust-v1", {
      origin: "https://example.agentbox.test:8443",
      url: "https://example.agentbox.test:8443/workspace",
      frameId: 0,
      documentId: "12345678-abcd-4321-abcd-123456789abc",
      tab: { incognito: false },
    });
    external.listeners[0]?.(page);
    page.onMessage.listeners[0]?.({
      type: "OPEN",
      protocol_version: 1,
      page_nonce: "a".repeat(43),
      sequence: "1",
      correlation_id: `req_${"b".repeat(32)}`,
    });
    expect(page.disconnected).toBe(false);
    expect(native.sent).toEqual([]);
    resolvePolicy({
      provider_installation_key_fingerprint: "c".repeat(64),
      allowed_origins: ["https://example.agentbox.test:8443"],
    });
    await vi.waitFor(() => expect(native.sent).toHaveLength(2));
    expect(native.sent[0]).toMatchObject({
      type: "BROKER_OPEN",
      origin: "https://example.agentbox.test:8443",
      native_nonce: expect.stringMatching(/^[A-Za-z0-9_-]{43}$/),
    });
    expect(native.sent[1]).toMatchObject({ type: "OPEN", sequence: "1" });
  });
});
