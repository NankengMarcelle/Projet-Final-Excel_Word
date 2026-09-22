import { apiClient } from "./client";
import type {
  ChildSheetCreateRequest,
  ChildSheetCreateResponse,
  ChildSheetStatus,
  SheetRelationshipRead,
  SyncChildSheetRequest,
} from "../types/sheetRelationship";

export function createChildSheet(
  workbookId: string,
  payload: ChildSheetCreateRequest
): Promise<ChildSheetCreateResponse> {
  return apiClient.post<ChildSheetCreateResponse>(`/workbooks/${workbookId}/child-sheets`, payload);
}

export function listChildSheets(workbookId: string): Promise<SheetRelationshipRead[]> {
  return apiClient.get<SheetRelationshipRead[]>(`/workbooks/${workbookId}/child-sheets`);
}

export function getChildSheetStatus(
  workbookId: string,
  childWorksheetId: string
): Promise<ChildSheetStatus> {
  return apiClient.get<ChildSheetStatus>(
    `/workbooks/${workbookId}/child-sheets/by-child/${childWorksheetId}/status`
  );
}

export function syncChildSheet(
  workbookId: string,
  childWorksheetId: string,
  payload?: SyncChildSheetRequest
): Promise<SheetRelationshipRead[]> {
  return apiClient.post<SheetRelationshipRead[]>(
    `/workbooks/${workbookId}/child-sheets/by-child/${childWorksheetId}/sync`,
    payload
  );
}
