export interface MerchantOffer {
  available: boolean;
  price?: number | null;
  time?: number;
  tokens?: number;
  api_calls?: number;
  api_cost?: number;
}

export interface ResourceBudget {
  time?: number | null;
  tokens?: number | null;
  api_calls?: number | null;
  api_cost?: number | null;
}

export interface ResourceUsage {
  time: number;
  tokens: number;
  api_calls: number;
  api_cost: number;
}

export interface SearchOutcome {
  purchased: boolean;
  accepted_price: number | null;
  accepted_index: number | null;
  queries: number;
  resources: ResourceUsage;
  terminal_reason: "purchased" | "resource_exhausted" | "merchants_exhausted";
}

export interface MerchantForecast {
  price_weights: Array<{ price: number; weight: number }>;
  unavailable_weight?: number;
  time?: number;
  tokens?: number;
  api_calls?: number;
  api_cost?: number;
}

export interface ShoppingDecisionInput {
  merchants: MerchantForecast[];
  budget: Required<Omit<ResourceBudget, keyof { [K in keyof ResourceBudget as ResourceBudget[K] extends null ? K : never]: never }>> | ResourceBudget;
  observedPrice: number;
  maxPurchasePrice: number;
  failurePenalty: number;
  observedMerchantIndex?: number;
}

export interface ShoppingDecision {
  action: "buy" | "continue" | "reject_without_feasible_query";
  first_merchant_index: number | null;
  reservation_price: number;
  continuation_value: number;
  next_merchant_index: number | null;
  feasible_next_merchants: number[];
  remaining_after_observation: ResourceUsage;
}

export type SearchPolicy = "accept_first" | "fixed_threshold" | "resource_aware_threshold";

export function simulatePolicy(
  offers: MerchantOffer[],
  policy: SearchPolicy,
  threshold?: number | null,
  budget?: ResourceBudget | null,
): SearchOutcome;

export function planShoppingDecision(input: ShoppingDecisionInput): ShoppingDecision;

export interface ShoppingOptimizerOptions {
  merchants: MerchantForecast[];
  budget: ResourceBudget;
  maxPurchasePrice: number;
  failurePenalty: number;
}

export interface AgentDecision {
  action: "buy" | "continue" | "reject_without_feasible_query";
  observedMerchantIndex: number;
  observedPrice: number | null;
  reservationPrice: number | null;
  nextMerchantIndex: number | null;
  remainingBudget: ResourceUsage;
  reason: string;
}

export interface QueryPermit {
  merchantIndex: number;
  timeout: number;
  maxTokens: number;
  maxApiCalls: number;
  maxApiSpend: number;
}

export class AutonomousShoppingOptimizer {
  constructor(options: ShoppingOptimizerOptions);
  readonly remainingBudget: ResourceUsage;
  readonly unqueriedMerchants: number[];
  nextQuery(): number | null;
  nextQueryPermit(): QueryPermit | null;
  observe(
    merchantIndex: number,
    observedPrice: number | null,
    actualResources?: Partial<ResourceUsage> | null,
  ): AgentDecision;
}

export { AutonomousShoppingOptimizer as ShoppingAgentMiddleware };
export type AgentMiddlewareOptions = ShoppingOptimizerOptions;