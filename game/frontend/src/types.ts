export interface PlayerUser {
  id: number;
  first_name: string;
  username: string | null;
  photo_url: string | null;
  lang: "ru" | "en";
  is_premium: boolean;
}

export interface CityInfo {
  id: number;
  name: string;
  country_code: string;
  country_name: string;
  population: number;
  lat: number;
  lng: number;
  sectors_count: number;
}

export interface Country {
  code: string;
  name: string;
}

export interface PlayerState {
  user: PlayerUser;
  onboarded: boolean;
  country_code: string | null;
  country_name: string | null;
  city: CityInfo | null;
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
