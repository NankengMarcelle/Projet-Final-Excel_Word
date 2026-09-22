import type { WorksheetColumn } from "../../types/sheetRelationship";

export function ColumnPicker({
  columns,
  selected,
  onChange,
}: {
  columns: WorksheetColumn[];
  selected: number[];
  onChange: (selected: number[]) => void;
}) {
  function toggle(index: number) {
    if (selected.includes(index)) {
      onChange(selected.filter((c) => c !== index));
    } else {
      onChange([...selected, index]);
    }
  }

  return (
    <fieldset className="column-picker">
      <legend>Columns to include</legend>
      {columns.map((column) => (
        <label key={column.index} className="column-picker-item">
          <input
            type="checkbox"
            checked={selected.includes(column.index)}
            onChange={() => toggle(column.index)}
          />
          {column.label} (Col {column.letter})
        </label>
      ))}
    </fieldset>
  );
}
