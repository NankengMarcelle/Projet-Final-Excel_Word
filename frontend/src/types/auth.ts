export interface UserCreate {
  email: string;
  password: string;
  full_name?: string | null;
}

export interface UserRead {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface Token {
  access_token: string;
  token_type: string;
}
