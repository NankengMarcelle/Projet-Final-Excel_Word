import { apiClient } from "./client";
import type { ConversionCreateResponse, WordFileRead } from "../types/conversion";
import type { ComputedCellValue } from "../univer/UniverSheetGrid";

export function convertWorksheet(
  worksheetId: string,
  computedValues: ComputedCellValue[] = []
): Promise<ConversionCreateResponse> {
  return apiClient.post<ConversionCreateResponse>(`/worksheets/${worksheetId}/convert`, {
    computed_values: computedValues,
  });
}

export function listWordFiles(): Promise<WordFileRead[]> {
  return apiClient.get<WordFileRead[]>("/conversions");
}

export function deleteConversion(conversionId: string): Promise<void> {
  return apiClient.delete<void>(`/conversions/${conversionId}`);
}
