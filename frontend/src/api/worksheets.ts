import { apiClient } from "./client";
import type {
  StructuralEditRequest,
  WorksheetData,
  WorksheetEditRequest,
  WorksheetRead,
} from "../types/worksheet";
import type { WorksheetColumn } from "../types/sheetRelationship";

export function getWorksheet(workbookId: string, worksheetId: string): Promise<WorksheetData> {
  return apiClient.get<WorksheetData>(`/workbooks/${workbookId}/worksheets/${worksheetId}`);
}

export function listWorksheetColumns(
  workbookId: string,
  worksheetId: string,
  headerStartRow: number,
  headerEndRow: number
): Promise<WorksheetColumn[]> {
  const query = new URLSearchParams({
    header_start_row: String(headerStartRow),
    header_end_row: String(headerEndRow),
  });
  return apiClient.get<WorksheetColumn[]>(
    `/workbooks/${workbookId}/worksheets/${worksheetId}/columns?${query}`
  );
}

export function updateWorksheet(
  workbookId: string,
  worksheetId: string,
  payload: WorksheetEditRequest
): Promise<WorksheetRead> {
  return apiClient.put<WorksheetRead>(`/workbooks/${workbookId}/worksheets/${worksheetId}`, payload);
}

export function applyWorksheetStructuralEdit(
  workbookId: string,
  worksheetId: string,
  payload: StructuralEditRequest
): Promise<WorksheetRead> {
  return apiClient.patch<WorksheetRead>(
    `/workbooks/${workbookId}/worksheets/${worksheetId}/structure`,
    payload
  );
}

export function deleteWorksheet(workbookId: string, worksheetId: string): Promise<void> {
  return apiClient.delete<void>(`/workbooks/${workbookId}/worksheets/${worksheetId}`);
}
