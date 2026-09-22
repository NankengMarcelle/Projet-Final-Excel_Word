import { apiClient } from "./client";
import type { WorkbookDetail, WorkbookRead } from "../types/workbook";

export function listWorkbooks(): Promise<WorkbookRead[]> {
  return apiClient.get<WorkbookRead[]>("/workbooks");
}

export function getWorkbook(workbookId: string): Promise<WorkbookDetail> {
  return apiClient.get<WorkbookDetail>(`/workbooks/${workbookId}`);
}

export function importWorkbook(file: File): Promise<WorkbookRead> {
  const form = new FormData();
  form.append("file", file);
  return apiClient.postForm<WorkbookRead>("/workbooks", form);
}

export function deleteWorkbook(workbookId: string): Promise<void> {
  return apiClient.delete<void>(`/workbooks/${workbookId}`);
}

export function renameWorkbook(workbookId: string, filename: string): Promise<WorkbookRead> {
  return apiClient.patch<WorkbookRead>(`/workbooks/${workbookId}`, { filename });
}
