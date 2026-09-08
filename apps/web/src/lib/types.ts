export type DocumentStatus = "UPLOADED" | "PROCESSING" | "COMPLETE" | "FAILED";

export interface ProjectRecord {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  document_count: number;
  completed_document_count: number;
  fact_count: number;
  relationship_count: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentRecord {
  id: string;
  project_id: string;
  sha256: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  title: string | null;
  page_count: number | null;
  status: DocumentStatus;
  created_at: string;
  updated_at: string;
}

export interface ProcessingEvent {
  id: string;
  stage: string;
  level: string;
  message: string;
  progress: number | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface ProcessingJob {
  id: string;
  document_id: string;
  status: "QUEUED" | "RUNNING" | "COMPLETE" | "FAILED";
  stage: string;
  progress: number;
  current_page: number | null;
  total_pages: number | null;
  attempt_count: number;
  error_code: string | null;
  error_message: string | null;
  result: Record<string, number | string>;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  events?: ProcessingEvent[];
}

export interface PageRecord {
  id: string;
  page_index: number;
  printed_page_label: string | null;
  width: number;
  height: number;
  text?: string;
}

export interface Evidence {
  id: string;
  document_id: string;
  page_id: string;
  quote: string;
  element_ids: string[];
  bboxes: number[][];
  section: string | null;
  table_title: string | null;
  row_label: string | null;
  column_label: string | null;
  footnotes: string[];
  attributes: Record<string, unknown>;
}

export interface Fact {
  id: string;
  document_id: string;
  evidence_id: string;
  subject_raw: string;
  subject_canonical: string;
  predicate_raw: string;
  predicate_canonical: string;
  value_raw: string;
  value_kind: string;
  numeric_value: number | null;
  normalized_value: string | null;
  unit_raw: string | null;
  unit_canonical: string | null;
  canonical_numeric_value: number | null;
  claim_kind: string;
  period_start: string | null;
  period_end: string | null;
  period_label: string | null;
  estimate_vintage: string | null;
  context: {
    scope?: string | null;
    supporting_quote?: string;
    period_raw?: string | null;
  };
  confidence: number;
  status: string;
}

export type Relation =
  | "CORROBORATES"
  | "CONTRADICTS"
  | "RECONCILABLE"
  | "RELATED"
  | "NOT_COMPARABLE";

export interface FactRelationship {
  id: string;
  fact_a_id: string;
  fact_b_id: string;
  relation: Relation;
  confidence: number;
  comparison: Record<string, boolean>;
  differences: Array<Record<string, unknown>>;
  explanation: string;
  candidate_score: number;
  classifier_version: string;
  status: string;
}

export interface UploadResult {
  document: DocumentRecord;
  job: ProcessingJob;
  duplicate: boolean;
}
