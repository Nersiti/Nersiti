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

export interface DailyInfo {
  streak: number;
  claimed_today: boolean;
  next_day: number;
  next_reward: number;
  rewards: number[];
}

export interface ClanSummary {
  id: number;
  title: string;
  kind: "militia" | "channel" | "group";
  is_militia: boolean;
  color: string;
  members_count: number;
  season_points: number;
  username: string | null;
  subscribers_only: boolean;
  subscribe_url: string | null;
  city_id: number | null;
}

export interface ClanMember {
  id: number;
  first_name: string;
  season_score: number;
}

export interface ClanDetails extends ClanSummary {
  rank: number;
  sectors_held: number;
  invite_link: string;
  is_member: boolean;
  is_owner: boolean;
  top_members: ClanMember[];
}

export interface PlayerState {
  user: PlayerUser;
  onboarded: boolean;
  country_code: string | null;
  country_name: string | null;
  city: CityInfo | null;
  clan: ClanSummary | null;
  clan_joined_at: string | null;
  coins: number;
  total_earned: number;
  level: number;
  level_from: number;
  level_to: number | null;
  energy: number;
  energy_max: number;
  energy_regen_per_sec: number;
  tap_power: number;
  income_per_hour: number;
  offline_cap_hours: number;
  attack_mult: number;
  defense_mult: number;
  vip_until: string | null;
  daily: DailyInfo;
  server_time: string;
}

export interface GameConfig {
  game_name: string;
  bot_username: string;
  max_taps_per_sec: number;
}

export interface SessionResponse {
  created: boolean;
  offline_earned: number;
  invite_clan: ClanSummary | null;
  state: PlayerState;
  config: GameConfig;
}

export type CardCategory = "economy" | "army" | "defense" | "boost";
export type CardEffect = "income" | "attack_bp" | "defense_bp" | "multitap" | "battery";

export interface UpgradeCard {
  id: string;
  category: CardCategory;
  effect: CardEffect;
  level: number;
  max_level: number;
  next_cost: number | null;
  next_gain: number | null;
  total_effect: number;
  battery_step: number | null;
}

export interface ComboStatus {
  found: string[];
  total: number;
  reward: number;
  claimed: boolean;
}
