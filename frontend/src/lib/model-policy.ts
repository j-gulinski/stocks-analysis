/**
 * User-facing Codex routing choices.
 *
 * These are requested roles/models, not a claim about the concrete deployment
 * behind the current Codex host. The queue stores the choice for auditability.
 */
export const ORCHESTRATOR_MODELS = [
  {
    value: "Sol high",
    label: "Sol · high",
    description: "Złożona analiza, scenariusze i niezależna weryfikacja.",
  },
  {
    value: "Terra high",
    label: "Terra · high",
    description: "Standardowa implementacja i analiza o średniej złożoności.",
  },
  {
    value: "GPT-5.3 high",
    label: "GPT-5.3 · high",
    description: "Testy, kontrola mechaniczna i krótsze zadania.",
  },
  {
    value: "Luna medium",
    label: "Luna · medium",
    description: "Podstawowe, szybkie zadania i odczyty.",
  },
] as const;

export const DEFAULT_ORCHESTRATOR_MODEL = ORCHESTRATOR_MODELS[0].value;

export function modelPolicyDescription(value: string): string {
  return ORCHESTRATOR_MODELS.find((option) => option.value === value)?.description
    ?? "Model żądany przez użytkownika; dokładny deployment hosta nie jest ujawniany.";
}
