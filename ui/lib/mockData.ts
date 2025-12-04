import { ConversationLog, GameHistory, GameSummary, ExperimentSummary, ExperimentResults } from "@/types";

export const mockGames: GameSummary[] = [
  {
    game_id: "game_0001",
    experiment_id: "exp_alpha",
    status: "running",
    players: {
      white: { type: "llm", model: "openai/gpt-4o" },
      black: { type: "llm", model: "anthropic/claude-4.5" }
    },
    current_fen: "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
    last_move: { from: "e7", to: "e5", san: "e5" },
    move_number: 2,
    winner: null,
    termination_reason: null,
    illegal_moves: { white: 0, black: 0 }
  },
  {
    game_id: "game_0002",
    experiment_id: "exp_beta",
    status: "finished",
    players: {
      white: { type: "llm", model: "meta/llama-3.1-70b" },
      black: { type: "llm", model: "openai/gpt-4o-mini" }
    },
    current_fen: "6k1/5ppp/8/8/8/8/5PPP/6K1 w - - 0 45",
    last_move: { from: "e7", to: "e8", san: "e8=Q+" },
    move_number: 45,
    winner: "white",
    termination_reason: "checkmate",
    illegal_moves: { white: 0, black: 1 }
  },
  {
    game_id: "game_0003",
    experiment_id: null,
    status: "queued",
    players: {
      white: { type: "llm", model: "mistral-large" },
      black: { type: "llm", model: "openai/gpt-4o" }
    },
    current_fen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    last_move: null,
    move_number: 0,
    winner: null,
    termination_reason: null,
    illegal_moves: { white: 0, black: 0 }
  }
];

export const mockConversation: ConversationLog = {
  game_id: "game_0001",
  conversation: [
    {
      turn_ply: 1,
      side: "white",
      model: "openai/gpt-4o",
      messages: [
        { role: "system", content: "You are a strong chess player." },
        { role: "user", content: "Side to move: white\nMove history:\nNone\nProvide only your best legal move in SAN." },
        { role: "assistant", content: "I will start with e4" }
      ],
      parsed_move: { uci: "e2e4", san: "e4" }
    },
    {
      turn_ply: 2,
      side: "black",
      model: "anthropic/claude-4.5",
      messages: [
        { role: "system", content: "You are a strong chess player." },
        { role: "user", content: "Side to move: black\nMove history:\nWhite Pawn e4\nProvide only your best legal move in SAN." },
        { role: "assistant", content: "e5" }
      ],
      parsed_move: { uci: "e7e5", san: "e5" }
    }
  ]
};

export const mockHistory: GameHistory = {
  game_id: "game_0001",
  initial_fen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  moves: [
    {
      ply: 1,
      turn: "white",
      player_model: "openai/gpt-4o",
      fen_before: "startpos",
      uci: "e2e4",
      san: "e4",
      is_legal: true,
      illegal_attempts_before: 0,
      llm_latency_s: 1.04,
      timestamp: new Date().toISOString(),
      conversation_id: "conv_0001_turn_001"
    },
    {
      ply: 2,
      turn: "black",
      player_model: "anthropic/claude-4.5",
      fen_before: "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
      uci: "e7e5",
      san: "e5",
      is_legal: true,
      illegal_attempts_before: 0,
      llm_latency_s: 0.82,
      timestamp: new Date().toISOString(),
      conversation_id: "conv_0001_turn_002"
    },
    {
      ply: 3,
      turn: "white",
      player_model: "openai/gpt-4o",
      fen_before: "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
      uci: "g1f3",
      san: "Nf3",
      is_legal: true,
      illegal_attempts_before: 0,
      llm_latency_s: 0.9,
      timestamp: new Date().toISOString(),
      conversation_id: "conv_0001_turn_003"
    },
    {
      event: "termination",
      result: "1-0",
      reason: "checkmate"
    }
  ]
};

export const mockExperiments: ExperimentSummary[] = [
  {
    experiment_id: "exp_alpha",
    name: "gpt4o_vs_claude45_20",
    log_dir_name: "exp_alpha",
    status: "running",
    players: { a: { model: "openai/gpt-4o" }, b: { model: "anthropic/claude-4.5" } },
    games: { total: 20, completed: 8 },
    wins: { player_a: 5, player_b: 2, draws: 1 }
  },
  {
    experiment_id: "exp_beta",
    name: "llama_vs_gpt4omini",
    log_dir_name: "exp_beta",
    status: "finished",
    players: { a: { model: "meta/llama-3.1-70b" }, b: { model: "openai/gpt-4o-mini" } },
    games: { total: 12, completed: 12 },
    wins: { player_a: 7, player_b: 4, draws: 1 }
  }
];

export const mockExperimentResults: ExperimentResults = {
  experiment_id: "exp_beta",
  name: "llama_vs_gpt4omini",
  log_dir_name: "exp_beta",
  wins: { player_a: 7, player_b: 4, draws: 1 },
  total_games: 12,
  avg_game_length_plies: 62,
  illegal_move_stats: { player_a_avg: 0.3, player_b_avg: 0.6 },
  games: [
    {
      game_id: "game_0002",
      white_model: "meta/llama-3.1-70b",
      black_model: "openai/gpt-4o-mini",
      winner: "white",
      illegal_moves: 1
    }
  ]
};
