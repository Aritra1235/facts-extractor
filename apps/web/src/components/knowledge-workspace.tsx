"use client";

import {
  Check,
  ChevronDown,
  ExternalLink,
  FileUp,
  FolderPlus,
  Plus,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import {
  type ChangeEvent,
  type DragEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ModeToggle } from "@/components/ui/dark-toggle";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarInset,
  SidebarMenuButton,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type {
  DocumentRecord,
  Evidence,
  Fact,
  FactRelationship,
  PageRecord,
  ProcessingJob,
  ProjectRecord,
  Relation,
} from "@/lib/types";

type View =
  | "projects"
  | "overview"
  | "facts"
  | "documents"
  | "relationships"
  | "failures";
type DocumentTab = "facts" | "source" | "pipeline";
type RelationFilter = Relation | "ALL";

const relationLabels: Record<Relation, string> = {
  CORROBORATES: "Corroborates",
  CONTRADICTS: "Contradicts",
  RECONCILABLE: "Reconcilable",
  RELATED: "Related",
  NOT_COMPARABLE: "Not comparable",
};

const relationStyles: Record<Relation, string> = {
  CORROBORATES:
    "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  CONTRADICTS:
    "border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-300",
  RECONCILABLE:
    "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300",
  RELATED:
    "border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-300",
  NOT_COMPARABLE:
    "border-slate-200 bg-slate-100 text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300",
};

function formatDate(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatBytes(value: number) {
  return value < 1024 * 1024
    ? `${Math.round(value / 1024)} KB`
    : `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function statusVariant(
  status: string,
): "success" | "warning" | "danger" | "secondary" {
  if (status === "COMPLETE") return "success";
  if (status === "FAILED") return "danger";
  if (status === "RUNNING" || status === "PROCESSING") return "warning";
  return "secondary";
}

function shortPredicate(predicate: string) {
  return predicate.split(".").slice(-1)[0].replaceAll("_", " ");
}

function MetricCard({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-sm font-medium text-muted-foreground">{label}</p>
        <p className="mt-2 text-2xl font-semibold tracking-[-0.04em]">
          {value}
        </p>
      </CardContent>
    </Card>
  );
}

function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex min-h-40 flex-col items-center justify-center rounded-xl border border-dashed bg-card px-6 text-center">
      <p className="font-semibold">{title}</p>
      {description && (
        <p className="mt-2 max-w-md text-sm text-muted-foreground">
          {description}
        </p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

function RelationshipBadge({ relation }: { relation: Relation }) {
  return (
    <span
      className={`inline-flex h-7 items-center rounded-md border px-2.5 text-xs font-semibold ${relationStyles[relation]}`}
    >
      {relationLabels[relation]}
    </span>
  );
}

function JobStrip({
  job,
  onRetry,
}: {
  job?: ProcessingJob;
  onRetry: () => void;
}) {
  if (!job) return null;
  if (job.status === "COMPLETE")
    return (
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-emerald-500/25 bg-emerald-500/10 px-5 py-3 text-sm text-emerald-900 dark:text-emerald-200">
        <Badge variant="success">Complete</Badge>
        <span>{job.result.facts ?? 0} facts</span>
        <span>{job.result.evidence_regions ?? 0} evidence regions</span>
        <span>{job.result.relationships ?? 0} relationships</span>
      </div>
    );
  if (job.status === "FAILED")
    return (
      <div className="flex items-center gap-4 border-b border-red-500/25 bg-red-500/10 px-5 py-3 text-sm text-red-900 dark:text-red-200">
        <Badge variant="danger">Failed</Badge>
        <span className="min-w-0 flex-1 truncate">
          {job.error_message ?? "Processing stopped unexpectedly."}
        </span>
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw />
          Retry
        </Button>
      </div>
    );
  return (
    <div className="border-b border-primary/25 bg-primary/10 px-5 py-3">
      <div className="mb-2 flex items-center justify-between text-sm text-foreground">
        <span className="font-medium capitalize">
          {job.stage.replaceAll("_", " ").toLowerCase()}
        </span>
        <span>{Math.round(job.progress * 100)}%</span>
      </div>
      <Progress
        value={job.progress * 100}
        className="bg-primary/15 [&>div]:bg-primary"
      />
    </div>
  );
}

function FactRow({
  fact,
  selected,
  onSelect,
  source,
}: {
  fact: Fact;
  selected: boolean;
  onSelect: () => void;
  source?: string;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full border-b px-4 py-4 text-left text-foreground transition-colors last:border-0 ${selected ? "bg-primary/12 ring-1 ring-inset ring-primary/35" : "hover:bg-muted/60"}`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="truncate text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
            {fact.subject_raw}
          </p>
          <p className="mt-1.5 line-clamp-2 text-sm font-medium capitalize">
            {shortPredicate(fact.predicate_canonical)}
          </p>
        </div>
        <Badge variant="outline">{Math.round(fact.confidence * 100)}%</Badge>
      </div>
      <p className="mt-3 font-mono text-[15px] font-semibold">
        {fact.value_raw}
        {fact.unit_raw &&
        !fact.value_raw.toLowerCase().includes(fact.unit_raw.toLowerCase())
          ? ` ${fact.unit_raw}`
          : ""}
      </p>
      <p className="mt-2 text-xs text-muted-foreground">
        {fact.period_label ?? "Period not stated"} ·{" "}
        {fact.claim_kind.toLowerCase()}
      </p>
      {source && (
        <p className="mt-1 truncate text-xs text-muted-foreground">{source}</p>
      )}
    </button>
  );
}

function FactInspector({
  fact,
  evidence,
  page,
  document,
}: {
  fact?: Fact;
  evidence?: Evidence;
  page?: PageRecord;
  document?: DocumentRecord;
}) {
  if (!fact) return <EmptyState title="Select a fact" />;
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="border-b">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.1em] text-primary">
                Validated fact
              </p>
              <CardTitle className="mt-1 capitalize">
                {shortPredicate(fact.predicate_canonical)}
              </CardTitle>
            </div>
            <Badge variant="success">
              {Math.round(fact.confidence * 100)}% confidence
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="pt-5">
          <div className="grid gap-5 sm:grid-cols-2">
            <div>
              <p className="text-xs text-muted-foreground">Raw claim</p>
              <p className="mt-1 text-lg font-semibold">
                {fact.value_raw} {fact.unit_raw}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                {fact.subject_raw} · {fact.predicate_raw}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Normalized</p>
              <p className="mt-1 font-mono text-lg font-semibold">
                {fact.normalized_value ?? fact.value_raw} {fact.unit_canonical}
              </p>
              <p className="mt-1 break-all text-sm text-muted-foreground">
                {fact.subject_canonical} · {fact.predicate_canonical}
              </p>
            </div>
          </div>
          <Separator className="my-5" />
          <dl className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
            <div>
              <dt className="text-xs text-muted-foreground">Period</dt>
              <dd className="mt-1 font-medium">
                {fact.period_label ?? "Not stated"}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Claim type</dt>
              <dd className="mt-1 font-medium capitalize">
                {fact.claim_kind.toLowerCase()}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Scope</dt>
              <dd className="mt-1 font-medium">
                {fact.context.scope ?? "Not stated"}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Vintage</dt>
              <dd className="mt-1 font-medium">
                {fact.estimate_vintage ?? "Not applicable"}
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="border-b">
          <div className="flex items-center justify-between gap-4">
            <div>
              <CardTitle>Exact evidence</CardTitle>
              <CardDescription>
                {document?.filename} · page {(page?.page_index ?? 0) + 1}
              </CardDescription>
            </div>
            {document && (
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  window.open(
                    `${api.documentFile(document.id)}#page=${(page?.page_index ?? 0) + 1}`,
                    "_blank",
                  )
                }
              >
                <ExternalLink />
                Open PDF
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="pt-5">
          <blockquote className="border-l-2 border-primary pl-4 text-[15px] leading-7 text-foreground/90">
            {evidence?.quote ??
              fact.context.supporting_quote ??
              "Loading evidence…"}
          </blockquote>
        </CardContent>
      </Card>
    </div>
  );
}

function ProjectDirectory({
  projects,
  onOpen,
  onNew,
}: {
  projects: ProjectRecord[];
  onOpen: (projectId: string) => void;
  onNew: () => void;
}) {
  return (
    <div className="mx-auto max-w-[1480px] space-y-5">
      <div className="flex justify-end">
        <Button onClick={onNew}>
          <FolderPlus />
          New project
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {projects.map((project) => (
          <Card
            key={project.id}
            className="group cursor-pointer transition-colors hover:border-blue-500/60"
            onClick={() => onOpen(project.id)}
          >
            <CardHeader className="border-b p-4">
              <div className="flex items-start justify-between gap-4">
                <CardTitle className="text-xl">{project.name}</CardTitle>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={(event) => {
                    event.stopPropagation();
                    onOpen(project.id);
                  }}
                >
                  Open
                </Button>
              </div>
            </CardHeader>
            <CardContent className="grid grid-cols-3 gap-4 p-4">
              <div>
                <p className="text-2xl font-semibold">
                  {project.document_count}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">PDFs</p>
              </div>
              <div>
                <p className="text-2xl font-semibold">{project.fact_count}</p>
                <p className="mt-1 text-xs text-muted-foreground">Facts</p>
              </div>
              <div>
                <p className="text-2xl font-semibold">
                  {project.relationship_count}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Relationships
                </p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

export function KnowledgeWorkspace() {
  const [view, setView] = useState<View>("projects");
  const [documentTab, setDocumentTab] = useState<DocumentTab>("facts");
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>();
  const [creatingProject, setCreatingProject] = useState(false);
  const [createProjectOpen, setCreateProjectOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectDescription, setNewProjectDescription] = useState("");
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string>();
  const [facts, setFacts] = useState<Fact[]>([]);
  const [projectFacts, setProjectFacts] = useState<Fact[]>([]);
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [relationships, setRelationships] = useState<FactRelationship[]>([]);
  const [selectedFactId, setSelectedFactId] = useState<string>();
  const [selectedEvidence, setSelectedEvidence] = useState<Evidence>();
  const [selectedRelationshipId, setSelectedRelationshipId] =
    useState<string>();
  const [relationshipFacts, setRelationshipFacts] = useState<[Fact, Fact]>();
  const [relationshipEvidence, setRelationshipEvidence] =
    useState<[Evidence, Evidence]>();
  const [relationFilter, setRelationFilter] = useState<RelationFilter>("ALL");
  const [factSearch, setFactSearch] = useState("");
  const [factKind, setFactKind] = useState("ALL");
  const [factDocument, setFactDocument] = useState("ALL");
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [notice, setNotice] = useState<string>();
  const inputRef = useRef<HTMLInputElement>(null);

  const selectedProject = projects.find(
    (item) => item.id === selectedProjectId,
  );
  const selectedDocument = documents.find(
    (item) => item.id === selectedDocumentId,
  );
  const factPool = view === "facts" ? projectFacts : facts;
  const selectedFact = factPool.find((item) => item.id === selectedFactId);
  const selectedFactDocument = documents.find(
    (item) => item.id === selectedFact?.document_id,
  );
  const [selectedEvidencePage, setSelectedEvidencePage] =
    useState<PageRecord>();
  const latestJob = jobs[0];

  const refreshProjects = useCallback(async () => {
    const next = await api.projects();
    setProjects(next);
    setSelectedProjectId((current) =>
      next.some((item) => item.id === current) ? current : next[0]?.id,
    );
    return next;
  }, []);

  const refreshDocuments = useCallback(async () => {
    if (!selectedProjectId) return [];
    const next = await api.documents(selectedProjectId);
    setDocuments(next);
    setSelectedDocumentId((current) =>
      next.some((item) => item.id === current) ? current : next[0]?.id,
    );
    return next;
  }, [selectedProjectId]);

  useEffect(() => {
    refreshProjects()
      .catch((error: Error) => setNotice(error.message))
      .finally(() => setLoading(false));
  }, [refreshProjects]);

  useEffect(() => {
    if (!selectedProjectId) return;
    setDocuments([]);
    setRelationships([]);
    setFacts([]);
    setProjectFacts([]);
    setJobs([]);
    setSelectedDocumentId(undefined);
    Promise.all([
      api.documents(selectedProjectId),
      api.relationships(selectedProjectId),
      api.projectFacts(selectedProjectId),
    ])
      .then(([nextDocuments, nextRelationships, nextProjectFacts]) => {
        setDocuments(nextDocuments);
        setRelationships(nextRelationships);
        setProjectFacts(nextProjectFacts);
        setSelectedDocumentId(nextDocuments[0]?.id);
      })
      .catch((error: Error) => setNotice(error.message));
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedDocumentId) return;
    let cancelled = false;
    Promise.all([api.facts(selectedDocumentId), api.jobs(selectedDocumentId)])
      .then(([nextFacts, nextJobs]) => {
        if (cancelled) return;
        setFacts(nextFacts);
        setJobs(nextJobs);
        setSelectedFactId((current) =>
          nextFacts.some((item) => item.id === current)
            ? current
            : nextFacts[0]?.id,
        );
      })
      .catch((error: Error) => setNotice(error.message));
    return () => {
      cancelled = true;
    };
  }, [selectedDocumentId]);

  useEffect(() => {
    if (!selectedFact) {
      setSelectedEvidence(undefined);
      setSelectedEvidencePage(undefined);
      return;
    }
    api
      .evidence(selectedFact.evidence_id)
      .then(async (nextEvidence) => {
        setSelectedEvidence(nextEvidence);
        setSelectedEvidencePage(await api.page(nextEvidence.page_id));
      })
      .catch((error: Error) => setNotice(error.message));
  }, [selectedFact]);

  useEffect(() => {
    const hasActive = documents.some(
      (item) => item.status === "PROCESSING" || item.status === "UPLOADED",
    );
    if (!hasActive) return;
    const interval = window.setInterval(async () => {
      try {
        const nextDocuments = await refreshDocuments();
        if (selectedDocumentId) {
          const nextJobs = await api.jobs(selectedDocumentId);
          setJobs(nextJobs);
          if (nextJobs[0]?.status === "COMPLETE") {
            setFacts(await api.facts(selectedDocumentId));
            if (selectedProjectId) {
              const [nextRelationships, nextProjectFacts] = await Promise.all([
                api.relationships(selectedProjectId),
                api.projectFacts(selectedProjectId),
              ]);
              setRelationships(nextRelationships);
              setProjectFacts(nextProjectFacts);
              await refreshProjects();
            }
          }
        }
        if (
          !nextDocuments.some(
            (item) =>
              item.status === "PROCESSING" || item.status === "UPLOADED",
          )
        )
          window.clearInterval(interval);
      } catch {}
    }, 3000);
    return () => window.clearInterval(interval);
  }, [
    documents,
    refreshDocuments,
    refreshProjects,
    selectedDocumentId,
    selectedProjectId,
  ]);

  const handleUpload = async (file?: File) => {
    if (!file || !selectedProjectId) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setNotice("Choose a PDF file.");
      return;
    }
    setUploading(true);
    setNotice(undefined);
    try {
      const result = await api.upload(selectedProjectId, file);
      await Promise.all([refreshDocuments(), refreshProjects()]);
      setSelectedDocumentId(result.document.id);
      setJobs([result.job]);
      setView("documents");
      setDocumentTab("pipeline");
      setNotice(
        result.duplicate
          ? "This PDF already exists. Opened its latest job."
          : "PDF accepted. Processing has started.",
      );
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Upload failed.");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const handleCreateProject = async (name: string, description: string) => {
    setCreatingProject(true);
    setNotice(undefined);
    try {
      const project = await api.createProject(name, description);
      await refreshProjects();
      setSelectedProjectId(project.id);
      setView("overview");
      setCreateProjectOpen(false);
      setNewProjectName("");
      setNewProjectDescription("");
      setNotice(
        `Created ${project.name}. Add PDFs to build its knowledge layer.`,
      );
    } catch (error) {
      setNotice(
        error instanceof Error ? error.message : "Project creation failed.",
      );
      throw error;
    } finally {
      setCreatingProject(false);
    }
  };

  const openProject = (projectId: string) => {
    setSelectedProjectId(projectId);
    setView("overview");
  };

  const handleRetry = useCallback(async () => {
    if (!selectedDocumentId) return;
    try {
      const job = await api.retry(selectedDocumentId);
      setJobs((current) => [
        job,
        ...current.filter((item) => item.id !== job.id),
      ]);
      setNotice("Processing queued from the latest durable checkpoint.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Retry failed.");
    }
  }, [selectedDocumentId]);

  useEffect(() => {
    const context = document.modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    const register = async () => {
      await context.registerTool(
        {
          name: "open_knowledge_view",
          title: "Open knowledge view",
          description:
            "Open the project directory, project overview, document facts, relationship review, or failure review in the visible workspace.",
          inputSchema: {
            type: "object",
            properties: {
              view: {
                type: "string",
                enum: [
                  "projects",
                  "overview",
                  "facts",
                  "documents",
                  "relationships",
                  "failures",
                ],
              },
              projectId: { type: "string" },
              documentId: { type: "string" },
            },
            required: ["view"],
            additionalProperties: false,
          },
          annotations: { readOnlyHint: true, untrustedContentHint: false },
          execute(input) {
            const value = input as {
              view?: View;
              projectId?: string;
              documentId?: string;
            };
            if (
              !value.view ||
              ![
                "projects",
                "overview",
                "facts",
                "documents",
                "relationships",
                "failures",
              ].includes(value.view)
            )
              throw new Error("Invalid knowledge view");
            if (
              value.projectId &&
              !projects.some((item) => item.id === value.projectId)
            )
              throw new Error("Project does not exist");
            if (
              value.documentId &&
              !documents.some((item) => item.id === value.documentId)
            )
              throw new Error("Document does not exist");
            if (value.projectId) setSelectedProjectId(value.projectId);
            if (value.documentId) {
              const target = documents.find(
                (item) => item.id === value.documentId,
              );
              if (target) setSelectedProjectId(target.project_id);
              setSelectedDocumentId(value.documentId);
            }
            setView(value.view);
            return {
              view: value.view,
              projectId: value.projectId ?? selectedProjectId ?? null,
              documentId: value.documentId ?? selectedDocumentId ?? null,
            };
          },
        },
        { signal: lifecycle.signal },
      );
    };
    void register().catch((error: unknown) => {
      if (error instanceof DOMException && error.name === "AbortError") return;
      console.error("WebMCP registration failed", error);
    });
    return () => lifecycle.abort();
  }, [documents, projects, selectedDocumentId, selectedProjectId]);

  const filteredFacts = useMemo(() => {
    const query = factSearch.trim().toLowerCase();
    return factPool.filter(
      (fact) =>
        (factKind === "ALL" || fact.claim_kind === factKind) &&
        (view !== "facts" ||
          factDocument === "ALL" ||
          fact.document_id === factDocument) &&
        (!query ||
          `${fact.subject_raw} ${fact.predicate_raw} ${fact.predicate_canonical} ${fact.value_raw} ${fact.period_label}`
            .toLowerCase()
            .includes(query)),
    );
  }, [factDocument, factKind, factPool, factSearch, view]);
  const filteredRelationships = useMemo(
    () =>
      relationships.filter(
        (item) => relationFilter === "ALL" || item.relation === relationFilter,
      ),
    [relationFilter, relationships],
  );

  useEffect(() => {
    if (view !== "facts") return;
    setSelectedFactId((current) =>
      filteredFacts.some((item) => item.id === current)
        ? current
        : filteredFacts[0]?.id,
    );
  }, [filteredFacts, view]);

  const selectedRelationship =
    relationships.find((item) => item.id === selectedRelationshipId) ??
    filteredRelationships[0];
  const relationCounts = useMemo(
    () =>
      Object.fromEntries(
        (Object.keys(relationLabels) as Relation[]).map((key) => [
          key,
          relationships.filter((item) => item.relation === key).length,
        ]),
      ) as Record<Relation, number>,
    [relationships],
  );

  useEffect(() => {
    if (!selectedRelationship) {
      setRelationshipFacts(undefined);
      setRelationshipEvidence(undefined);
      return;
    }
    Promise.all([
      api.fact(selectedRelationship.fact_a_id),
      api.fact(selectedRelationship.fact_b_id),
    ])
      .then(async ([a, b]) => {
        setRelationshipFacts([a, b]);
        setRelationshipEvidence(
          await Promise.all([
            api.evidence(a.evidence_id),
            api.evidence(b.evidence_id),
          ]),
        );
      })
      .catch((error: Error) => setNotice(error.message));
  }, [selectedRelationship]);

  const openDocument = (id: string) => {
    setSelectedDocumentId(id);
    setView("documents");
    setDocumentTab("facts");
  };
  const rejectedSamples =
    latestJob?.events?.flatMap(
      (event) =>
        (event.details.samples as Array<Record<string, unknown>> | undefined) ??
        [],
    ) ?? [];
  const requiredCases = [
    {
      title: "Corroboration",
      count: relationCounts.CORROBORATES,
      relation: "CORROBORATES" as Relation,
      view: "relationships" as View,
    },
    {
      title: "Likely contradiction",
      count: relationCounts.CONTRADICTS,
      relation: "CONTRADICTS" as Relation,
      view: "relationships" as View,
    },
    {
      title: "Contextual reconciliation",
      count: relationCounts.RECONCILABLE,
      relation: "RECONCILABLE" as Relation,
      view: "relationships" as View,
    },
    {
      title: "Failure case",
      count:
        rejectedSamples.length +
        documents.filter((item) => item.status === "FAILED").length,
      view: "failures" as View,
    },
  ];

  return (
    <SidebarProvider>
      <Sidebar>
        <SidebarHeader className="border-b border-white/10 p-5">
          <div className="flex items-center gap-3">
            <div className="grid size-9 place-items-center rounded-lg bg-blue-500 text-sm font-bold text-white">
              FK
            </div>
            <div>
              <p className="text-sm font-semibold text-white">Fact Knowledge</p>
            </div>
          </div>
        </SidebarHeader>
        <SidebarContent className="py-5">
          <p className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
            Projects
          </p>
          <nav className="space-y-1">
            <DropdownMenu>
              <DropdownMenuTrigger className="flex h-10 w-full items-center rounded-lg px-3 text-left text-sm font-medium text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-2 focus-visible:outline-sidebar-ring">
                <span className="min-w-0 flex-1 truncate">
                  {selectedProject?.name ?? "Projects"}
                </span>
                <ChevronDown className="size-4 text-slate-500" />
              </DropdownMenuTrigger>
              <DropdownMenuContent
                side="bottom"
                align="start"
                sideOffset={6}
                className="min-w-60"
              >
                <DropdownMenuItem onClick={() => setView("projects")}>
                  All projects
                  {view === "projects" && <Check className="ml-auto" />}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                {projects.map((project) => (
                  <DropdownMenuItem
                    key={project.id}
                    onClick={() => openProject(project.id)}
                  >
                    <span className="min-w-0 flex-1 truncate">
                      {project.name}
                    </span>
                    {project.id === selectedProjectId &&
                      view !== "projects" && <Check className="ml-auto" />}
                  </DropdownMenuItem>
                ))}
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => setCreateProjectOpen(true)}>
                  <Plus />
                  New project
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </nav>
          {selectedProject && (
            <>
              <Separator className="my-4 bg-white/10" />
              <nav className="space-y-1">
                <SidebarMenuButton
                  active={view === "overview"}
                  onClick={() => setView("overview")}
                >
                  <span className="flex-1">Overview</span>
                </SidebarMenuButton>
                <SidebarMenuButton
                  active={view === "facts"}
                  onClick={() => setView("facts")}
                >
                  <span className="flex-1">Facts</span>
                  <span className="text-slate-500">{projectFacts.length}</span>
                </SidebarMenuButton>
                <SidebarMenuButton
                  active={view === "documents"}
                  onClick={() => setView("documents")}
                >
                  <span className="flex-1">Documents</span>
                  <span className="text-slate-500">{documents.length}</span>
                </SidebarMenuButton>
                <SidebarMenuButton
                  active={view === "relationships"}
                  onClick={() => setView("relationships")}
                >
                  <span className="flex-1">Relationships</span>
                  <span className="text-slate-500">{relationships.length}</span>
                </SidebarMenuButton>
                <SidebarMenuButton
                  active={view === "failures"}
                  onClick={() => setView("failures")}
                >
                  <span className="flex-1">Failure review</span>
                  <span className="text-slate-500">
                    {
                      documents.filter((item) => item.status === "FAILED")
                        .length
                    }
                  </span>
                </SidebarMenuButton>
              </nav>
              <Separator className="my-5 bg-white/10" />
              <div className="flex items-center justify-between px-3 pb-2">
                <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                  Project PDFs
                </p>
                <button
                  type="button"
                  onClick={() => inputRef.current?.click()}
                  className="text-xs font-medium text-blue-400"
                >
                  Add
                </button>
              </div>
              <div className="space-y-1">
                {documents.slice(0, 12).map((document) => (
                  <SidebarMenuButton
                    key={document.id}
                    active={
                      view === "documents" && selectedDocumentId === document.id
                    }
                    className="h-auto min-h-12 py-2.5"
                    onClick={() => openDocument(document.id)}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate">
                        {document.filename}
                      </span>
                      <span className="mt-0.5 block text-xs font-normal text-slate-500">
                        {document.page_count ?? "—"} pages ·{" "}
                        {document.status.toLowerCase()}
                      </span>
                    </span>
                    <span
                      className={`size-1.5 rounded-full ${document.status === "COMPLETE" ? "bg-emerald-400" : document.status === "FAILED" ? "bg-red-400" : "bg-amber-400"}`}
                    />
                  </SidebarMenuButton>
                ))}
              </div>
            </>
          )}
        </SidebarContent>
        <SidebarFooter className="border-t border-white/10">
          <ModeToggle />
        </SidebarFooter>
      </Sidebar>
      <SidebarInset className="bg-[#f5f7fa] dark:bg-background">
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b bg-background/95 px-4 backdrop-blur md:px-6">
          <SidebarTrigger />
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-[15px] font-semibold">
              {view === "projects"
                ? "Projects"
                : view === "overview"
                  ? (selectedProject?.name ?? "Project overview")
                  : view === "facts"
                    ? "Facts"
                    : view === "documents"
                      ? (selectedDocument?.filename ?? "Documents")
                      : view === "relationships"
                        ? "Relationship review"
                        : "Failure review"}
            </h1>
          </div>
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,.pdf"
            className="hidden"
            onChange={(event: ChangeEvent<HTMLInputElement>) =>
              handleUpload(event.target.files?.[0])
            }
          />
          {view !== "projects" && selectedProject && (
            <Button
              onClick={() => inputRef.current?.click()}
              disabled={uploading}
            >
              <FileUp />
              {uploading ? "Uploading…" : "Upload PDF"}
            </Button>
          )}
        </header>
        {notice && (
          <div className="flex items-center gap-3 border-b border-primary/25 bg-primary/10 px-5 py-3 text-sm text-foreground">
            <span className="flex-1">{notice}</span>
            <button
              type="button"
              aria-label="Dismiss"
              onClick={() => setNotice(undefined)}
            >
              <X className="size-4" />
            </button>
          </div>
        )}
        {view === "documents" && (
          <JobStrip job={latestJob} onRetry={handleRetry} />
        )}
        <div className="p-4 md:p-6">
          {loading ? (
            <div className="grid gap-4 md:grid-cols-4">
              {["documents", "facts", "relationships", "attention"].map(
                (item) => (
                  <Skeleton key={item} className="h-36" />
                ),
              )}
            </div>
          ) : view === "projects" ? (
            <ProjectDirectory
              projects={projects}
              onOpen={openProject}
              onNew={() => setCreateProjectOpen(true)}
            />
          ) : view === "overview" ? (
            <div className="mx-auto max-w-[1480px] space-y-5">
              <div className="flex justify-end">
                <Button
                  variant="outline"
                  onClick={async () => {
                    await Promise.all([refreshDocuments(), refreshProjects()]);
                    if (selectedProjectId)
                      setRelationships(
                        await api.relationships(selectedProjectId),
                      );
                  }}
                >
                  <RefreshCw />
                  Refresh
                </Button>
              </div>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <MetricCard label="Documents" value={documents.length} />
                <MetricCard
                  label="Grounded facts"
                  value={selectedProject?.fact_count ?? facts.length}
                />
                <MetricCard
                  label="Relationships"
                  value={relationships.length}
                />
                <MetricCard
                  label="Needs attention"
                  value={
                    documents.filter((item) => item.status === "FAILED").length
                  }
                />
              </div>
              <Card>
                <CardHeader className="border-b">
                  <CardTitle>Required cases</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-3 pt-5 md:grid-cols-2 xl:grid-cols-4">
                  {requiredCases.map((item) => (
                    <button
                      key={item.title}
                      type="button"
                      onClick={() => {
                        if (item.relation) setRelationFilter(item.relation);
                        setView(item.view);
                      }}
                      className="rounded-lg border p-3 text-left transition-colors hover:border-blue-500/60 hover:bg-muted/40"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm font-semibold">{item.title}</p>
                        <Badge variant={item.count ? "success" : "secondary"}>
                          {item.count ? `${item.count} found` : "Missing"}
                        </Badge>
                      </div>
                    </button>
                  ))}
                </CardContent>
              </Card>
              <div className="grid gap-6 xl:grid-cols-[1.35fr_0.65fr]">
                <Card>
                  <CardHeader className="flex-row items-center justify-between border-b">
                    <CardTitle>Documents</CardTitle>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setView("documents")}
                    >
                      Review facts
                    </Button>
                  </CardHeader>
                  <CardContent className="p-0">
                    {documents.length === 0 ? (
                      <div className="p-5">
                        <EmptyState title="No documents yet" />
                      </div>
                    ) : (
                      documents.map((document) => (
                        <button
                          key={document.id}
                          type="button"
                          onClick={() => openDocument(document.id)}
                          className="grid w-full grid-cols-[1fr_auto] items-center gap-4 border-b px-5 py-4 text-left last:border-0 hover:bg-muted/50 md:grid-cols-[1fr_100px_130px_auto]"
                        >
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold">
                              {document.filename}
                            </p>
                          </div>
                          <span className="hidden text-sm text-muted-foreground md:block">
                            {document.page_count ?? "—"} pages
                          </span>
                          <span className="hidden text-sm text-muted-foreground md:block">
                            {formatBytes(document.size_bytes)}
                          </span>
                          <Badge variant={statusVariant(document.status)}>
                            {document.status.toLowerCase()}
                          </Badge>
                        </button>
                      ))
                    )}
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="border-b">
                    <CardTitle>Relationship mix</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4 pt-5">
                    {(Object.keys(relationLabels) as Relation[]).map(
                      (relation) => (
                        <button
                          type="button"
                          key={relation}
                          onClick={() => {
                            setRelationFilter(relation);
                            setView("relationships");
                          }}
                          className="block w-full text-left"
                        >
                          <div className="mb-2 flex justify-between text-sm">
                            <span className="font-medium">
                              {relationLabels[relation]}
                            </span>
                            <span className="text-muted-foreground">
                              {relationCounts[relation]}
                            </span>
                          </div>
                          <Progress
                            value={
                              relationships.length
                                ? (relationCounts[relation] /
                                    relationships.length) *
                                  100
                                : 0
                            }
                          />
                        </button>
                      ),
                    )}
                  </CardContent>
                </Card>
              </div>
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                onDragEnter={() => setDragging(true)}
                onDragLeave={() => setDragging(false)}
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event: DragEvent<HTMLButtonElement>) => {
                  event.preventDefault();
                  setDragging(false);
                  handleUpload(event.dataTransfer.files[0]);
                }}
                className={`rounded-xl border-2 border-dashed p-5 text-center text-foreground transition-colors ${dragging ? "border-primary bg-primary/10" : "border-border bg-card"}`}
              >
                <p className="font-semibold">Drop PDF here</p>
                <span className="mt-3 inline-flex h-8 items-center gap-1.5 rounded-lg border bg-background px-2.5 text-sm font-medium shadow-sm">
                  <FileUp />
                  Browse
                </span>
              </button>
            </div>
          ) : view === "facts" ? (
            <div className="mx-auto max-w-[1540px]">
              {projectFacts.length === 0 ? (
                <EmptyState title="No facts yet" />
              ) : (
                <div className="grid min-h-[calc(100vh-120px)] gap-5 xl:grid-cols-[410px_minmax(0,1fr)]">
                  <Card className="overflow-hidden">
                    <div className="space-y-2 border-b p-3">
                      <div className="relative">
                        <Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" />
                        <Input
                          value={factSearch}
                          onChange={(event) =>
                            setFactSearch(event.target.value)
                          }
                          placeholder={`Search ${projectFacts.length} facts`}
                          className="pl-9"
                        />
                      </div>
                      <div className="flex gap-1 overflow-x-auto">
                        {[
                          "ALL",
                          "OBSERVATION",
                          "ESTIMATE",
                          "FORECAST",
                          "TARGET",
                        ].map((kind) => (
                          <button
                            key={kind}
                            type="button"
                            onClick={() => setFactKind(kind)}
                            className={`shrink-0 rounded-md px-2 py-1 text-xs font-medium ${factKind === kind ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground"}`}
                          >
                            {kind.toLowerCase()}
                          </button>
                        ))}
                      </div>
                      <DropdownMenu>
                        <DropdownMenuTrigger className="flex h-9 w-full items-center rounded-md border bg-background px-3 text-sm">
                          <span className="min-w-0 flex-1 truncate text-left">
                            {factDocument === "ALL"
                              ? "All documents"
                              : documents.find(
                                  (item) => item.id === factDocument,
                                )?.filename}
                          </span>
                          <ChevronDown className="size-4 text-muted-foreground" />
                        </DropdownMenuTrigger>
                        <DropdownMenuContent className="min-w-80">
                          <DropdownMenuItem
                            onClick={() => setFactDocument("ALL")}
                          >
                            All documents
                            {factDocument === "ALL" && (
                              <Check className="ml-auto" />
                            )}
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          {documents.map((document) => (
                            <DropdownMenuItem
                              key={document.id}
                              onClick={() => setFactDocument(document.id)}
                            >
                              <span className="min-w-0 flex-1 truncate">
                                {document.filename}
                              </span>
                              {factDocument === document.id && (
                                <Check className="ml-auto" />
                              )}
                            </DropdownMenuItem>
                          ))}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                    <div className="max-h-[calc(100vh-250px)] overflow-y-auto">
                      {filteredFacts.map((fact) => (
                        <FactRow
                          key={fact.id}
                          fact={fact}
                          selected={selectedFactId === fact.id}
                          onSelect={() => setSelectedFactId(fact.id)}
                          source={
                            documents.find(
                              (item) => item.id === fact.document_id,
                            )?.filename
                          }
                        />
                      ))}
                    </div>
                  </Card>
                  <FactInspector
                    fact={selectedFact}
                    evidence={selectedEvidence}
                    page={selectedEvidencePage}
                    document={selectedFactDocument}
                  />
                </div>
              )}
            </div>
          ) : view === "documents" ? (
            <div className="mx-auto max-w-[1540px] space-y-5">
              {!selectedDocument ? (
                <EmptyState title="No document selected" />
              ) : (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="inline-flex rounded-lg border bg-card p-1">
                      {(["facts", "source", "pipeline"] as DocumentTab[]).map(
                        (tab) => (
                          <button
                            key={tab}
                            type="button"
                            onClick={() => setDocumentTab(tab)}
                            className={`rounded-md px-3 py-1.5 text-sm font-medium capitalize ${documentTab === tab ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}
                          >
                            {tab === "source" ? "Source & evidence" : tab}
                          </button>
                        ),
                      )}
                    </div>
                    <Badge variant={statusVariant(selectedDocument.status)}>
                      {selectedDocument.status.toLowerCase()}
                    </Badge>
                  </div>
                  {documentTab === "facts" &&
                    (facts.length === 0 ? (
                      <EmptyState
                        title="No validated facts yet"
                        description={
                          latestJob?.status === "RUNNING"
                            ? "Processing…"
                            : undefined
                        }
                      />
                    ) : (
                      <div className="grid min-h-[calc(100vh-190px)] gap-5 xl:grid-cols-[390px_minmax(0,1fr)]">
                        <Card className="overflow-hidden">
                          <div className="border-b p-3">
                            <div className="relative">
                              <Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" />
                              <Input
                                value={factSearch}
                                onChange={(event) =>
                                  setFactSearch(event.target.value)
                                }
                                placeholder="Search facts"
                                className="pl-9"
                              />
                            </div>
                            <div className="mt-2 flex gap-1 overflow-x-auto">
                              {[
                                "ALL",
                                "OBSERVATION",
                                "ESTIMATE",
                                "FORECAST",
                                "TARGET",
                              ].map((kind) => (
                                <button
                                  key={kind}
                                  type="button"
                                  onClick={() => setFactKind(kind)}
                                  className={`shrink-0 rounded-md px-2 py-1 text-xs font-medium ${factKind === kind ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground"}`}
                                >
                                  {kind.toLowerCase()}
                                </button>
                              ))}
                            </div>
                          </div>
                          <div className="max-h-[calc(100vh-292px)] overflow-y-auto">
                            {filteredFacts.map((fact) => (
                              <FactRow
                                key={fact.id}
                                fact={fact}
                                selected={selectedFactId === fact.id}
                                onSelect={() => setSelectedFactId(fact.id)}
                              />
                            ))}
                          </div>
                        </Card>
                        <FactInspector
                          fact={selectedFact}
                          evidence={selectedEvidence}
                          page={selectedEvidencePage}
                          document={selectedDocument}
                        />
                      </div>
                    ))}
                  {documentTab === "source" && (
                    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
                      <Card className="overflow-hidden">
                        <iframe
                          title={selectedDocument.filename}
                          src={api.documentFile(selectedDocument.id)}
                          className="h-[calc(100vh-190px)] min-h-[640px] w-full bg-slate-200"
                        />
                      </Card>
                      <Card>
                        <CardHeader className="border-b">
                          <CardTitle>Evidence locator</CardTitle>
                        </CardHeader>
                        <CardContent className="pt-5">
                          {selectedEvidence ? (
                            <>
                              <blockquote className="mt-5 border-l-2 border-blue-600 pl-3 text-sm leading-6">
                                {selectedEvidence.quote}
                              </blockquote>
                              <Button
                                variant="outline"
                                className="mt-5 w-full"
                                onClick={() =>
                                  window.open(
                                    `${api.documentFile(selectedDocument.id)}#page=${(selectedEvidencePage?.page_index ?? 0) + 1}`,
                                    "_blank",
                                  )
                                }
                              >
                                <ExternalLink />
                                Open exact page
                              </Button>
                            </>
                          ) : (
                            <p className="text-sm text-muted-foreground">
                              Select a fact first.
                            </p>
                          )}
                        </CardContent>
                      </Card>
                    </div>
                  )}
                  {documentTab === "pipeline" && (
                    <div className="grid gap-5 xl:grid-cols-[1fr_420px]">
                      <Card>
                        <CardHeader className="border-b">
                          <CardTitle>Processing timeline</CardTitle>
                        </CardHeader>
                        <CardContent className="pt-2">
                          {latestJob?.events?.map((event, index) => (
                            <div
                              key={event.id}
                              className="grid grid-cols-[28px_1fr] gap-3 py-4"
                            >
                              <div className="relative flex justify-center">
                                <span
                                  className={`mt-1.5 size-2.5 rounded-full ${event.level === "ERROR" ? "bg-red-500" : event.level === "WARNING" ? "bg-amber-500" : "bg-blue-600"}`}
                                />
                                {index <
                                  (latestJob.events?.length ?? 0) - 1 && (
                                  <span className="absolute top-5 bottom-[-18px] w-px bg-border" />
                                )}
                              </div>
                              <div>
                                <div className="flex justify-between gap-2">
                                  <p className="text-sm font-semibold">
                                    {event.message}
                                  </p>
                                  <span className="text-xs text-muted-foreground">
                                    {formatDate(event.created_at)}
                                  </span>
                                </div>
                                <p className="mt-1 text-xs uppercase tracking-[0.08em] text-muted-foreground">
                                  {event.stage.replaceAll("_", " ")}
                                  {event.progress != null
                                    ? ` · ${Math.round(event.progress * 100)}%`
                                    : ""}
                                </p>
                              </div>
                            </div>
                          ))}
                        </CardContent>
                      </Card>
                      <Card>
                        <CardHeader className="border-b">
                          <CardTitle>Job record</CardTitle>
                        </CardHeader>
                        <CardContent className="pt-5">
                          <dl className="space-y-4 text-sm">
                            <div className="flex justify-between">
                              <dt className="text-muted-foreground">Status</dt>
                              <dd>
                                <Badge
                                  variant={statusVariant(
                                    latestJob?.status ?? "QUEUED",
                                  )}
                                >
                                  {latestJob?.status.toLowerCase()}
                                </Badge>
                              </dd>
                            </div>
                            <div className="flex justify-between">
                              <dt className="text-muted-foreground">Attempt</dt>
                              <dd>{latestJob?.attempt_count ?? 0}</dd>
                            </div>
                            <div className="flex justify-between">
                              <dt className="text-muted-foreground">Pages</dt>
                              <dd>
                                {latestJob?.current_page ?? 0} /{" "}
                                {latestJob?.total_pages ?? 0}
                              </dd>
                            </div>
                            <div className="flex justify-between">
                              <dt className="text-muted-foreground">
                                Completed
                              </dt>
                              <dd>
                                {formatDate(latestJob?.completed_at ?? null)}
                              </dd>
                            </div>
                          </dl>
                          {latestJob && (
                            <>
                              <Separator className="my-5" />
                              <pre className="max-h-72 overflow-auto rounded-lg bg-slate-950 p-4 text-xs leading-5 text-slate-300">
                                {JSON.stringify(latestJob.result, null, 2)}
                              </pre>
                            </>
                          )}
                        </CardContent>
                      </Card>
                    </div>
                  )}
                </>
              )}
            </div>
          ) : view === "relationships" ? (
            <div className="mx-auto max-w-[1540px] space-y-5">
              <div className="flex flex-wrap gap-2">
                {(
                  ["ALL", ...Object.keys(relationLabels)] as RelationFilter[]
                ).map((relation) => (
                  <button
                    key={relation}
                    type="button"
                    onClick={() => setRelationFilter(relation)}
                    className={`rounded-lg border px-3 py-2 text-sm font-medium ${relationFilter === relation ? "border-primary bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:text-foreground"}`}
                  >
                    {relation === "ALL"
                      ? `All ${relationships.length}`
                      : `${relationLabels[relation]} ${relationCounts[relation]}`}
                  </button>
                ))}
              </div>
              {filteredRelationships.length === 0 ? (
                <EmptyState title="No relationships in this view" />
              ) : (
                <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
                  <Card className="overflow-hidden">
                    <div className="max-h-[calc(100vh-205px)] overflow-y-auto">
                      {filteredRelationships.map((relationship) => (
                        <button
                          key={relationship.id}
                          type="button"
                          onClick={() =>
                            setSelectedRelationshipId(relationship.id)
                          }
                          className={`w-full border-b p-4 text-left text-foreground last:border-0 ${selectedRelationship?.id === relationship.id ? "bg-primary/12 ring-1 ring-inset ring-primary/35" : "hover:bg-muted/50"}`}
                        >
                          <RelationshipBadge relation={relationship.relation} />
                          <p className="mt-3 line-clamp-3 text-sm font-medium leading-6">
                            {relationship.explanation}
                          </p>
                          <div className="mt-2 flex justify-between text-xs text-muted-foreground">
                            <span>
                              {relationship.classifier_version.startsWith(
                                "rules-v1+",
                              )
                                ? "Rules + model"
                                : "Rules"}
                            </span>
                            <span>
                              {Math.round(relationship.confidence * 100)}%
                            </span>
                          </div>
                        </button>
                      ))}
                    </div>
                  </Card>
                  <div className="space-y-4">
                    {selectedRelationship && (
                      <Card>
                        <CardHeader className="border-b">
                          <div className="flex items-center justify-between">
                            <RelationshipBadge
                              relation={selectedRelationship.relation}
                            />
                            <div className="text-right">
                              <p className="text-sm font-semibold">
                                {Math.round(
                                  selectedRelationship.confidence * 100,
                                )}
                                % confidence
                              </p>
                              <p className="text-xs text-muted-foreground">
                                candidate{" "}
                                {selectedRelationship.candidate_score.toFixed(
                                  3,
                                )}
                              </p>
                            </div>
                          </div>
                        </CardHeader>
                        <CardContent className="pt-5">
                          <p className="text-base font-medium leading-7">
                            {selectedRelationship.explanation}
                          </p>
                          {selectedRelationship.differences.length > 0 && (
                            <pre className="mt-4 overflow-auto whitespace-pre-wrap rounded-lg border bg-muted p-3 text-xs leading-5 text-foreground">
                              {JSON.stringify(
                                selectedRelationship.differences,
                                null,
                                2,
                              )}
                            </pre>
                          )}
                        </CardContent>
                      </Card>
                    )}
                    {relationshipFacts && (
                      <div className="grid gap-4 lg:grid-cols-2">
                        {relationshipFacts.map((fact, index) => (
                          <Card key={fact.id}>
                            <CardHeader className="border-b">
                              <p className="text-xs font-semibold uppercase tracking-[0.1em] text-muted-foreground">
                                Fact {index === 0 ? "A" : "B"}
                              </p>
                              <CardTitle className="capitalize">
                                {shortPredicate(fact.predicate_canonical)}
                              </CardTitle>
                            </CardHeader>
                            <CardContent className="pt-5">
                              <p className="text-sm text-muted-foreground">
                                {fact.subject_raw}
                              </p>
                              <p className="mt-2 font-mono text-xl font-semibold">
                                {fact.normalized_value ?? fact.value_raw}{" "}
                                {fact.unit_canonical}
                              </p>
                              <div className="mt-3 flex gap-2">
                                <Badge variant="outline">
                                  {fact.period_label ?? "No period"}
                                </Badge>
                                <Badge variant="outline">
                                  {fact.claim_kind.toLowerCase()}
                                </Badge>
                              </div>
                              <Separator className="my-5" />
                              <blockquote className="border-l-2 border-blue-600 pl-3 text-sm leading-6 text-slate-700 dark:text-slate-200">
                                {relationshipEvidence?.[index]?.quote ??
                                  fact.context.supporting_quote}
                              </blockquote>
                            </CardContent>
                          </Card>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="mx-auto max-w-[1200px] space-y-5">
              {documents.filter((item) => item.status === "FAILED").length ===
                0 && rejectedSamples.length === 0 ? (
                <EmptyState title="Nothing needs attention" />
              ) : (
                <>
                  {latestJob?.status === "FAILED" && (
                    <Card>
                      <CardHeader className="border-b">
                        <div className="flex justify-between">
                          <div>
                            <CardTitle>
                              {latestJob.error_code ?? "Processing failure"}
                            </CardTitle>
                            <CardDescription>
                              {formatDate(latestJob.completed_at)}
                            </CardDescription>
                          </div>
                          <Badge variant="danger">failed</Badge>
                        </div>
                      </CardHeader>
                      <CardContent className="pt-5">
                        <p className="text-sm leading-6">
                          {latestJob.error_message}
                        </p>
                        <Button className="mt-5" onClick={handleRetry}>
                          <RefreshCw />
                          Retry from checkpoint
                        </Button>
                      </CardContent>
                    </Card>
                  )}
                  {rejectedSamples.length > 0 && (
                    <Card>
                      <CardHeader className="border-b">
                        <CardTitle>Rejected extraction candidates</CardTitle>
                      </CardHeader>
                      <CardContent className="divide-y p-0">
                        {rejectedSamples.map((sample) => (
                          <div key={JSON.stringify(sample)} className="p-5">
                            <div className="flex items-start justify-between gap-4">
                              <pre className="min-w-0 whitespace-pre-wrap text-sm leading-6">
                                {JSON.stringify(
                                  sample.candidate ??
                                    sample.page_error ??
                                    sample,
                                  null,
                                  2,
                                )}
                              </pre>
                              <Badge variant="warning">rejected</Badge>
                            </div>
                            <p className="mt-3 text-sm text-amber-800 dark:text-amber-300">
                              {Array.isArray(sample.reasons)
                                ? sample.reasons.join("; ")
                                : "Provider batch failure"}
                            </p>
                          </div>
                        ))}
                      </CardContent>
                    </Card>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </SidebarInset>
      <Dialog open={createProjectOpen} onOpenChange={setCreateProjectOpen}>
        <DialogContent>
          <DialogTitle>New project</DialogTitle>
          <DialogDescription className="mt-1">
            PDFs and comparisons stay inside this project.
          </DialogDescription>
          <form
            className="mt-6 space-y-4"
            onSubmit={async (event) => {
              event.preventDefault();
              if (newProjectName.trim().length < 2) return;
              try {
                await handleCreateProject(
                  newProjectName.trim(),
                  newProjectDescription.trim(),
                );
              } catch {}
            }}
          >
            <label htmlFor="new-project-name" className="block space-y-2">
              <span className="text-sm font-medium">Name</span>
              <Input
                id="new-project-name"
                autoFocus
                value={newProjectName}
                onChange={(event) => setNewProjectName(event.target.value)}
                placeholder="Project name"
              />
            </label>
            <label
              htmlFor="new-project-description"
              className="block space-y-2"
            >
              <span className="text-sm font-medium">Description</span>
              <Input
                id="new-project-description"
                value={newProjectDescription}
                onChange={(event) =>
                  setNewProjectDescription(event.target.value)
                }
                placeholder="Optional"
              />
            </label>
            <div className="flex justify-end gap-2 pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setCreateProjectOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={creatingProject || newProjectName.trim().length < 2}
              >
                {creatingProject ? "Creating…" : "Create"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </SidebarProvider>
  );
}
