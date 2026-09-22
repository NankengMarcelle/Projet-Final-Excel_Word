import { Component, type ErrorInfo, type ReactNode } from "react";

interface GridErrorBoundaryProps {
  children: ReactNode;
  // Passed down from EditorPage.tsx (a class component can't call useLang()/useContext itself)
  // rather than defaulted here — this is the one place in the editor that previously stayed
  // hardcoded English regardless of the FR/EN toggle, since it's rendered so far from any hook.
  message: string;
  retryLabel: string;
}

interface GridErrorBoundaryState {
  error: Error | null;
}

// Scoped tightly around FortuneSheetGrid, not the whole editor page — a crash inside Fortune-
// sheet's own internals (confirmed real: calculateFormula() has thrown deep in its own
// calculateSheetFromula/setCellValue code on at least one real workbook) previously took down
// the entire route with React Router's default error boundary, forcing a full page reload to
// recover. This keeps the navy title bar, Save button, and navigation usable even if the grid
// itself can't render, and lets the user get back to the workspace without losing anything else.
export class GridErrorBoundary extends Component<GridErrorBoundaryProps, GridErrorBoundaryState> {
  state: GridErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): GridErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error("Grid crashed:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="editor-grid-wrap">
          <div className="editor-grid-error">
            <p>{this.props.message}</p>
            <p className="editor-grid-error-detail">{this.state.error.message}</p>
            <button type="button" className="editor-action-btn small" onClick={() => this.setState({ error: null })}>
              {this.props.retryLabel}
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
