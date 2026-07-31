// Minimal ambient types for @novnc/novnc (the package ships no .d.ts).
declare module '@novnc/novnc' {
  interface RFBOptions {
    shared?: boolean;
    credentials?: { username?: string; password?: string; target?: string };
    repeaterID?: string;
    wsProtocols?: string[];
  }
  export default class RFB extends EventTarget {
    constructor(target: HTMLElement, url: string, options?: RFBOptions);
    scaleViewport: boolean;
    clipViewport: boolean;
    viewOnly: boolean;
    disconnect(): void;
  }
}
