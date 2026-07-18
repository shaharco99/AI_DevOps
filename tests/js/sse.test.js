/**
 * Tests for the incremental SSE frame parser.
 *
 * The behaviour that matters is chunk-boundary handling: network reads do not
 * align with frame boundaries, so a frame can arrive split in half and several
 * frames can arrive together.
 */

import assert from "node:assert/strict";
import { test, describe } from "node:test";

import { SseParser } from "../../ai_devops_assistant/static/js/sse.js";

describe("SseParser", () => {
  test("parses a single complete frame", () => {
    const parser = new SseParser();
    const frames = parser.push('event: token\ndata: {"t":"hi"}\n\n');
    assert.deepEqual(frames, [{ event: "token", data: { t: "hi" } }]);
  });

  test("parses several frames from one chunk", () => {
    const parser = new SseParser();
    const frames = parser.push(
      'event: token\ndata: {"t":"a"}\n\nevent: token\ndata: {"t":"b"}\n\n',
    );
    assert.equal(frames.length, 2);
    assert.equal(frames[1].data.t, "b");
  });

  test("buffers a frame split across chunks", () => {
    const parser = new SseParser();
    assert.deepEqual(parser.push("event: tok"), [], "incomplete frame yields nothing");
    assert.deepEqual(parser.push('en\ndata: {"t":"split"}'), [], "still incomplete");
    const frames = parser.push("\n\n");
    assert.deepEqual(frames, [{ event: "token", data: { t: "split" } }]);
  });

  test("handles a split in the middle of the json payload", () => {
    const parser = new SseParser();
    parser.push('event: done\ndata: {"mess');
    const frames = parser.push('age":"hello"}\n\n');
    assert.equal(frames[0].data.message, "hello");
  });

  test("reassembles tokens in order across ragged chunks", () => {
    const parser = new SseParser();
    const raw =
      'event: token\ndata: {"t":"Three "}\n\n' +
      'event: token\ndata: {"t":"pods "}\n\n' +
      'event: token\ndata: {"t":"failed"}\n\n';

    // Feed it in deliberately awkward 7-character slices.
    const collected = [];
    for (let i = 0; i < raw.length; i += 7) {
      for (const frame of parser.push(raw.slice(i, i + 7))) collected.push(frame);
    }
    assert.equal(collected.map((f) => f.data.t).join(""), "Three pods failed");
  });

  test("ignores keepalive comments", () => {
    const parser = new SseParser();
    const frames = parser.push(': keepalive\n\nevent: token\ndata: {"t":"x"}\n\n');
    assert.equal(frames.length, 1);
    assert.equal(frames[0].data.t, "x");
  });

  test("defaults the event name when none is given", () => {
    const parser = new SseParser();
    const frames = parser.push('data: {"t":"x"}\n\n');
    assert.equal(frames[0].event, "message");
  });

  test("a frame with no data line is skipped", () => {
    const parser = new SseParser();
    assert.deepEqual(parser.push("event: ping\n\n"), []);
  });

  test("unparseable json is surfaced as raw text, not thrown", () => {
    // One malformed frame must not kill the whole stream.
    const parser = new SseParser();
    const frames = parser.push("event: token\ndata: {not json}\n\n");
    assert.equal(frames.length, 1);
    assert.equal(frames[0].data.raw, "{not json}");
  });

  test("keeps parsing after a malformed frame", () => {
    const parser = new SseParser();
    const frames = parser.push(
      'event: token\ndata: {bad}\n\nevent: token\ndata: {"t":"good"}\n\n',
    );
    assert.equal(frames.length, 2);
    assert.equal(frames[1].data.t, "good");
  });

  test("joins multi-line data fields", () => {
    const parser = new SseParser();
    const frames = parser.push('event: done\ndata: {"a":1,\ndata: "b":2}\n\n');
    assert.deepEqual(frames[0].data, { a: 1, b: 2 });
  });

  test("an empty chunk yields nothing and does not corrupt the buffer", () => {
    const parser = new SseParser();
    parser.push('event: token\ndata: {"t":"x"}');
    assert.deepEqual(parser.push(""), []);
    assert.equal(parser.push("\n\n")[0].data.t, "x");
  });
});
