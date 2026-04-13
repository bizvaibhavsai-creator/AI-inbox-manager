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

export function getReplyDetail(replyId: number): Promise<ReplyItem> {
  return fetchAPI(`/api/replies/${replyId}`);
}

export interface FeedbackResponse {
  reply_id: number;
  draft_response: string;
  status: string;
}

export function submitFeedback(replyId: number, feedback: string): Promise<FeedbackResponse> {
  return fetchAPI(`/api/replies/${replyId}/feedback`, {
    method: "POST",
    body: JSON.stringify({ feedback }),
  });
}

export interface ApproveResponse {
  status: string;
  reply_id: number;
  lead_email: string;
  sent_at: string;
}

export function approveReply(replyId: number): Promise<ApproveResponse> {
  return fetchAPI(`/api/replies/${replyId}/approve`, { method: "POST" });
}

export function rejectReply(replyId: number): Promise<{ status: string; reply_id: number }> {
  return fetchAPI(`/api/replies/${replyId}/reject`, { method: "POST" });
}

export interface ThreadEmail {
  id: string;
  from: string;
  to: string;
  subject: string;
  body: string;
  timestamp: string;
  type: "sent" | "received";
  content_preview: string;
}

export interface ThreadResponse {
  reply_id: number;
  lead_email: string;
  campaign_name: string;
  thread: ThreadEmail[];
  count: number;
}

export function getReplyThread(replyId: number): Promise<ThreadResponse> {
  return fetchAPI(`/api/replies/${replyId}/thread`);
}

export interface AppSettingsResponse {
  approval_mode: string;
}

export function getSettings(): Promise<AppSettingsResponse> {
  return fetchAPI("/api/settings");
}

export function updateSettings(approval_mode: string): Promise<AppSettingsResponse> {
  return fetchAPI("/api/settings", {
    method: "PUT",
    body: JSON.stringify({ approval_mode }),
  });
}

// ---------------------------------------------------------------------------
// LinkedIn / HeyReach
// ---------------------------------------------------------------------------

export interface LinkedInCampaign {
  id: number;
  heyreach_campaign_id: string;
  name: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface LinkedInConversation {
  id: number;
  heyreach_conversation_id: string;
  account_id: string;
  lead_name: string;
  lead_linkedin_url: string;
  lead_title: string;
  lead_company: string;
  last_message: string;
  category: string;
  draft_response: string;
  status: string;
  campaign_id: number | null;
  heyreach_campaign_id: string;
  created_at: string;
  sent_at: string | null;
}

export interface LinkedInConversationDetail extends LinkedInConversation {
  thread: { content: string; sent_at: string; is_outgoing: boolean }[];
}

export interface LinkedInConversationsResponse {
  conversations: LinkedInConversation[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface LinkedInAnalyticsDashboard {
  total_conversations: number;
  by_category: Record<string, number>;
  by_status: Record<string, number>;
  interest_rate: number;
  avg_response_hours: number;
  daily_volumes: { date: string; count: number }[];
  campaigns: {
    id: number;
    heyreach_campaign_id: string;
    name: string;
    status: string;
    total_conversations: number;
    by_category: Record<string, number>;
    interest_rate: number;
  }[];
  heyreach_stats: {
    connections_sent: number;
    connections_accepted: number;
    acceptance_rate: number;
    messages_sent: number;
    messages_replied: number;
    reply_rate: number;
    inmails_sent: number;
    inmails_replied: number;
    inmail_reply_rate: number;
    profile_views: number;
  };
  heyreach_stats_error: string | null;
  heyreach_stats_period: { start_date: string; end_date: string };
}

export function syncLinkedInCampaigns(): Promise<{ status: string; created: number; updated: number }> {
  return fetchAPI("/api/linkedin/campaigns/sync", { method: "POST" });
}

export function getLinkedInCampaigns(): Promise<{ campaigns: LinkedInCampaign[]; total: number }> {
  return fetchAPI("/api/linkedin/campaigns");
}

export function syncLinkedInConversations(maxConversations = 50): Promise<{ status: string; count: number; skipped: number }> {
  return fetchAPI(`/api/linkedin/conversations/sync?max_conversations=${maxConversations}`, { method: "POST" });
}

export function getLinkedInConversations(
  page = 1,
  category?: string,
  status?: string
): Promise<LinkedInConversationsResponse> {
  const params = new URLSearchParams({ page: String(page) });
  if (category) params.set("category", category);
  if (status) params.set("status", status);
  return fetchAPI(`/api/linkedin/conversations?${params}`);
}

export function getLinkedInConversation(id: number): Promise<LinkedInConversationDetail> {
  return fetchAPI(`/api/linkedin/conversations/${id}`);
}

export function submitLinkedInFeedback(id: number, feedback: string): Promise<{ id: number; draft_response: string; status: string }> {
  return fetchAPI(`/api/linkedin/conversations/${id}/feedback`, {
    method: "POST",
    body: JSON.stringify({ feedback }),
  });
}

export function approveLinkedInConversation(id: number): Promise<{ status: string; id: number; sent_at: string }> {
  return fetchAPI(`/api/linkedin/conversations/${id}/approve`, { method: "POST" });
}

export function rejectLinkedInConversation(id: number): Promise<{ status: string; id: number }> {
  return fetchAPI(`/api/linkedin/conversations/${id}/reject`, { method: "POST" });
}

export function getLinkedInAnalyticsDashboard(
  period = "month",
  start_date?: string,
  end_date?: string
): Promise<LinkedInAnalyticsDashboard> {
  const params = new URLSearchParams({ period });
  if (start_date) params.set("start_date", start_date);
  if (end_date) params.set("end_date", end_date);
  return fetchAPI(`/api/linkedin/analytics/dashboard?${params}`);
}
