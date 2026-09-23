import type { FilterConditionGroup, FilterConditionLeaf, FilterOperator } from "../../types/filter";
import { isFilterGroup } from "../../types/filter";
import type { WorksheetColumn } from "../../types/sheetRelationship";

const OPERATORS: { value: FilterOperator; label: string }[] = [
  { value: "equals", label: "equals" },
  { value: "not_equals", label: "not equals" },
  { value: "contains", label: "contains" },
  { value: "greater_than", label: "greater than" },
  { value: "less_than", label: "less than" },
  { value: "greater_or_equal", label: "greater or equal" },
  { value: "less_or_equal", label: "less or equal" },
  { value: "is_empty", label: "is empty" },
  { value: "is_not_empty", label: "is not empty" },
  { value: "in", label: "in (comma-separated)" },
];

function needsValue(operator: FilterOperator): boolean {
  return operator !== "is_empty" && operator !== "is_not_empty";
}

function valueToText(value: unknown): string {
  if (Array.isArray(value)) return value.join(",");
  if (typeof value === "string") return value;
  return value == null ? "" : String(value);
}

function ConditionLeafEditor({
  condition,
  columns,
  onChange,
  onRemove,
}: {
  condition: FilterConditionLeaf;
  columns: WorksheetColumn[];
  onChange: (condition: FilterConditionLeaf) => void;
  onRemove: () => void;
}) {
  return (
    <div className="filter-condition-row">
      <select
        value={condition.column}
        onChange={(e) => onChange({ ...condition, column: Number(e.target.value) })}
      >
        <option value="" disabled>
          Column
        </option>
        {columns.map((column) => (
          <option key={column.index} value={column.index}>
            {column.label} (Col {column.letter})
          </option>
        ))}
      </select>
      <select
        value={condition.operator}
        onChange={(e) => onChange({ ...condition, operator: e.target.value as FilterOperator })}
      >
        {OPERATORS.map((op) => (
          <option key={op.value} value={op.value}>
            {op.label}
          </option>
        ))}
      </select>
      {needsValue(condition.operator) && (
        <input
          type="text"
          value={valueToText(condition.value)}
          onChange={(e) => {
            const raw = e.target.value;
            const value = condition.operator === "in" ? raw.split(",").map((s) => s.trim()) : raw;
            onChange({ ...condition, value });
          }}
        />
      )}
      <button type="button" className="editor-action-btn small ghost" onClick={onRemove}>
        Remove
      </button>
    </div>
  );
}

// Deliberately flat: just a list of conditions, always implicitly AND'd together. The
// underlying data shape (FilterConditionGroup, with "logic" and nested groups) still supports
// AND/OR and nesting on the backend (filter_engine.py's evaluate()), but that was confusing for
// a non-technical user configuring a child sheet — "just the condition part is necessary" — so
// this editor only ever produces/edits a single flat AND group of leaf conditions. A group's
// `logic` is left as "AND" and never surfaced as a choice; any leaf that happens to be a nested
// group (not possible to create from this UI, but tolerated if present in existing data) is
// simply skipped rather than rendered.
export function FilterGroupEditor({
  group,
  columns,
  onChange,
}: {
  group: FilterConditionGroup;
  columns: WorksheetColumn[];
  onChange: (group: FilterConditionGroup) => void;
}) {
  function updateChild(index: number, condition: FilterConditionLeaf) {
    const conditions = [...group.conditions];
    conditions[index] = condition;
    onChange({ ...group, conditions });
  }

  function removeChild(index: number) {
    onChange({ ...group, conditions: group.conditions.filter((_, i) => i !== index) });
  }

  function addCondition() {
    onChange({
      ...group,
      conditions: [
        ...group.conditions,
        { column: columns[0]?.index ?? 1, operator: "equals", value: "" },
      ],
    });
  }

  return (
    <div className="filter-group">
      {group.conditions.map((node, index) =>
        isFilterGroup(node) ? null : (
          <ConditionLeafEditor
            key={index}
            condition={node}
            columns={columns}
            onChange={(updated) => updateChild(index, updated)}
            onRemove={() => removeChild(index)}
          />
        )
      )}
      <button type="button" className="editor-action-btn small ghost" onClick={addCondition}>
        + Condition
      </button>
    </div>
  );
}
