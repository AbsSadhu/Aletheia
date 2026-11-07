import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** change this (e.g. the pathname) to clear a caught error when the user navigates away */
  resetKey: string;
}

interface State {
  error: Error | null;
  key: string;
}

/**
 * A render error (or a lazy chunk that failed to load) in one page must not unmount the whole app,
 * which shows as a black window. The sidebar stays; the page area shows the error and a way back.
 */
export default class PageErrorBoundary extends Component<Props, State> {
  state: State = { error: null, key: this.props.resetKey };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    return props.resetKey !== state.key ? { error: null, key: props.resetKey } : null;
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Page crashed:", error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <main className="page-shell">
        <div className="card" role="alert" style={{ padding: "var(--space-8)" }}>
          <p style={{ fontWeight: 600, marginBottom: "var(--space-2)" }}>This page hit an error.</p>
          <p style={{ color: "var(--text-secondary)", marginBottom: "var(--space-4)" }}>{this.state.error.message}</p>
          <button className="btn btn-secondary" onClick={() => this.setState({ error: null })}>
            Try again
          </button>
        </div>
      </main>
    );
  }
}
