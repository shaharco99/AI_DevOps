/**
 * SSE client for a POST endpoint.
 *
 * The browser's native EventSource is GET-only, and /chat/stream is POST on
 * purpose (prompts are long, and a GET would put every user message into access
 * logs). So the body is read with fetch + ReadableStream and the SSE framing is
 * parsed here.
 *
 * The frame parser is split out and pure so it can be tested under `node --test`
 * without a network or a browser.
 */

/**
 * Incremental SSE frame parser.
 *
 * Network chunks do not align with frame boundaries: a frame can arrive split
 * across two reads, and several frames can arrive in one. Feed each chunk in and
 * take whatever complete frames come out; partial trailing data is buffered
 * until the rest of it arrives.
 */
export class SseParser {
  constructor() {
    this.buffer = "";
    this.pendingCr = "";
  }

  /**
   * Feed a chunk of text, return the frames completed by it.
   * @returns {Array<{event: string, data: any}>}
   */
  push(chunk) {
    // The spec allows CRLF, LF or a lone CR as the line terminator, and
    // sse-starlette (what /chat/stream uses) sends CRLF. Normalising to LF on
    // the way in means the framing below only has to handle one form.
    let text = this.pendingCr + chunk;
    this.pendingCr = "";
    // A chunk can end mid-CRLF. Hold the CR back rather than treating it as a
    // line end, or the LF that follows would look like a second, empty line and
    // split one frame into two.
    if (text.endsWith("\r")) {
      this.pendingCr = "\r";
      text = text.slice(0, -1);
    }
    this.buffer += text.replace(/\r\n|\r/g, "\n");
    const frames = [];

    // Frames are separated by a blank line. Split on \n\n, keeping the last
    // (possibly incomplete) piece in the buffer.
    const parts = this.buffer.split("\n\n");
    this.buffer = parts.pop() ?? "";

    for (const part of parts) {
      const frame = this.#parseFrame(part);
      if (frame) frames.push(frame);
    }
    return frames;
  }

  #parseFrame(raw) {
    let event = "message";
    const dataLines = [];

    for (const line of raw.split("\n")) {
      if (line.startsWith(":")) continue; // keepalive comment
      if (line.startsWith("event:")) {
        event = line.slice("event:".length).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice("data:".length).trimStart());
      }
    }

    if (dataLines.length === 0) return null;

    const payload = dataLines.join("\n");
    try {
      return { event, data: JSON.parse(payload) };
    } catch {
      // A frame we cannot parse must not kill the stream; surface it as raw text.
      return { event, data: { raw: payload } };
    }
  }
}

/**
 * POST to an SSE endpoint and invoke onEvent for each frame.
 *
 * @param {string} url
 * @param {object} body - JSON request body
 * @param {(frame: {event: string, data: any}) => void} onEvent
 * @param {object} options
 * @param {AbortSignal} [options.signal] - abort to stop generation
 * @param {string} [options.csrfToken] - echoed in X-CSRF-Token
 */
export async function streamPost(url, body, onEvent, { signal, csrfToken } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;

  const response = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    // Send the session cookie. Without this the request is anonymous and 401s.
    credentials: "same-origin",
    signal,
  });

  if (!response.ok) {
    // The status is carried on the error, not just formatted into its message,
    // so callers can tell "log in again" (401/403) from a real failure without
    // parsing prose.
    const error = new Error(`stream failed: ${response.status}`);
    error.status = response.status;
    throw error;
  }
  if (!response.body) {
    throw new Error("stream failed: response has no body");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser();

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      // stream: true so a multi-byte character split across chunks is not
      // decoded into replacement characters.
      for (const frame of parser.push(decoder.decode(value, { stream: true }))) {
        onEvent(frame);
      }
    }
  } finally {
    // Aborting mid-stream leaves the reader open otherwise, which keeps the
    // connection alive and the server generating.
    reader.releaseLock();
  }
}
