import { apiClient } from "./client";
import type { UserRead } from "../types/auth";

export interface UserListParams {
  search?: string;
  role?: "user" | "admin";
  is_active?: boolean;
  // YYYY-MM-DD (matches <input type="date">'s own value format, and the backend's date param).
  created_after?: string;
  created_before?: string;
  page?: number;
  page_size?: number;
}

export interface UserListResponse {
  items: UserRead[];
  total: number;
  page: number;
  page_size: number;
}

export function listUsers(params: UserListParams = {}): Promise<UserListResponse> {
  const query = new URLSearchParams();
  if (params.search) query.set("search", params.search);
  if (params.role) query.set("role", params.role);
  if (params.is_active !== undefined) query.set("is_active", String(params.is_active));
  if (params.created_after) query.set("created_after", params.created_after);
  if (params.created_before) query.set("created_before", params.created_before);
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.page_size ?? 25));
  return apiClient.get<UserListResponse>(`/admin/users?${query.toString()}`);
}

export interface UserUpdatePayload {
  role?: "user" | "admin";
  is_active?: boolean;
}

export function updateUser(userId: string, payload: UserUpdatePayload): Promise<UserRead> {
  return apiClient.patch<UserRead>(`/admin/users/${userId}`, payload);
}

export function deleteUser(userId: string): Promise<void> {
  return apiClient.delete<void>(`/admin/users/${userId}`);
}
