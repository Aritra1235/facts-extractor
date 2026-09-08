import type {
  DocumentRecord,
  Evidence,
  Fact,
  FactRelationship,
  PageRecord,
  ProcessingJob,
  ProjectRecord,
  Relation,
  UploadResult,
} from "@/lib/types";

const API = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, { cache: "no-store", ...init });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {}
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  projects: () => request<ProjectRecord[]>("/projects"),
  createProject: (name: string, description?: string) =>
    request<ProjectRecord>("/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description: description || null }),
    }),
  documents: (projectId: string) =>
    request<DocumentRecord[]>(`/projects/${projectId}/documents?limit=250`),
  upload: (projectId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<UploadResult>(`/projects/${projectId}/documents`, {
      method: "POST",
      body: form,
    });
  },
  pages: (documentId: string) =>
    request<PageRecord[]>(`/documents/${documentId}/pages`),
  facts: (documentId: string) =>
    request<Fact[]>(`/documents/${documentId}/facts?limit=250`),
  projectFacts: (projectId: string) =>
    request<Fact[]>(`/projects/${projectId}/facts?limit=5000`),
  fact: (factId: string) => request<Fact>(`/facts/${factId}`),
  page: (pageId: string) => request<PageRecord>(`/pages/${pageId}`),
  evidence: (evidenceId: string) =>
    request<Evidence>(`/evidence/${evidenceId}`),
  jobs: async (documentId: string) => {
    const jobs = await request<ProcessingJob[]>(
      `/documents/${documentId}/jobs`,
    );
    if (jobs[0]) jobs[0] = await request<ProcessingJob>(`/jobs/${jobs[0].id}`);
    return jobs;
  },
  job: (jobId: string) => request<ProcessingJob>(`/jobs/${jobId}`),
  retry: (documentId: string) =>
    request<ProcessingJob>(`/documents/${documentId}/process`, {
      method: "POST",
    }),
  relationships: (
    projectId: string,
    documentId?: string,
    relation?: Relation | "ALL",
  ) => {
    const params = new URLSearchParams({ limit: "250" });
    params.set("project_id", projectId);
    if (documentId) params.set("document_id", documentId);
    if (relation && relation !== "ALL") params.set("relation", relation);
    return request<FactRelationship[]>(`/relationships?${params}`);
  },
  documentFile: (documentId: string) => `${API}/documents/${documentId}/file`,
};
