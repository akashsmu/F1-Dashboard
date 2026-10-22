/**
 * Fetches /session-info once on load and stores it in sessionStorage
 * so every panel can read it without re-fetching.
 *
 * Include this script in index.html BEFORE stream.js.
 * Panels access the data via:
 *   const info = JSON.parse(sessionStorage.getItem("f1SessionInfo") || "{}");
 */

(async function loadSessionInfo() {
  try {
    const res = await fetch("/session-info");
    if (!res.ok) throw new Error(res.statusText);
    const data = await res.json();
    sessionStorage.setItem("f1SessionInfo", JSON.stringify(data));
    window.dispatchEvent(new CustomEvent("f1SessionInfoReady", { detail: data }));
    console.log("[session] Session info loaded:", Object.keys(data));
  } catch (err) {
    console.warn("[session] Could not load session info:", err.message);
    sessionStorage.setItem("f1SessionInfo", "{}");
    window.dispatchEvent(new CustomEvent("f1SessionInfoReady", { detail: {} }));
  }
})();
