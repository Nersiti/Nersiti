export interface PlayerUser {
  id: number;
  first_name: string;
  username: string | null;
  photo_url: string | null;
  lang: "ru" | "en";
  is_premium: boolean;
}

export interface PlayerState {
  user: PlayerUser;
  coins: number;
  server_time: string;
}

export interface GameConfig {
  game_name: string;
  bot_username: string;
}

export interface SessionResponse {
  created: boolean;
  state: PlayerState;
  config: GameConfig;
}
