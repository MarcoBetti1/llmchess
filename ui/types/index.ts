export type PlayerRef = {
  type: "llm" | "human";
  model: string;
};

export type MoveRef = {
  from: string;
  to: string;
  san: string;
};

export type GameSummary = {
  game_id: string;
  experiment_id?: string | null;
  status: "queued" | "running" | "finished";
  players: {
    white: PlayerRef;
    black: PlayerRef;
  };
  current_fen: string;
  last_move?: MoveRef | null;
  move_number: number;
  winner?: "white" | "black" | "draw" | null;
  termination_reason?: "checkmate" | "illegal" | "timeout" | "draw" | null;
  illegal_moves?: {
    white: number;
    black: number;
  };
};

export type MoveHistoryEntry = {
  ply: number;
  turn: "white" | "black";
  player_model: string;
  fen_before: string;
  uci: string;
  san: string;
  is_legal: boolean;
  illegal_attempts_before: number;
  llm_latency_s: number;
  timestamp: string;
  conversation_id?: string;
};

export type GameHistory = {
  game_id: string;
  initial_fen: string;
  moves: MoveHistoryEntry[];
};

export type ConversationTurn = {
  turn_ply: number;
  side: "white" | "black";
  model: string;
  messages: { role: "system" | "user" | "assistant"; content: string }[];
  parsed_move?: { uci: string; san: string };
};

export type ConversationLog = {
  game_id: string;
  conversation: ConversationTurn[];
};

export type ExperimentSummary = {
  experiment_id: string;
  name?: string;
  status: "queued" | "running" | "finished";
  players: {
    a: { model: string };
    b: { model: string };
  };
  games: {
    total: number;
    completed: number;
  };
  wins?: {
    player_a: number;
    player_b: number;
    draws: number;
  };
};

export type ExperimentResults = {
  experiment_id: string;
  wins: { player_a: number; player_b: number; draws: number };
  total_games: number;
  avg_game_length_plies: number;
  illegal_move_stats: {
    player_a_avg: number;
    player_b_avg: number;
  };
  games: {
    game_id: string;
    white_model: string;
    black_model: string;
    winner: "white" | "black" | "draw" | null;
    illegal_moves: number;
  }[];
};

export type HumanGameState = {
  human_game_id: string;
  fen: string;
  side_to_move: "white" | "black";
  status: "running" | "finished";
  winner: "human" | "ai" | "draw" | null;
  ai_illegal_move_count: number;
};

export type HumanGameCreateRequest = {
  model: string;
  prompt: {
    mode: "plaintext" | "fen" | "fen+plaintext";
    instruction_template_id?: string;
  };
  illegal_move_limit: number;
  human_plays: "white" | "black";
};

export type HumanGameCreateResponse = {
  human_game_id: string;
  initial_fen: string;
  side_to_move: "white" | "black";
};

export type HumanMoveRequest = {
  human_move: string;
};

export type HumanMoveResponse = {
  status: "ok" | "finished";
  fen_after_human: string;
  ai_move: { uci: string; san: string } | null;
  fen_after_ai?: string;
  ai_reply_raw?: string;
  ai_illegal_move_count: number;
  game_status: "running" | "finished";
  winner: "human" | "ai" | "draw" | null;
  termination_reason: string | null;
};
