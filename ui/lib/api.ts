import { mockConversation, mockExperimentResults, mockExperiments, mockGames, mockHistory } from "@/lib/mockData";
import {
  ConversationLog,
  ExperimentCreateRequest,
  ExperimentCreateResponse,
  ExperimentResults,
  ExperimentSummary,
  GameHistory,
  GameSummary,
  HumanGameCreateRequest,
  HumanGameCreateResponse,
  HumanMoveRequest,
  HumanMoveResponse
} from "@/types";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE || "").replace(/\/$/, "");
const USE_MOCKS = (process.env.NEXT_PUBLIC_USE_MOCKS || "false").toLowerCase() === "true";

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T | null> {
  if (typeof fetch === "undefined") return null;
  try {
    const res = await fetch(`${API_BASE}${path}`, { cache: "no-store", ...(init || {}) });
    if (!res.ok) throw new Error(`Request failed ${res.status}`);
    return (await res.json()) as T;
  } catch (err) {
    if (USE_MOCKS) {
      console.warn("Falling back to mock data for", path, err);
      return null;
    }
    throw err;
  }
}

export async function fetchLiveGames(): Promise<GameSummary[]> {
  try {
    const data = await fetchJson<GameSummary[]>("/api/games/live");
    if (data && Array.isArray(data)) return data;
  } catch (err) {
    console.error("Failed to fetch live games", err);
    if (!USE_MOCKS) return [];
  }
  return mockGames;
}

export async function fetchGameConversation(gameId: string): Promise<ConversationLog> {
  try {
    const data = await fetchJson<ConversationLog>(`/api/games/${gameId}/conversation`);
    if (data) return data;
  } catch (err) {
    console.error("Failed to fetch conversation", err);
    if (!USE_MOCKS) throw err;
  }
  return mockConversation;
}

export async function fetchGameHistory(gameId: string): Promise<GameHistory> {
  try {
    const data = await fetchJson<GameHistory>(`/api/games/${gameId}/history?t=${Date.now()}`);
    if (data) return data;
  } catch (err) {
    console.error("Failed to fetch history", err);
    if (!USE_MOCKS) throw err;
  }
  return mockHistory;
}

export async function fetchExperiments(): Promise<ExperimentSummary[]> {
  try {
    const data = await fetchJson<ExperimentSummary[]>(`/api/experiments?t=${Date.now()}`);
    if (data && Array.isArray(data)) return data;
  } catch (err) {
    console.error("Failed to fetch experiments", err);
    if (!USE_MOCKS) return [];
  }
  return mockExperiments;
}

export async function fetchExperimentResults(experimentId: string): Promise<ExperimentResults> {
  try {
    const data = await fetchJson<ExperimentResults>(`/api/experiments/${experimentId}/results?t=${Date.now()}`);
    if (data) return data;
  } catch (err) {
    console.error("Failed to fetch experiment results", err);
    if (!USE_MOCKS) throw err;
  }
  if (experimentId === mockExperimentResults.experiment_id) return mockExperimentResults;
  return { ...mockExperimentResults, experiment_id: experimentId };
}

type GameUpdateHandler = (summary: Partial<GameSummary> & { game_id: string }) => void;

export function subscribeToGameStream(onUpdate: GameUpdateHandler): () => void {
  if (typeof window === "undefined" || typeof EventSource === "undefined") return () => undefined;
  const url = `${API_BASE || ""}/api/stream/games`;
  const source = new EventSource(url);
  source.onmessage = (ev) => {
    try {
      const payload = JSON.parse(ev.data);
      if (payload?.game_id) {
        onUpdate(payload);
      }
    } catch (err) {
      console.error("Failed to parse game stream event", err);
    }
  };
  source.onerror = () => {
    source.close();
  };
  return () => source.close();
}

export async function createExperiment(payload: ExperimentCreateRequest): Promise<ExperimentCreateResponse> {
  const res = await fetchJson<ExperimentCreateResponse>("/api/experiments", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (res) return res;
  if (USE_MOCKS) {
    return { experiment_id: `exp_${Date.now()}` };
  }
  throw new Error("Failed to create experiment");
}

export async function createHumanGame(req: HumanGameCreateRequest): Promise<HumanGameCreateResponse> {
  const res = await fetchJson<HumanGameCreateResponse>("/api/human-games", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req)
  });
  if (!res) {
    throw new Error("Failed to create human game");
  }
  return res;
}

export async function postHumanMove(id: string, req: HumanMoveRequest): Promise<HumanMoveResponse> {
  const res = await fetchJson<HumanMoveResponse>(`/api/human-games/${id}/move`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req)
  });
  if (!res) throw new Error("Failed to submit human move");
  return res;
}
