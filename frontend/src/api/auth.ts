import { apiClient } from "./client";
import type { Token, UserCreate, UserRead } from "../types/auth";

export function register(payload: UserCreate): Promise<UserRead> {
  return apiClient.post<UserRead>("/auth/register", payload);
}

export function login(email: string, password: string): Promise<Token> {
  const form = new URLSearchParams();
  form.set("username", email);
  form.set("password", password);
  return apiClient.postForm<Token>("/auth/login", form);
}

export function getCurrentUser(): Promise<UserRead> {
  return apiClient.get<UserRead>("/auth/me");
}
