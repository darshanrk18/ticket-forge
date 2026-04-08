const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type ApiErrorPayload = {
  detail?: string;
  message?: string;
};

export type ApiResult<T> = {
  data: T | null;
  error: string | null;
};

export interface UserResponse {
  id: string;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  created_at: string;
}

export interface AuthResponse {
  user: UserResponse;
  access_token: string;
}

export interface TokenResponse {
  access_token: string;
}

export interface ProjectListItem {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  role: string;
  member_count: number;
  created_at: string;
}

export interface BoardColumnRequest {
  name: string;
}

export interface BoardColumn {
  id: string;
  name: string;
  position: number;
}

export interface ProjectMember {
  id: string;
  user_id: string;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  role: string;
  joined_at: string;
}

export interface UserSearchResult {
  id: string;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
}

export interface ProjectResponse {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  board_columns: BoardColumn[];
  members: ProjectMember[];
}

export interface TicketAssigneeResponse {
  id: string;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
}

export interface TicketResponse {
  id: string;
  project_id: string;
  column_id: string;
  ticket_key: string;
  title: string;
  description: string | null;
  priority: string;
  type: string;
  labels: string[];
  due_date: string | null;
  position: number;
  assignee: TicketAssigneeResponse | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface BoardTicketsResponse {
  tickets: TicketResponse[];
}

export interface SigninRequest {
  login: string;
  password: string;
}

export interface SignupRequest {
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  password: string;
}

export interface ProjectCreateRequest {
  name: string;
  description?: string;
  board_columns: BoardColumnRequest[];
  member_ids: string[];
}

export interface AddMemberRequest {
  user_id: string;
  role: string;
}

export interface UpdateMemberRoleRequest {
  role: string;
}

export interface TicketCreateRequest {
  title: string;
  description?: string;
  column_id: string;
  priority?: string;
  type?: string;
  labels?: string[];
  due_date?: string;
  assignee_id?: string | null;
}

export interface TicketUpdateRequest {
  title?: string;
  description?: string;
  priority?: string;
  type?: string;
  labels?: string[];
  due_date?: string;
  assignee_id?: string | null;
}

export interface TicketMoveRequest {
  column_id: string;
  position: number;
}

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: object | undefined;
  token?: string | null;
};

function withJsonHeaders(
  token: string | null | undefined,
  headers?: HeadersInit
): Headers {
  const merged = new Headers(headers);
  if (!merged.has("Content-Type")) {
    merged.set("Content-Type", "application/json");
  }
  if (token) {
    merged.set("Authorization", `Bearer ${token}`);
  }
  return merged;
}

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as ApiErrorPayload;
    return payload.detail || payload.message || response.statusText;
  } catch {
    return response.statusText || "Request failed";
  }
}

async function request<T>(
  path: string,
  { body, token, headers, ...init }: RequestOptions = {}
): Promise<ApiResult<T>> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: withJsonHeaders(token, headers),
      credentials: "include",
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (error) {
    return {
      data: null,
      error: error instanceof Error ? error.message : "Request failed",
    };
  }

  if (!response.ok) {
    return {
      data: null,
      error: await parseError(response),
    };
  }

  if (response.status === 204) {
    return { data: null, error: null };
  }

  const data = (await response.json()) as T;
  return { data, error: null };
}

export function signin(values: SigninRequest) {
  return request<AuthResponse>("/api/v1/auth/signin", {
    method: "POST",
    body: values,
  });
}

export function signup(values: SignupRequest) {
  return request<AuthResponse>("/api/v1/auth/signup", {
    method: "POST",
    body: values,
  });
}

export function refreshSession() {
  return request<TokenResponse>("/api/v1/auth/refresh", {
    method: "POST",
  });
}

export function getCurrentUser(token: string) {
  return request<UserResponse>("/api/v1/auth/me", {
    method: "GET",
    token,
  });
}

export function logout(token: string) {
  return request<{ message: string }>("/api/v1/auth/logout", {
    method: "POST",
    token,
  });
}

export function listProjects(token: string) {
  return request<ProjectListItem[]>("/api/v1/projects", {
    method: "GET",
    token,
  });
}

export function getProject(token: string, slug: string) {
  return request<ProjectResponse>(`/api/v1/projects/${slug}`, {
    method: "GET",
    token,
  });
}

export function createProject(token: string, payload: ProjectCreateRequest) {
  return request<ProjectResponse>("/api/v1/projects", {
    method: "POST",
    token,
    body: payload,
  });
}

export function deleteProject(token: string, slug: string) {
  return request<null>(`/api/v1/projects/${slug}`, {
    method: "DELETE",
    token,
  });
}

export function addProjectMember(
  token: string,
  slug: string,
  payload: AddMemberRequest
) {
  return request<ProjectMember>(`/api/v1/projects/${slug}/members`, {
    method: "POST",
    token,
    body: payload,
  });
}

export function removeProjectMember(
  token: string,
  slug: string,
  userId: string
) {
  return request<null>(`/api/v1/projects/${slug}/members/${userId}`, {
    method: "DELETE",
    token,
  });
}

export function updateMemberRole(
  token: string,
  slug: string,
  userId: string,
  role: string
) {
  return request<ProjectMember>(`/api/v1/projects/${slug}/members/${userId}`, {
    method: "PATCH",
    token,
    body: { role } satisfies UpdateMemberRoleRequest,
  });
}

export function searchUsers(
  token: string,
  query: string,
  projectSlug?: string
) {
  const params = new URLSearchParams({ q: query });
  if (projectSlug) {
    params.set("project_slug", projectSlug);
  }
  return request<UserSearchResult[]>(`/api/v1/users/search?${params.toString()}`, {
    method: "GET",
    token,
  });
}

export function getBoardTickets(token: string, slug: string) {
  return request<BoardTicketsResponse>(`/api/v1/projects/${slug}/tickets`, {
    method: "GET",
    token,
  });
}

export function createTicket(
  token: string,
  slug: string,
  payload: TicketCreateRequest
) {
  return request<TicketResponse>(`/api/v1/projects/${slug}/tickets`, {
    method: "POST",
    token,
    body: payload,
  });
}

export function updateTicket(
  token: string,
  slug: string,
  ticketKey: string,
  payload: TicketUpdateRequest
) {
  return request<TicketResponse>(`/api/v1/projects/${slug}/tickets/${ticketKey}`, {
    method: "PATCH",
    token,
    body: payload,
  });
}

export function moveTicket(
  token: string,
  slug: string,
  ticketKey: string,
  payload: TicketMoveRequest
) {
  return request<TicketResponse>(
    `/api/v1/projects/${slug}/tickets/${ticketKey}/move`,
    {
      method: "PATCH",
      token,
      body: payload,
    }
  );
}

export function deleteTicket(token: string, slug: string, ticketKey: string) {
  return request<null>(`/api/v1/projects/${slug}/tickets/${ticketKey}`, {
    method: "DELETE",
    token,
  });
}
