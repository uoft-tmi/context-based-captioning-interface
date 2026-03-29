import {
  createSession,
  uploadNotes,
  startSession,
  sendChunk,
  stopSession,
  getSession,
  downloadTranscript,
} from "./api";

jest.mock("./supabase", () => ({
  supabase: {
    auth: {
      getSession: jest.fn(),
    },
  },
}));

import { supabase } from "./supabase";

const mockedGetSession = supabase.auth.getSession as jest.Mock;

describe("api.ts", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    global.fetch = jest.fn();
    mockedGetSession.mockResolvedValue({
      data: {
        session: {
          access_token: "fake-token",
        },
      },
    });
  });

  test("createSession sends POST with mode baseline", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      json: async () => ({ id: "123", mode: "baseline" }),
    });

    await createSession("baseline");

    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/sessions",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          Authorization: "Bearer fake-token",
        }),
        body: JSON.stringify({ mode: "baseline" }),
      })
    );
  });

  test("startSession sends POST to correct endpoint", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      json: async () => ({ ok: true }),
    });

    await startSession("session-1");

    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/sessions/session-1/start",
      expect.objectContaining({
        method: "POST",
      })
    );
  });

  test("sendChunk sends correct transformed payload", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ partial_text: "hello world" }),
    });

    const result = await sendChunk("session-1", {
      chunkIndex: 3,
      audioB64: "abc123",
      mime: "audio/webm",
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/sessions/session-1/chunks",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          chunk_index: 3,
          audio_b64: "abc123",
          mime: "audio/webm",
        }),
      })
    );

    expect(result).toEqual({ partial_text: "hello world" });
  });

  test("sendChunk throws backend detail on failure", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: "Bad chunk" }),
    });

    await expect(
      sendChunk("session-1", {
        chunkIndex: 1,
        audioB64: "bad",
        mime: "audio/webm",
      })
    ).rejects.toThrow("Bad chunk");
  });

  test("getSession sends GET request", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      json: async () => ({ id: "session-1" }),
    });

    await getSession("session-1");

    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/sessions/session-1",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer fake-token",
        }),
      })
    );
  });

  test("downloadTranscript sends GET request", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      json: async () => ({ transcript: "done" }),
    });

    await downloadTranscript("session-1");

    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/sessions/session-1/download",
      expect.any(Object)
    );
  });

  test("uploadNotes uses FormData and auth header", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      json: async () => ({ ok: true }),
    });

    const file = new File(["pdf content"], "notes.pdf", {
      type: "application/pdf",
    });

    await uploadNotes("session-1", file);

    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/sessions/session-1/notes",
      expect.objectContaining({
        method: "POST",
        headers: {
          Authorization: "Bearer fake-token",
        },
        body: expect.any(FormData),
      })
    );
  });

  test("omits Authorization header when logged out", async () => {
    mockedGetSession.mockResolvedValue({
      data: { session: null },
    });

    (global.fetch as jest.Mock).mockResolvedValue({
      json: async () => ({ id: "123" }),
    });

    await createSession("context");

    const [, options] = (global.fetch as jest.Mock).mock.calls[0];
    expect(options.headers.Authorization).toBeUndefined();
  });
});