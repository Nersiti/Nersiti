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
  notify_enabled: boolean;
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

export interface MapClan {
  title: string;
  color: string;
  is_militia: boolean;
}

/** [h3, owner_clan_id, defense, value, shielded] */
export type SectorTuple = [string, number | null, number, number, 0 | 1];

export interface MapSectorsResponse {
  sectors: SectorTuple[];
  clans: Record<string, MapClan>;
  truncated: boolean;
}

export interface MapCity {
  id: number;
  name: string;
  lat: number;
  lng: number;
  population: number;
  controller_clan_id: number | null;
}

export interface MapCitiesResponse {
  cities: MapCity[];
  clans: Record<string, MapClan>;
}

export interface SectorLogEntry {
  user: string;
  clan: MapClan | null;
  action: "capture" | "attack" | "reinforce";
  power: number;
  flipped: boolean;
  at: string;
}

export interface SectorDetails {
  h3: string;
  city_id: number;
  value: number;
  owner_clan_id: number | null;
  defense: number;
  shield_until: string | null;
  capture_cost: number;
  city: { id: number; name: string } | null;
  owner: ClanSummary | null;
  is_own: boolean;
  foothold: boolean;
  militia_blocked: boolean;
  attack_mult: number;
  defense_mult: number;
  foothold_divisor: number;
  min_amount: number;
  log: SectorLogEntry[];
}

export interface SectorActionResult {
  action: "capture" | "attack" | "reinforce";
  power: number;
  flipped: boolean;
  foothold: boolean;
}

export interface SeasonInfo {
  number: number;
  starts_at: string;
  ends_at: string;
  seconds_left: number;
  hall_of_fame: { number: number; clans: { id: number; title: string; color: string; points: number }[] }[];
}

export interface PlayerRow {
  id: number;
  name: string;
  score: number;
  country_code: string | null;
}

export interface CountryRow {
  code: string;
  name: string;
  score: number;
}

export interface CityRow {
  id: number;
  name: string;
  country_code: string;
  score: number;
}

export interface Leaderboard<T> {
  items: T[];
  me: { rank: number | null; score?: number } | null;
}

export interface ShopItemInfo {
  id: string;
  stars: number;
  daily_limit: number | null;
  used_today: number;
  param: "none" | "sector" | "color";
  subscription: boolean;
  clan_owner_only: boolean;
  available: boolean;
}

export interface ShopInfo {
  items: ShopItemInfo[];
  palette: string[];
  coins_bag_amount: number;
  is_clan_owner: boolean;
  vip_shield_available: boolean;
}
