export type Provider = "wos" | "scopus" | "scholar";
export const PROVIDERS: Provider[] = ["wos", "scopus", "scholar"];

export interface User {
  id: number;
  username: string;
  display_name: string;
  role: "admin" | "librarian" | "reviewer";
  active: boolean;
}

export interface Case {
  id: number;
  researcher_name_en: string;
  researcher_name_he: string;
  name_variants: string[];
  orcid: string;
  scopus_author_id: string;
  wos_researcher_id: string;
  notes: string;
  cv_filename: string;
  cv_sha256: string;
  cv_uploaded_at: string | null;
  template_filename: string;
  extraction_confirmed: boolean;
  created_by: string;
  created_at: string;
  prepared_by: string;
  prepared_at: string | null;
  reviewed_by: string;
  reviewed_at: string | null;
  review_note: string;
  publication_count?: number;
}

export interface Policy {
  id: number;
  case_id: number | null;
  included_languages: string[];
  included_statuses: string[];
  included_types: string[];
  self_citation_definition: "A" | "B";
  full_name_match_is_self: boolean;
  summary_mode: "sum" | "unique" | "max" | "empty";
  updated_at: string;
  updated_by: string;
}

export interface Metrics {
  provider: Provider;
  status: "not_checked" | "found" | "not_indexed" | "needs_verification";
  status_label: string;
  record_id: string;
  source_url: string;
  checked_at: string | null;
  total: number | null;
  citing_records: number;
  self_a: number;
  self_b: number;
  non_self_a: number;
  non_self_b: number;
  unresolved_a: number;
  unresolved_b: number;
  missing_records: number;
  definition: string;
  self_selected: number | null;
  non_self_selected: number | null;
  unresolved_selected: number | null;
  non_self_formula: number | null;
  complete: boolean;
  citing_list_status: string;
  warnings: string[];
}

export interface SourceRecord {
  id: number;
  provider: Provider;
  record_id: string;
  found_title: string;
  found_authors: { name: string }[];
  found_year: number | null;
  found_doi: string;
  confidence: number;
  confidence_explanation: string;
  total_citations: number | null;
  retrieved_at: string;
  record_status: string;
  source_url: string;
  method: string;
  entered_by: string;
}

export interface Check {
  provider: Provider;
  status: string;
  selected_record_id: number | null;
  checked_at: string | null;
  checked_by: string;
  citing_list_status: string;
  notes: string;
}

export interface Publication {
  id: number;
  seq: number;
  original_number: string;
  raw_text: string;
  section: string;
  subsection: string;
  title: string;
  authors: string[];
  year: number | null;
  venue: string;
  pub_type: string;
  language: string;
  language_evidence: string;
  doi: string;
  cv_page: number | null;
  pub_status: string;
  status_evidence: string;
  manual_include: boolean | null;
  manual_include_reason: string;
  manually_edited: boolean;
  notes: string;
  included: boolean;
  exclusion_reason: string;
  scholar_search_url: string;
  metrics?: Record<Provider, Metrics>;
  summary?: { mode: string; label: string; non_self: number | null; self: number | null; complete: boolean; note: string };
  checks?: Partial<Record<Provider, Check>>;
  candidates?: SourceRecord[];
  citing_count?: Record<Provider, number>;
}

export interface Author {
  name: string;
  orcid?: string;
  scopus_id?: string;
  researcher_id?: string;
}

export interface Citing {
  id: number;
  publication_id: number;
  provider: Provider;
  title: string;
  doi: string;
  external_id: string;
  year: number | null;
  authors: Author[];
  authors_complete: boolean;
  source_url: string;
  origin: string;
  origin_detail: string;
  class_a: string;
  explain_a: string;
  class_b: string;
  explain_b: string;
  manual_a: string | null;
  manual_b: string | null;
  manual_note: string;
  final_a: string;
  final_b: string;
  manually_confirmed: boolean;
  confirmed_by: string;
}

export interface QAIssue {
  level: "error" | "warning" | "info";
  code: string;
  message: string;
  publication_id: number | null;
  provider: Provider | null;
}

export interface QAResult {
  issues: QAIssue[];
  stats: Record<string, number>;
  errors: number;
  warnings: number;
  ready: boolean;
  manual_changes: number;
}

export interface ProvidersInfo {
  scopus: { configured: boolean; inst_token: boolean; requirements: string[]; env: string[] };
  wos: { configured: boolean; citing_api: boolean; requirements: string[]; env: string[] };
  scholar: { configured: boolean; manual_only: boolean; requirements: string[]; env: string[] };
  external_ai: { enabled: boolean; note: string };
}
