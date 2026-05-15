export interface TaskPreview {
  sender: string;
  tag: string;
  receiver: string;
  internal: boolean;
  start: number;
  limit: number;
}

export interface UserSession {
  mobile: string;
  uid: string;
  updated_at: string;
}

export interface TaskRecord {
  id: string;
  filename: string;
  status: string;
  created_at: string;
}
