const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

// Types
export interface StatsOverview {
  total: number;
  interested: number;
  not_interested: number;
  ooo: number;
  unsubscribe: number;
  info_request: number;
  wrong_person: number;
  dnc: number;
  pending_approval: number;
  sent: number;
  avg_response_time_minutes: number | null;
  approval_rate: number | null;
}

export interface CampaignStats {
  campaign_id: string;
  campaign_name: string;
  total: number;
  interested: number;
  not_interested: number;
  ooo: number;
  unsubscribe: number;
  info_request: number;
  wrong_person: number;
  dnc: number;
  interest_rate: number;
}

export interface TimelineEntry {
  date: string;
  total: number;
  interested: number;
  not_interested: number;
  ooo: number;
  unsubscribe: number;
  info_request: number;
}

export interface ResponseTimes {
  avg_approval_time_minutes: number | null;
  avg_send_time_minutes: number | null;
  total_sent: number;
}

export interface FollowUpStats {
  total: number;
  sent: number;
  pending: number;
  by_sequence: Record<string, { total: number; sent: number }>;
}

export interface ReplyItem {
  id: number;
  lead_email: string;
  campaign_name: string;
  category: string;
  status: string;
  reply_body: string;
  draft_response: string;
  received_at: string;
  sent_at: string | null;
}

export interface RepliesResponse {
  replies: ReplyItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

// API functions
export function getStatsOverview(period = "all"): Promise<StatsOverview> {
  return fetchAPI(`/api/stats/overview?period=${period}`);
}

export function getCampaignStats(period = "all"): Promise<{ campaigns: CampaignStats[] }> {
  return fetchAPI(`/api/stats/campaigns?period=${period}`);
}

export function getTimeline(days = 30): Promise<{ timeline: TimelineEntry[] }> {
  return fetchAPI(`/api/stats/timeline?days=${days}`);
}

export function getResponseTimes(): Promise<ResponseTimes> {
  return fetchAPI("/api/stats/response-times");
}

export function getFollowUpStats(): Promise<FollowUpStats> {
  return fetchAPI("/api/stats/followups");
}

export function getReplies(
  page = 1,
  category?: string,
  status?: string
): Promise<RepliesResponse> {
  const params = new URLSearchParams({ page: String(page) });
  if (category) params.set("category", category);
  if (status) params.set("status", status);
  return fetchAPI(`/api/replies?${params}`);
}
