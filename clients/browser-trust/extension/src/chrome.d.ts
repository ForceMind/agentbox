interface AgentBoxChromeMessageSender {
  readonly origin?: string;
  readonly url?: string;
  readonly frameId?: number;
  readonly documentId?: string;
  readonly tab?: { readonly incognito?: boolean };
}

interface AgentBoxChromePort {
  readonly name: string;
  readonly sender?: AgentBoxChromeMessageSender;
  readonly onMessage: {
    addListener(listener: (message: unknown) => void): void;
  };
  readonly onDisconnect: { addListener(listener: () => void): void };
  postMessage(message: unknown): void;
  disconnect(): void;
}

interface AgentBoxChromeRuntime {
  readonly onConnectExternal: {
    addListener(listener: (port: AgentBoxChromePort) => void): void;
  };
  connectNative(application: string): AgentBoxChromePort;
}

interface AgentBoxChromeStorageArea {
  get(keys: readonly string[]): Promise<Record<string, unknown>>;
}

declare const chrome: {
  readonly runtime: AgentBoxChromeRuntime;
  readonly storage: { readonly managed: AgentBoxChromeStorageArea };
};
