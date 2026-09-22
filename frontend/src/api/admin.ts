import { apiClient } from "./client";
import type { UserRead } from "../types/auth";

export function listUsers(): Promise<UserRead[]> {
  return apiClient.get<UserRead[]>("/admin/users");
}
