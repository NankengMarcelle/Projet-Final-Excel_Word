import { apiClient } from "./client";
import type { ConversionCreateResponse, WordFileRead } from "../types/conversion";

export function convertWorksheet(worksheetId: string): Promise<ConversionCreateResponse> {
  return apiClient.post<ConversionCreateResponse>(`/worksheets/${worksheetId}/convert`);
}

export function listWordFiles(): Promise<WordFileRead[]> {
  return apiClient.get<WordFileRead[]>("/conversions");
}

export function deleteConversion(conversionId: string): Promise<void> {
  return apiClient.delete<void>(`/conversions/${conversionId}`);
}
