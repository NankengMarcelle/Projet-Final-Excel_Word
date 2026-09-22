import type { WorksheetRead } from "./worksheet";

export interface WorkbookRead {
  id: string;
  filename: string;
  file_size_bytes: number | null;
  created_at: string;
  updated_at: string;
}

export interface WorkbookDetail extends WorkbookRead {
  worksheets: WorksheetRead[];
}
