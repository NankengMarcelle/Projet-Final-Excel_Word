export type FilterOperator =
  | "equals"
  | "not_equals"
  | "contains"
  | "greater_than"
  | "less_than"
  | "greater_or_equal"
  | "less_or_equal"
  | "is_empty"
  | "is_not_empty"
  | "in";

export interface FilterConditionLeaf {
  // 1-indexed column number, not header text — a real multi-row-header matrix sheet can
  // repeat the same leaf label under different group headers (e.g. "AE voté" under both
  // "Prévision 2026" and "Prévision 2027"), so column identity has to be positional. See
  // WorksheetColumn in sheetRelationship.ts for the {index, label} pairing used to display
  // this as a readable dropdown while keeping the number as the actual value.
  column: number;
  operator: FilterOperator;
  value?: unknown;
}

export interface FilterConditionGroup {
  logic: "AND" | "OR";
  conditions: FilterNode[];
}

export type FilterNode = FilterConditionLeaf | FilterConditionGroup;

export function isFilterGroup(node: FilterNode): node is FilterConditionGroup {
  return "logic" in node;
}
