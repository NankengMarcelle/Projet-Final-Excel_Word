export interface ConversionRead {
  id: string;
  worksheet_id: string;
  requested_by_id: string;
  status: string;
  created_at: string;
}

export interface WordDocumentRead {
  id: string;
  filename: string;
  file_size_bytes: number | null;
  downloaded_at: string | null;
}

export interface ConversionCreateResponse {
  conversion: ConversionRead;
  word_document: WordDocumentRead;
}

export interface WordFileRead {
  conversion_id: string;
  filename: string;
  file_size_bytes: number | null;
  downloaded_at: string | null;
  created_at: string;
  worksheet_name: string;
  workbook_filename: string;
}
