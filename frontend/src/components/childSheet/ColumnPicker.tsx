import type { WorksheetColumn } from "../../types/sheetRelationship";
import { copy } from "../../i18n/copy";
import { useLang } from "../../i18n/useLang";

export function ColumnPicker({
  columns,
  selected,
  onChange,
}: {
  columns: WorksheetColumn[];
  selected: number[];
  onChange: (selected: number[]) => void;
}) {
  const { lang } = useLang();
  const t = copy[lang];

  function toggle(index: number) {
    if (selected.includes(index)) {
      onChange(selected.filter((c) => c !== index));
    } else {
      onChange([...selected, index]);
    }
  }

  return (
    <fieldset className="column-picker">
      <legend>{t.columnsToIncludeLabel}</legend>
      {columns.map((column) => (
        <label key={column.index} className="column-picker-item">
          <input
            type="checkbox"
            checked={selected.includes(column.index)}
            onChange={() => toggle(column.index)}
          />
          {column.label} {t.colSuffixLabel(column.letter)}
        </label>
      ))}
    </fieldset>
  );
}
