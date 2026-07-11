/**
 * User-facing Codex routing choices.
 *
 * These are requested roles/models, not a claim about the concrete deployment
 * behind the current Codex host. The queue stores the choice for auditability.
 */
export const ORCHESTRATOR_MODELS = [
  {
    value: "gpt-5.6-terra",
    label: "GPT-5.6 Terra · high",
    description: "Zalecany worker: mocna implementacja i synteza przy lepszej efektywności niż Sol.",
  },
  {
    value: "gpt-5.6-sol",
    label: "Sol · high",
    description: "Najwyższa jakość: głęboka analiza, scenariusze finansowe i ścisła weryfikacja.",
  },
  {
    value: "gpt-5.6-luna",
    label: "GPT-5.6 Luna · medium",
    description: "Proste i wysokonakładowe zadania; nie jako domyślny analityk inwestycyjny.",
  },
] as const;

export const DEFAULT_ORCHESTRATOR_MODEL = ORCHESTRATOR_MODELS[0].value;

export function defaultModelForWorkflow(workflow: string): string {
  return workflow === "stock-deep-analysis"
    ? "gpt-5.6-sol"
    : DEFAULT_ORCHESTRATOR_MODEL;
}

export function modelPolicyDescription(value: string): string {
  return ORCHESTRATOR_MODELS.find((option) => option.value === value)?.description
    ?? "Model żądany przez użytkownika; dokładny deployment hosta nie jest ujawniany.";
}
