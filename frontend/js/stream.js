/**
 * Shared WebSocket fan-out.
 * Opens ONE connection to the F1 replay server and fans each frame out
 * to all other panels via BroadcastChannel("f1frames").
 *
 * Include this script ONLY in index.html — panels subscribe via BroadcastChannel.
 */

const WS_URL = `ws://${location.hostname}:8765/ws`;
const bc = new BroadcastChannel("f1frames");

let ws;
let reconnectDelay = 1500;

function connect() {
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    console.log("[stream] Connected to F1 replay server");
    reconnectDelay = 1500;
    bc.postMessage({ _meta: "connected" });
  };

  ws.onmessage = (e) => {
    try {
      const frame = JSON.parse(e.data);
      bc.postMessage(frame);
    } catch (_) {}
  };

  ws.onclose = () => {
    console.warn("[stream] Disconnected — retrying in", reconnectDelay, "ms");
    bc.postMessage({ _meta: "disconnected" });
    setTimeout(connect, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 1.5, 10000);
  };

  ws.onerror = () => ws.close();
}

connect();
